"""FastAPI application for CityLab Diagnostics Medical Lab Report Explainer."""
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
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
from .ai import LLMAdapter, answer, compute_analysis_revision, enhance_analysis_with_ai
from .corpus_parser import ingest_corpus_directory
from .engine import analyze
from .ingestion import ExtractionError, MAX_BYTES, MEDIA_TYPES, extract_report, ocr_available
from .models import AccessCredential, Analysis, Database, Model, Patient, Report, SessionRecord
from .pdf import generate_pdf
from .storage import CANONICAL_FILENAME, Repository, StorageError


DEMO_PERSONAS = [
    {
        'patient_id': 'patient-p001',
        'name': 'Arjun Mehta',
        'tag': 'Synthetic demo',
        'description': 'Reference limits and unit conversions',
        'token': 'citylab-demo-p001-arjun-mehta-access-key-01',
    },
    {
        'patient_id': 'patient-p002',
        'name': 'Fatima Khan',
        'tag': 'Synthetic demo',
        'description': 'Urgent findings',
        'token': 'citylab-demo-p002-fatima-khan-access-key-02',
    },
    {
        'patient_id': 'patient-p003',
        'name': 'Jordan Patel',
        'tag': 'Synthetic demo',
        'description': 'Missing patient information',
        'token': 'citylab-demo-p003-jordan-patel-access-key-03',
    },
    {
        'patient_id': 'patient-p004',
        'name': 'Viktor Chen',
        'tag': 'Synthetic demo',
        'description': 'Incomplete and unusual report data',
        'token': 'citylab-demo-p004-viktor-chen-access-key-04',
    },
]

CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # 32 unambiguous symbols -> 5 bits per char
SESSION_TTL_HOURS = 24


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _generate_access_code() -> str:
    # 30 random symbols from a 32-symbol alphabet = 150 bits of CSPRNG entropy.
    groups = [''.join(secrets.choice(CODE_ALPHABET) for _ in range(5)) for _ in range(6)]
    return 'CLD-' + '-'.join(groups)


def _generate_session_token() -> str:
    return 'st-' + secrets.token_urlsafe(32)


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


class RegisterRequest(Model):
    name: str = Field(min_length=1, max_length=120)


class LoginRequest(Model):
    access_code: str = Field(min_length=1, max_length=200)


class ChatRequest(Model):
    question: str = Field(min_length=1, max_length=1200)
    active_measurement_ids: list[str] = Field(default_factory=list, max_length=10)
    context_revision: str | None = Field(default=None, max_length=80)


class AnalyzeRequest(Model):
    report_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')


class DemographicsUpdateRequest(Model):
    age_at_report: Decimal | None = Field(default=None, ge=0, le=150)
    sex_at_report: Literal['female', 'male', 'unknown'] = 'unknown'


class ReviewMeasurementEdit(Model):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    test: str = Field(min_length=1, max_length=160)
    value: str = Field(max_length=80)
    unit: str = Field(default='', max_length=80)


class ReviewUpdateRequest(Model):
    measurements: list[ReviewMeasurementEdit] = Field(min_length=1, max_length=500)
    age_at_report: Decimal | None = Field(default=None, ge=0, le=150)
    sex_at_report: Literal['female', 'male', 'unknown'] | None = None
    confirm_name_mismatch: bool = False


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
        description='Evidence-first medical laboratory report explainer backed by an atomic JSON snapshot and deterministic rules engine.',
    )
    app.add_middleware(BodyLimit)
    cors_origins = [
        o.strip()
        for o in os.getenv(
            'CORS_ORIGINS',
            'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8001,http://localhost:8001',
        ).split(',')
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=['GET', 'POST', 'PATCH'],
        allow_headers=['Authorization', 'Content-Type'],
    )

    repo = Repository(data_dir or os.getenv('DATA_DIR', 'data'))
    resolved_corpus = Path(corpus_dir or os.getenv('CORPUS_DIR', 'corpus'))
    adapter = LLMAdapter()

    if demo_mode is None:
        demo_mode = os.getenv('DEMO_MODE', 'true').strip().lower() == 'true'
    public_demo = os.getenv('PUBLIC_DEMO_MODE', 'false').strip().lower() == 'true'

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
    login_buckets: dict[str, deque[float]] = defaultdict(deque)
    bucket_lock = threading.Lock()

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    def _enforce_rate_limit(bucket_map: dict[str, deque[float]], host: str, limit: int) -> None:
        now = time.monotonic()
        with bucket_lock:
            if len(bucket_map) > 10000:
                for key in list(bucket_map):
                    if not bucket_map[key] or bucket_map[key][-1] < now - 60:
                        del bucket_map[key]
            queue = bucket_map[host]
            while queue and queue[0] < now - 60:
                queue.popleft()
            if len(queue) >= limit:
                raise HTTPException(429, 'Too many requests. Please wait one minute.', headers={'Retry-After': '60'})
            queue.append(now)

    def _resolve_bearer(raw_token: str) -> tuple[str, str | None] | None:
        if not raw_token:
            return None
        supplied = hashlib.sha256(raw_token.encode()).digest()
        for digest, patient_id in hashed_tokens.items():
            if hmac.compare_digest(digest, supplied):
                return patient_id, None

        db = repo.read()
        tok_hex = _sha256_hex(raw_token)
        now = datetime.now(timezone.utc)
        for sess in db.sessions.values():
            if hmac.compare_digest(sess.token_sha256, tok_hex) and sess.expires_at > now:
                return sess.patient_id, sess.session_id
        for cred in db.credentials.values():
            if hmac.compare_digest(cred.code_sha256, tok_hex):
                return cred.patient_id, None
        return None

    def authorized(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
        host = request.client.host if request.client else 'unknown'
        _enforce_rate_limit(buckets, host, 120)
        resolved = _resolve_bearer(credentials.credentials if credentials else '')
        if resolved is not None:
            return resolved[0]
        raise HTTPException(401, 'A valid patient access code is required.', headers={'WWW-Authenticate': 'Bearer'})

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

    def _build_session_payload(db: Database, patient: Patient) -> dict:
        return {
            'patient': patient,
            'knowledge_ready': db.reviewed and bool(db.test_aliases),
            'knowledge_version': db.knowledge_version,
            'knowledge_provenance': db.knowledge_provenance,
            'synthetic_demo': bool(
                demo_mode and db.knowledge_provenance == 'synthetic' and patient.profile_type == 'demo'
            ),
            'public_demo': public_demo,
            'ocr_available': ocr_available(),
            'tests_count': len(db.test_aliases),
            'ranges_count': len(db.reference_ranges),
            'urgent_rules_count': len(db.urgent_thresholds),
            'safety_rules_count': len(db.safety_rules),
            'ai_configured': adapter.is_configured(),
            'llm_provider': adapter.provider,
        }

    def _build_detail_payload(db: Database, report: Report, analysis: Analysis) -> dict:
        return {
            'report': report,
            'patient': db.patients[report.patient_id],
            'metadata': db.report_metadata.get(report.id),
            'analysis': analysis,
            'analysis_revision': compute_analysis_revision(report, analysis),
        }

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
            'knowledge_provenance': db.knowledge_provenance,
            'synthetic_demo': demo_mode and db.knowledge_provenance == 'synthetic',
            'public_demo': public_demo,
            'ocr_available': ocr_available(),
            'storage_mode': 'canonical-atomic-snapshot',
            'snapshot_file': CANONICAL_FILENAME,
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
        return {'enabled': True, 'public_demo': public_demo, 'personas': available}

    @app.post('/api/auth/register', status_code=201)
    def register_profile(request: Request, payload: RegisterRequest):
        host = request.client.host if request.client else 'unknown'
        _enforce_rate_limit(login_buckets, host, 25)
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in payload.name):
            raise HTTPException(422, 'Enter a valid full name without control characters.')
        clean_name = ' '.join(payload.name.split())
        if not clean_name:
            raise HTTPException(422, 'Enter a valid full name.')

        patient_id = 'p-' + secrets.token_hex(12)
        access_code = _generate_access_code()
        session_token = _generate_session_token()
        session_id = 's-' + secrets.token_hex(12)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=SESSION_TTL_HOURS)

        patient = Patient(
            id=patient_id,
            name=clean_name,
            profile_type='personal',
            created_at=now,
        )
        credential = AccessCredential(
            patient_id=patient_id,
            code_sha256=_sha256_hex(access_code),
            created_at=now,
        )
        sess = SessionRecord(
            session_id=session_id,
            patient_id=patient_id,
            token_sha256=_sha256_hex(session_token),
            created_at=now,
            expires_at=expires_at,
        )

        def create_personal(db: Database) -> None:
            for sid in [k for k, v in db.sessions.items() if v.expires_at <= now]:
                del db.sessions[sid]
            db.patients[patient_id] = patient
            db.credentials[patient_id] = credential
            db.sessions[session_id] = sess

        repo.update(create_personal)
        return {
            'profile': patient,
            'access_code': access_code,
            'session_token': session_token,
            'expires_at': expires_at,
        }

    @app.post('/api/auth/login')
    def login_with_code(request: Request, payload: LoginRequest):
        host = request.client.host if request.client else 'unknown'
        _enforce_rate_limit(login_buckets, host, 25)

        raw_code = payload.access_code.strip()
        invalid_msg = 'We couldn’t find a profile with that access code. Check the code and try again.'
        if not raw_code:
            raise HTTPException(401, invalid_msg)

        db = repo.read()
        code_hex = _sha256_hex(raw_code)
        code_digest = hashlib.sha256(raw_code.encode()).digest()

        matched_patient_id: str | None = None
        for cred in db.credentials.values():
            if hmac.compare_digest(cred.code_sha256, code_hex):
                matched_patient_id = cred.patient_id
                break
        if matched_patient_id is None:
            for digest, pid in hashed_tokens.items():
                if hmac.compare_digest(digest, code_digest):
                    matched_patient_id = pid
                    break

        if matched_patient_id is None or matched_patient_id not in db.patients:
            raise HTTPException(401, invalid_msg)

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
        session_token = _generate_session_token()
        session_id = 's-' + secrets.token_hex(12)
        sess = SessionRecord(
            session_id=session_id,
            patient_id=matched_patient_id,
            token_sha256=_sha256_hex(session_token),
            created_at=now,
            expires_at=expires_at,
        )

        def save_session(current: Database) -> None:
            if matched_patient_id not in current.patients:
                raise HTTPException(401, invalid_msg)
            for sid in [k for k, v in current.sessions.items() if v.expires_at <= now]:
                del current.sessions[sid]
            current.sessions[session_id] = sess

        updated_db = repo.update(save_session)
        return {
            'profile': updated_db.patients[matched_patient_id],
            'session_token': session_token,
            'expires_at': expires_at,
        }

    @app.post('/api/auth/logout')
    def logout_session(
        patient_id: str = Depends(authorized),
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ):
        raw_token = credentials.credentials if credentials else ''
        tok_hex = _sha256_hex(raw_token) if raw_token else ''
        if tok_hex:
            def revoke(current: Database) -> None:
                for sid in [
                    k
                    for k, v in current.sessions.items()
                    if v.patient_id == patient_id and hmac.compare_digest(v.token_sha256, tok_hex)
                ]:
                    del current.sessions[sid]

            repo.update(revoke)
        return {'status': 'signed_out'}

    @app.get('/api/auth/me')
    def auth_me(patient_id: str = Depends(authorized)):
        db = repo.read()
        patient = db.patients.get(patient_id)
        if not patient:
            raise HTTPException(403, 'This access code has no provisioned profile.')
        return _build_session_payload(db, patient)

    @app.get('/api/session')
    def session(patient_id: str = Depends(authorized)):
        db = repo.read()
        patient = db.patients.get(patient_id)
        if not patient:
            raise HTTPException(403, 'This access key has no provisioned patient record.')
        return _build_session_payload(db, patient)

    @app.get('/api/reports')
    def list_reports(patient_id: str = Depends(authorized)):
        db = repo.read()
        items = []
        for r in db.reports.values():
            if r.patient_id != patient_id:
                continue
            meta = db.report_metadata.get(r.id)
            uploaded_at = r.uploaded_at or (meta.ingested_at if meta else None)
            items.append(
                {
                    'id': r.id,
                    'title': r.title or r.source_file or r.id,
                    'report_date': r.report_date,
                    'uploaded_at': uploaded_at,
                    'review_status': r.review_status,
                    'name_mismatch_warning': r.name_mismatch_warning,
                    'tests': len(r.measurements),
                    'synthetic': r.synthetic,
                    'source_file': r.source_file or (meta.source_file if meta else ''),
                    'has_source_file': bool(r.stored_filename),
                    'noise_lines_skipped': meta.noise_lines_skipped if meta else 0,
                    'prompt_injection_detected': meta.prompt_injection_detected if meta else False,
                    'issues_count': len(r.issues),
                }
            )
        items.sort(key=lambda x: str(x['uploaded_at'] or x['report_date'] or ''), reverse=True)
        return {'reports': items}

    @app.post('/api/reports/upload', status_code=201)
    def upload(file: UploadFile = File(...), patient_id: str = Depends(authorized)):
        db = repo.read()
        patient = db.patients.get(patient_id)
        if not patient:
            raise HTTPException(403, 'Patient is not provisioned.')
        content = file.file.read(MAX_BYTES + 1)
        clean_filename = file.filename or 'upload.txt'
        suffix = Path(clean_filename).suffix.lower()

        report, metadata, _ = extract_report(
            content,
            clean_filename,
            authorized_patient=patient_id,
            synthetic=False,
            authenticated_patient_name=patient.name,
            strict_patient_id=False,
        )
        now = datetime.now(timezone.utc)
        report.title = report.source_file
        report.uploaded_at = now
        report.source_media_type = MEDIA_TYPES.get(suffix, 'application/octet-stream')
        stored_rel = repo.save_upload_file(patient_id, report.id, suffix, content)
        report.stored_filename = stored_rel

        initial_analysis = analyze(report, db)

        def save(current: Database) -> None:
            existing = current.reports.get(report.id)
            if existing:
                if existing.patient_id != patient_id:
                    raise HTTPException(409, 'Report identifier conflict.')
                same_source = (
                    existing.source_hash == report.source_hash
                    and existing.source_file == report.source_file
                    and not existing.demographics_overridden
                    and not any(m.user_corrected for m in existing.measurements)
                )
                if same_source:
                    return
                raise HTTPException(409, 'Existing report differs; review required.')
            ana = (
                initial_analysis
                if current.knowledge_version == db.knowledge_version
                else analyze(report, current)
            )
            current.reports[report.id] = report
            current.report_metadata[report.id] = metadata
            current.analysis_results[report.id] = ana

        try:
            repo.update(save)
        except Exception:
            repo.remove_upload_file(stored_rel)
            raise

        return {
            'report_id': report.id,
            'review_status': report.review_status,
            'name_mismatch_warning': report.name_mismatch_warning,
            'issues': report.issues,
            'noise_lines_skipped': metadata.noise_lines_skipped,
            'prompt_injection_detected': metadata.prompt_injection_detected,
        }

    @app.patch('/api/reports/{report_id}/review')
    def review_report(
        report_id: str,
        payload: ReviewUpdateRequest,
        patient_id: str = Depends(authorized),
    ):
        get_report(report_id, patient_id)
        updated_holder: dict[str, object] = {}

        def mutate(current: Database) -> None:
            rep = current.reports.get(report_id)
            if rep is None or rep.patient_id != patient_id:
                raise HTTPException(404, 'Report not found.')
            if rep.name_mismatch_warning and not rep.name_mismatch_confirmed and not payload.confirm_name_mismatch:
                raise HTTPException(
                    422,
                    'Confirm that this report belongs to your profile because the printed patient name differs.',
                )

            existing_ids = [m.id for m in rep.measurements]
            incoming_ids = [m.id for m in payload.measurements]
            if existing_ids != incoming_ids:
                raise HTTPException(422, 'Review measurements must match the extracted report rows.')

            now = datetime.now(timezone.utc)
            by_id = {m.id: m for m in rep.measurements}
            for edit in payload.measurements:
                orig = by_id[edit.id]
                changed = (
                    edit.test != orig.test
                    or edit.value != orig.value
                    or edit.unit != orig.unit
                )
                if changed:
                    if orig.original_test is None:
                        orig.original_test = orig.test
                    if orig.original_value is None:
                        orig.original_value = orig.value
                    if orig.original_unit is None:
                        orig.original_unit = orig.unit
                    orig.test = edit.test
                    orig.value = edit.value
                    orig.unit = edit.unit
                    orig.user_corrected = True
                    orig.corrected_at = now
                    orig.issue = None
                orig.uncertain = False

            if 'age_at_report' in payload.model_fields_set:
                rep.age_at_report = payload.age_at_report
            if 'sex_at_report' in payload.model_fields_set and payload.sex_at_report is not None:
                rep.sex_at_report = payload.sex_at_report
            rep.demographics_overridden = (
                rep.age_at_report != rep.original_age_at_report
                or rep.sex_at_report != rep.original_sex_at_report
            )

            if payload.confirm_name_mismatch or rep.name_mismatch_warning is None:
                rep.name_mismatch_confirmed = True
            rep.review_status = 'ready'
            rep.reviewed_at = now

            new_analysis = analyze(rep, current)
            current.reports[report_id] = rep
            current.analysis_results[report_id] = new_analysis
            updated_holder['report'] = rep
            updated_holder['analysis'] = new_analysis

        updated_db = repo.update(mutate)
        rep_out: Report = updated_holder['report']  # type: ignore[assignment]
        ana_out: Analysis = updated_holder['analysis']  # type: ignore[assignment]
        return _build_detail_payload(updated_db, rep_out, ana_out)

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

    @app.post('/api/reports/{report_id}/analyze')
    async def analyze_report_by_id(report_id: str, patient_id: str = Depends(authorized)):
        return await analyze_report(AnalyzeRequest(report_id=report_id), patient_id)

    @app.get('/api/reports/{report_id}')
    def report_detail(report_id: str, patient_id: str = Depends(authorized)):
        db, report = get_report(report_id, patient_id)
        analysis = current_analysis(db, report)
        return _build_detail_payload(db, report, analysis)

    @app.get('/api/reports/{report_id}/results')
    def report_results(report_id: str, patient_id: str = Depends(authorized)):
        db, report = get_report(report_id, patient_id)
        return current_analysis(db, report)

    @app.get('/api/reports/{report_id}/source')
    def report_source(report_id: str, patient_id: str = Depends(authorized)):
        _, report = get_report(report_id, patient_id)
        if not report.stored_filename:
            raise HTTPException(404, 'Original source document is not available for this report.')
        try:
            source_path = repo.read_upload_file(report.stored_filename, patient_id)
        except FileNotFoundError:
            raise HTTPException(404, 'Original source document could not be found.') from None
        safe_name = re.sub(r'[^A-Za-z0-9._-]', '_', report.source_file or f'{report.id}')
        return Response(
            source_path.read_bytes(),
            media_type=report.source_media_type or 'application/octet-stream',
            headers={
                'Content-Disposition': f'inline; filename="{safe_name}"',
                'Content-Security-Policy': "default-src 'none'; sandbox",
            },
        )

    @app.post('/api/reports/{report_id}/chat')
    async def chat(report_id: str, payload: ChatRequest, patient_id: str = Depends(authorized)):
        db, report = get_report(report_id, patient_id)
        analysis = current_analysis(db, report)
        try:
            return await answer(
                payload.question,
                analysis,
                adapter,
                db=db,
                report=report,
                active_measurement_ids=payload.active_measurement_ids,
                context_revision=payload.context_revision,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

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
            rep.demographics_overridden = (
                payload.age_at_report != rep.original_age_at_report
                or payload.sex_at_report != rep.original_sex_at_report
            )
            filtered_issues = [
                i
                for i in rep.issues
                if not i.startswith('Demographics updated via session:')
                and not i.startswith('Demographics reset via session:')
                and not i.startswith('User-supplied demographics:')
            ]
            orig_age_txt = str(rep.original_age_at_report) if rep.original_age_at_report is not None else 'missing'
            if payload.age_at_report is None and payload.sex_at_report == 'unknown':
                filtered_issues.append(
                    f'Demographics reset via session (restored to age omitted, sex unknown; original source: age={orig_age_txt}, sex={rep.original_sex_at_report}).'
                )
            else:
                age_txt = str(payload.age_at_report) if payload.age_at_report is not None else 'missing'
                filtered_issues.append(
                    f'User-supplied demographics: age={age_txt}, sex={payload.sex_at_report} (original source: age={orig_age_txt}, sex={rep.original_sex_at_report}).'
                )
            rep.issues = filtered_issues
            new_analysis = analyze(rep, current)
            current.reports[report_id] = rep
            current.analysis_results[report_id] = new_analysis
            updated_holder['report'] = rep
            updated_holder['analysis'] = new_analysis

        updated_db = repo.update(mutate)
        rep_out: Report = updated_holder['report']  # type: ignore[assignment]
        ana_out: Analysis = updated_holder['analysis']  # type: ignore[assignment]
        return _build_detail_payload(updated_db, rep_out, ana_out)

    frontend_dist = Path(__file__).resolve().parent.parent.parent / 'frontend' / 'dist'
    if (frontend_dist / 'index.html').is_file() and (frontend_dist / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=str(frontend_dist / 'assets')), name='frontend-assets')

        @app.get('/{full_path:path}', include_in_schema=False)
        def serve_spa(full_path: str):
            norm = full_path.lstrip('/')
            if (
                norm == 'api'
                or norm.startswith('api/')
                or norm == 'uploads'
                or norm.startswith('uploads/')
                or norm == 'data'
                or norm.startswith('data/')
            ):
                raise HTTPException(404, 'Endpoint not found.')
            return FileResponse(frontend_dist / 'index.html')

    app.state.repo = repo
    return app


app = create_app()
