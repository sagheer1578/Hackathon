"""FastAPI application for CityLab Diagnostics Medical Lab Report Explainer."""
import hashlib
import hmac
import json
import os
import threading
import time
from collections import defaultdict, deque
from decimal import Decimal
from pathlib import Path
from typing import Literal
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from filelock import Timeout
from pydantic import Field
from starlette.requests import Request
from .ai import LLMAdapter, answer, enhance_analysis_with_ai
from .corpus_parser import ingest_corpus_directory
from .engine import analyze
from .ingestion import ExtractionError, MAX_BYTES, extract_report
from .models import Analysis, Database, Model, Report
from .pdf import generate_pdf
from .storage import JSON_FILENAMES, Repository, StorageError


DEMO_PERSONAS = [
    {
        'patient_id': 'patient-p001',
        'name': 'Arjun Mehta',
        'tag': 'Boundaries & Unit Conversions',
        'description': 'SGPT at 45 U/L exact limit, FBS in mmol/L, Total Cholesterol at 200 mg/dL, elevated TSH.',
        'token': 'citylab-demo-p001-arjun-mehta-access-key-01',
    },
    {
        'patient_id': 'patient-p002',
        'name': 'Fatima Khan',
        'tag': 'Urgent Critical Values',
        'description': 'Critical FBS (22.5 mmol/L -> 405 mg/dL) and Potassium (6.3 mmol/L) plus Low Hemoglobin.',
        'token': 'citylab-demo-p002-fatima-khan-access-key-02',
    },
    {
        'patient_id': 'patient-p003',
        'name': 'Jordan Patel',
        'tag': 'Missing Demographics',
        'description': 'Age omitted and sex unknown; refuses range guessing while flagging urgent Potassium.',
        'token': 'citylab-demo-p003-jordan-patel-access-key-03',
    },
    {
        'patient_id': 'patient-p004',
        'name': 'Viktor Chen',
        'tag': 'Noisy Report & Edge Cases',
        'description': '200+ boilerplate lines, prompt-injection neutralized, Serum Ferritin, missing unit, duplicates.',
        'token': 'citylab-demo-p004-viktor-chen-access-key-04',
    },
]


class PayloadTooLarge(Exception):
    pass


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        total = 0

        async def limited():
            nonlocal total
            message = await receive()
            total += len(message.get('body', b''))
            if total > MAX_BYTES + 65536:
                raise PayloadTooLarge()
            return message

        try:
            await self.app(scope, limited, send)
        except PayloadTooLarge:
            await JSONResponse({'detail': 'Request exceeds 8 MiB upload limit.'}, status_code=413)(
                scope, receive, send
            )


class ChatRequest(Model):
    question: str = Field(min_length=1, max_length=1200)


class AnalyzeRequest(Model):
    report_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')


class DemographicsUpdateRequest(Model):
    age_at_report: Decimal | None = Field(default=None, ge=0, le=150)
    sex_at_report: Literal['female', 'male', 'unknown'] = 'unknown'


def create_app(
    data_dir: str | Path | None = None,
    auth_tokens: dict[str, str] | None = None,
    corpus_dir: str | Path | None = None,
    demo_mode: bool | None = None,
    auto_ingest: bool | None = None,
) -> FastAPI:
    app = FastAPI(
        title='CityLab Diagnostics',
        version='1.0.0',
        description='Evidence-first medical laboratory report explainer backed by a 9-file JSON store and deterministic rules engine.',
    )
    app.add_middleware(BodyLimit)
    cors_origins = [o.strip() for o in os.getenv('CORS_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173').split(',') if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=['GET', 'POST'],
        allow_headers=['Authorization', 'Content-Type'],
    )

    repo = Repository(data_dir or os.getenv('DATA_DIR', 'data'))
    resolved_corpus = Path(corpus_dir or os.getenv('CORPUS_DIR', 'corpus'))
    adapter = LLMAdapter()

    if demo_mode is None:
        demo_mode = os.getenv('DEMO_MODE', 'true').strip().lower() == 'true'

    should_auto_ingest = (auth_tokens is None) if auto_ingest is None else auto_ingest
    if should_auto_ingest and resolved_corpus.is_dir() and not repo.initialized():
        ingest_corpus_directory(resolved_corpus, repo, analyze_fn=analyze)

    if auth_tokens is None:
        raw_tokens = os.getenv('AUTH_TOKENS', '{}').strip() or '{}'
        try:
            parsed_tokens = json.loads(raw_tokens)
        except ValueError:
            raise RuntimeError('AUTH_TOKENS must be a JSON object mapping 32+ char tokens to patient IDs.') from None
        if not isinstance(parsed_tokens, dict):
            raise RuntimeError('AUTH_TOKENS must be a JSON object.')
        auth_tokens = dict(parsed_tokens)
        if demo_mode:
            for persona in DEMO_PERSONAS:
                auth_tokens.setdefault(persona['token'], persona['patient_id'])
            extra_demo_token = os.getenv('DEMO_TOKEN', '').strip()
            if extra_demo_token:
                if len(extra_demo_token) < 32:
                    raise RuntimeError('DEMO_TOKEN must contain at least 32 characters.')
                auth_tokens.setdefault(extra_demo_token, 'patient-p001')

    if not isinstance(auth_tokens, dict) or any(
        not isinstance(k, str) or len(k) < 32 or not isinstance(v, str)
        for k, v in auth_tokens.items()
    ):
        raise RuntimeError('Every authorization token must contain at least 32 characters and map to one patient ID.')

    hashed_tokens = {hashlib.sha256(k.encode()).digest(): v for k, v in auth_tokens.items()}
    bearer = HTTPBearer(auto_error=False)
    buckets: dict[str, deque[float]] = defaultdict(deque)
    bucket_lock = threading.Lock()

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    def authorized(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        host = request.client.host if request.client else 'unknown'
        now = time.monotonic()
        with bucket_lock:
            if len(buckets) > 10000:
                for key in list(buckets):
                    if not buckets[key] or buckets[key][-1] < now - 60:
                        del buckets[key]
            queue = buckets[host]
            while queue and queue[0] < now - 60:
                queue.popleft()
            if len(queue) >= 120:
                raise HTTPException(429, 'Too many requests. Please wait one minute.', headers={'Retry-After': '60'})
            queue.append(now)

        supplied = hashlib.sha256((credentials.credentials if credentials else '').encode()).digest()
        for digest, patient_id in hashed_tokens.items():
            if hmac.compare_digest(digest, supplied):
                return patient_id
        raise HTTPException(401, 'A valid patient access key is required.', headers={'WWW-Authenticate': 'Bearer'})

    def get_report(report_id: str, patient_id: str) -> tuple[Database, Report]:
        db = repo.read()
        report = db.reports.get(report_id)
        if report is None or report.patient_id != patient_id:
            raise HTTPException(404, 'Report not found.')
        return db, report

    def current_analysis(db: Database, report: Report) -> Analysis:
        existing = db.analysis_results.get(report.id)
        if existing and existing.knowledge_version == db.knowledge_version:
            return existing
        result = analyze(report, db)

        def save(current: Database) -> None:
            if current.knowledge_version == db.knowledge_version and current.reports.get(report.id) == report:
                current.analysis_results[report.id] = result

        repo.update(save)
        return result

    @app.exception_handler(StorageError)
    @app.exception_handler(Timeout)
    async def storage_error(request, exc):
        return JSONResponse({'detail': 'Storage is unavailable. Existing data has been preserved.'}, status_code=503)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'detail': 'Invalid input. Check the documented request format.'}, status_code=422)

    @app.exception_handler(ExtractionError)
    async def extraction_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=422)

    @app.get('/api/health')
    def health():
        db = repo.read()
        return {
            'status': 'ok',
            'knowledge_ready': db.reviewed and bool(db.test_aliases),
            'knowledge_version': db.knowledge_version,
            'storage_files': len(JSON_FILENAMES),
            'patients_count': len(db.patients),
            'reports_count': len(db.reports),
            'ai_configured': adapter.is_configured(),
            'llm_provider': adapter.provider,
        }

    @app.get('/api/demo/sessions')
    def demo_sessions():
        if not demo_mode:
            return {'enabled': False, 'personas': []}
        db = repo.read()
        available = [
            p for p in DEMO_PERSONAS if p['patient_id'] in db.patients and p['token'] in auth_tokens
        ]
        return {'enabled': True, 'personas': available}

    @app.get('/api/session')
    def session(patient_id: str = Depends(authorized)):
        db = repo.read()
        patient = db.patients.get(patient_id)
        if not patient:
            raise HTTPException(403, 'This access key has no provisioned patient record.')
        return {
            'patient': patient,
            'knowledge_ready': db.reviewed and bool(db.test_aliases),
            'knowledge_version': db.knowledge_version,
            'tests_count': len(db.test_aliases),
            'ranges_count': len(db.reference_ranges),
            'urgent_rules_count': len(db.urgent_thresholds),
            'safety_rules_count': len(db.safety_rules),
            'ai_configured': adapter.is_configured(),
            'llm_provider': adapter.provider,
        }

    @app.get('/api/reports')
    def list_reports(patient_id: str = Depends(authorized)):
        db = repo.read()
        items = []
        for r in db.reports.values():
            if r.patient_id != patient_id:
                continue
            meta = db.report_metadata.get(r.id)
            items.append(
                {
                    'id': r.id,
                    'report_date': r.report_date,
                    'tests': len(r.measurements),
                    'synthetic': r.synthetic,
                    'source_file': r.source_file or (meta.source_file if meta else ''),
                    'noise_lines_skipped': meta.noise_lines_skipped if meta else 0,
                    'prompt_injection_detected': meta.prompt_injection_detected if meta else False,
                    'issues_count': len(r.issues),
                }
            )
        items.sort(key=lambda x: str(x['report_date'] or ''), reverse=True)
        return {'reports': items}

    @app.post('/api/reports/upload', status_code=201)
    def upload(file: UploadFile = File(...), patient_id: str = Depends(authorized)):
        if patient_id not in repo.read().patients:
            raise HTTPException(403, 'Patient is not provisioned.')
        content = file.file.read(MAX_BYTES + 1)
        report, metadata, _ = extract_report(content, file.filename or 'upload.txt', authorized_patient=patient_id)

        def save(db: Database) -> None:
            existing = db.reports.get(report.id)
            if existing and existing.patient_id != patient_id:
                raise HTTPException(409, 'Report identifier conflict.')
            if existing and existing != report:
                raise HTTPException(409, 'Existing report differs; review required.')
            db.reports[report.id] = report
            db.report_metadata[report.id] = metadata

        repo.update(save)
        return {
            'report_id': report.id,
            'issues': report.issues,
            'noise_lines_skipped': metadata.noise_lines_skipped,
            'prompt_injection_detected': metadata.prompt_injection_detected,
        }

    @app.post('/api/reports/analyze')
    async def analyze_report(payload: AnalyzeRequest, patient_id: str = Depends(authorized)):
        db, report = get_report(payload.report_id, patient_id)
        analysis = current_analysis(db, report)
        if adapter.is_configured() and not analysis.ai_enhanced:
            enhanced = await enhance_analysis_with_ai(analysis, db, adapter)
            if enhanced != analysis:
                def save_enhanced(current: Database) -> None:
                    if current.knowledge_version == db.knowledge_version and current.reports.get(report.id) == report:
                        current.analysis_results[report.id] = enhanced
                repo.update(save_enhanced)
                analysis = enhanced
        return analysis

    @app.get('/api/reports/{report_id}')
    def report_detail(report_id: str, patient_id: str = Depends(authorized)):
        db, report = get_report(report_id, patient_id)
        analysis = current_analysis(db, report)
        return {
            'report': report,
            'patient': db.patients[patient_id],
            'metadata': db.report_metadata.get(report_id),
            'analysis': analysis,
        }

    @app.get('/api/reports/{report_id}/results')
    def report_results(report_id: str, patient_id: str = Depends(authorized)):
        db, report = get_report(report_id, patient_id)
        return current_analysis(db, report)

    @app.post('/api/reports/{report_id}/chat')
    async def chat(report_id: str, payload: ChatRequest, patient_id: str = Depends(authorized)):
        db, report = get_report(report_id, patient_id)
        analysis = current_analysis(db, report)
        return await answer(payload.question, analysis, adapter, db=db, report=report)

    @app.get('/api/reports/{report_id}/download')
    def download(report_id: str, patient_id: str = Depends(authorized)):
        db, report = get_report(report_id, patient_id)
        analysis = current_analysis(db, report)
        content = generate_pdf(db.patients[patient_id], report, analysis)
        return Response(
            content,
            media_type='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="citylab-{report.id}.pdf"'},
        )

    @app.post('/api/reports/{report_id}/demographics')
    def update_demographics(
        report_id: str,
        payload: DemographicsUpdateRequest,
        patient_id: str = Depends(authorized),
    ):
        get_report(report_id, patient_id)
        updated_holder: dict[str, object] = {}

        def mutate(current: Database) -> None:
            rep = current.reports.get(report_id)
            if rep is None or rep.patient_id != patient_id:
                raise HTTPException(404, 'Report not found.')
            rep.age_at_report = payload.age_at_report
            rep.sex_at_report = payload.sex_at_report
            filtered_issues = [
                i for i in rep.issues if not i.startswith('Demographics updated via session:') and not i.startswith('Demographics reset via session:')
            ]
            if payload.age_at_report is None and payload.sex_at_report == 'unknown':
                filtered_issues.append('Demographics reset via session: age omitted and sex set to unknown.')
            else:
                age_txt = str(payload.age_at_report) if payload.age_at_report is not None else 'missing'
                filtered_issues.append(
                    f'Demographics updated via session: age={age_txt}, sex={payload.sex_at_report}.'
                )
            rep.issues = filtered_issues
            new_analysis = analyze(rep, current)
            current.reports[report_id] = rep
            current.analysis_results[report_id] = new_analysis
            updated_holder['report'] = rep
            updated_holder['analysis'] = new_analysis

        updated_db = repo.update(mutate)
        return {
            'report': updated_holder['report'],
            'patient': updated_db.patients[patient_id],
            'metadata': updated_db.report_metadata.get(report_id),
            'analysis': updated_holder['analysis'],
        }

    frontend_dist = Path(__file__).resolve().parent.parent.parent / 'frontend' / 'dist'
    if (frontend_dist / 'index.html').is_file() and (frontend_dist / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=str(frontend_dist / 'assets')), name='frontend-assets')

        @app.get('/{full_path:path}', include_in_schema=False)
        def serve_spa(full_path: str):
            if full_path == 'api' or full_path.startswith('api/'):
                raise HTTPException(404, 'Endpoint not found.')
            return FileResponse(frontend_dist / 'index.html')

    app.state.repo = repo
    return app


app = create_app()
