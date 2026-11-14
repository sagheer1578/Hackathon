from io import BytesIO
import json
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
import pytest
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from backend.app import ingestion
from backend.app.main import create_app
from backend.app.storage import CANONICAL_FILENAME, StorageError


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _make_text_pdf(lines: list[str]) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf)
    y = 760
    for line in lines:
        c.drawString(50, y, line)
        y -= 18
    c.showPage()
    c.save()
    return buf.getvalue()


def _make_scanned_image_pdf() -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf)
    c.drawImage(ImageReader(BytesIO(_make_jpg_bytes())), 50, 600, width=120, height=40)
    c.showPage()
    c.save()
    return buf.getvalue()


def _make_png_bytes() -> bytes:
    buf = BytesIO()
    img = Image.new('RGB', (120, 40), color=(255, 255, 255))
    img.save(buf, format='PNG')
    return buf.getvalue()


def _make_jpg_bytes() -> bytes:
    buf = BytesIO()
    img = Image.new('RGB', (120, 40), color=(255, 255, 255))
    img.save(buf, format='JPEG')
    return buf.getvalue()


@pytest.fixture
def personal_env(tmp_path):
    corpus_dir = Path(__file__).resolve().parent.parent / 'corpus'
    data_dir = tmp_path / 'data'
    app = create_app(data_dir=data_dir, corpus_dir=corpus_dir, demo_mode=True)
    with TestClient(app) as client:
        yield client, data_dir, corpus_dir


def test_profile_registration_entropy_validation_and_unicode(personal_env):
    client, data_dir, _ = personal_env

    # Empty, whitespace-only, or control-character names must be rejected
    for bad_name in ['', '   ', 'Alice\x00Bob', 'Test\nUser']:
        resp = client.post('/api/auth/register', json={'name': bad_name})
        assert resp.status_code == 422

    # Unicode, apostrophe, and hyphenated names accepted and normalized cleanly
    r1 = client.post('/api/auth/register', json={'name': "  Zoë O'Connor-Müller  "})
    r2 = client.post('/api/auth/register', json={'name': 'طارق الأحمد'})
    assert r1.status_code == 201 and r2.status_code == 201
    b1, b2 = r1.json(), r2.json()
    assert b1['profile']['name'] == "Zoë O'Connor-Müller"
    assert b1['profile']['profile_type'] == 'personal'
    assert b2['profile']['name'] == 'طارق الأحمد'
    assert b1['access_code'].startswith('CLD-')
    alnum = b1['access_code'].replace('-', '')
    assert len(alnum) >= 20
    assert b1['access_code'] != b2['access_code']

    # Duplicate names receive independent IDs and distinct non-derived access codes
    d1 = client.post('/api/auth/register', json={'name': 'Samir Patel'}).json()
    d2 = client.post('/api/auth/register', json={'name': 'Samir Patel'}).json()
    assert d1['profile']['id'] != d2['profile']['id']
    assert d1['access_code'] != d2['access_code']
    assert d1['session_token'] != d2['session_token']

    # Raw access codes and session tokens must never appear in database.json
    raw_db = (data_dir / CANONICAL_FILENAME).read_text(encoding='utf-8')
    for payload in (b1, b2, d1, d2):
        assert payload['access_code'] not in raw_db
        assert payload['session_token'] not in raw_db

    # Demo list never exposes personal profiles
    demos = client.get('/api/demo/sessions').json()
    demo_ids = {p['patient_id'] for p in demos['personas']}
    assert b1['profile']['id'] not in demo_ids
    assert b2['profile']['id'] not in demo_ids


def test_profile_login_logout_restart_persistence_and_empty_reports(tmp_path):
    corpus_dir = Path(__file__).resolve().parent.parent / 'corpus'
    data_dir = tmp_path / 'persist_data'

    app1 = create_app(data_dir=data_dir, corpus_dir=corpus_dir, demo_mode=True)
    with TestClient(app1) as c1:
        reg = c1.post('/api/auth/register', json={'name': 'Nadia Rahman'}).json()
        code = reg['access_code']
        tok1 = reg['session_token']

        # Newly created profile has zero reports and synthetic_demo=False
        sess = c1.get('/api/session', headers=_auth(tok1))
        assert sess.status_code == 200
        assert sess.json()['synthetic_demo'] is False
        assert sess.json()['patient']['profile_type'] == 'personal'
        assert c1.get('/api/reports', headers=_auth(tok1)).json() == {'reports': []}

        # Auth me matches session
        assert c1.get('/api/auth/me', headers=_auth(tok1)).json()['patient']['id'] == reg['profile']['id']

        # Invalid access code returns generic 401 without user enumeration
        bad = c1.post('/api/auth/login', json={'access_code': 'CLD-WRONG-CODE-00000-00000-00000'})
        assert bad.status_code == 401
        assert "couldn’t find a profile" in bad.json()['detail'].lower()
        assert 'nadia' not in bad.text.lower()

        # Upload a report before restart
        up = c1.post(
            '/api/reports/upload',
            headers=_auth(tok1),
            files={'file': ('nadia_lab.txt', b'Patient Name: Nadia Rahman\nTest | Value | Unit\nALT | 38 | U/L', 'text/plain')},
        )
        assert up.status_code == 201
        rid = up.json()['report_id']

        # Logout revokes session token immediately
        out = c1.post('/api/auth/logout', headers=_auth(tok1))
        assert out.status_code == 200
        assert c1.get('/api/session', headers=_auth(tok1)).status_code == 401

    # Restart on the same data_dir: saved access code still works and preserves reports
    app2 = create_app(data_dir=data_dir, corpus_dir=corpus_dir, demo_mode=True)
    with TestClient(app2) as c2:
        relogin = c2.post('/api/auth/login', json={'access_code': code})
        assert relogin.status_code == 200
        tok2 = relogin.json()['session_token']
        assert tok2 != tok1
        listed = c2.get('/api/reports', headers=_auth(tok2)).json()['reports']
        assert [r['id'] for r in listed] == [rid]
        assert listed[0]['has_source_file'] is True


def test_text_pdf_image_ocr_and_error_handling(personal_env, monkeypatch):
    client, data_dir, _ = personal_env
    reg = client.post('/api/auth/register', json={'name': 'Farah Khan'}).json()
    tok = reg['session_token']
    pid = reg['profile']['id']

    # 1. Text-based PDF extraction + private storage + authenticated source serving
    pdf_bytes = _make_text_pdf([
        'CityLab Clinical Summary',
        'Patient Name: Farah Khan',
        'Test Value Unit',
        'ALT 32 U/L',
        'FBS 95 mg/dL',
    ])
    pdf_resp = client.post(
        '/api/reports/upload',
        headers=_auth(tok),
        files={'file': ('farah_panel.pdf', pdf_bytes, 'application/pdf')},
    )
    assert pdf_resp.status_code == 201
    pdf_rid = pdf_resp.json()['report_id']
    source_resp = client.get(f'/api/reports/{pdf_rid}/source', headers=_auth(tok))
    assert source_resp.status_code == 200
    assert source_resp.headers['content-type'] == 'application/pdf'
    assert source_resp.headers.get('content-security-policy') == "default-src 'none'; sandbox"
    assert source_resp.content == pdf_bytes
    assert (data_dir / 'uploads' / pid / f'{pdf_rid}.pdf').is_file()

    # Raw upload paths must not be statically exposed
    assert client.get(f'/uploads/{pid}/{pdf_rid}.pdf').status_code in (404, 405)
    assert client.get(f'/data/uploads/{pid}/{pdf_rid}.pdf').status_code in (404, 405)

    # 2. Image / scanned-PDF fail cleanly when OCR binary is unavailable
    monkeypatch.setattr(ingestion, 'OCR_RUNNER', None)
    monkeypatch.setattr(ingestion, 'find_tesseract_binary', lambda: None)
    no_ocr_png = client.post(
        '/api/reports/upload',
        headers=_auth(tok),
        files={'file': ('scan.png', _make_png_bytes(), 'image/png')},
    )
    assert no_ocr_png.status_code == 422
    assert 'ocr' in no_ocr_png.json()['detail'].lower()

    no_ocr_pdf = client.post(
        '/api/reports/upload',
        headers=_auth(tok),
        files={'file': ('blank_scan.pdf', _make_scanned_image_pdf(), 'application/pdf')},
    )
    assert no_ocr_pdf.status_code == 422
    assert 'ocr' in no_ocr_pdf.json()['detail'].lower()

    # 3. With OCR runner available, PNG, JPG, and scanned PDF extract results and flag uncertain / needs_review
    monkeypatch.setattr(
        ingestion,
        'OCR_RUNNER',
        lambda _raw, _suffix: 'Patient Name: Farah Khan\nTest | Value | Unit\nHemoglobin | 13.4 | g/dL\n',
    )
    png_ok = client.post(
        '/api/reports/upload',
        headers=_auth(tok),
        files={'file': ('photo_report.png', _make_png_bytes(), 'image/png')},
    )
    assert png_ok.status_code == 201
    assert png_ok.json()['review_status'] == 'needs_review'
    png_detail = client.get(f"/api/reports/{png_ok.json()['report_id']}", headers=_auth(tok)).json()
    assert png_detail['report']['measurements'][0]['uncertain'] is True

    jpg_ok = client.post(
        '/api/reports/upload',
        headers=_auth(tok),
        files={'file': ('photo_report.jpg', _make_jpg_bytes(), 'image/jpeg')},
    )
    assert jpg_ok.status_code == 201

    scanned_ok = client.post(
        '/api/reports/upload',
        headers=_auth(tok),
        files={'file': ('scanned_doc.pdf', _make_scanned_image_pdf(), 'application/pdf')},
    )
    assert scanned_ok.status_code == 201

    # 4. Reject invalid extension, empty file, corrupt PDF, corrupt image, and unparseable text cleanly
    for fname, body, mime in [
        ('payload.exe', b'MZ...', 'application/octet-stream'),
        ('empty.txt', b'', 'text/plain'),
        ('corrupt.pdf', b'%PDF-1.4\nbroken', 'application/pdf'),
        ('corrupt.png', b'not-a-png', 'image/png'),
        ('no_rows.txt', b'Hello this is not a lab table at all.\nNo numbers here.', 'text/plain'),
    ]:
        bad_up = client.post('/api/reports/upload', headers=_auth(tok), files={'file': (fname, body, mime)})
        assert bad_up.status_code == 422


def test_ownership_binding_name_mismatch_review_audit_and_cross_profile_isolation(personal_env):
    client, data_dir, _ = personal_env
    alice = client.post('/api/auth/register', json={'name': 'Alice Verma'}).json()
    bob = client.post('/api/auth/register', json={'name': 'Bob Menon'}).json()
    tok_a, tok_b = alice['session_token'], bob['session_token']

    # Path traversal filename + printed foreign patient-p001 ID + mismatched printed Patient Name
    malicious_content = (
        b'Patient ID: patient-p001\n'
        b'Patient Name: Someone Else Entirely\n'
        b'Test | Value | Unit\n'
        b'ALT | 42 | U/L\n'
    )
    up = client.post(
        '/api/reports/upload',
        headers=_auth(tok_a),
        files={'file': ('../../secret/evil_report.txt', malicious_content, 'text/plain')},
    )
    assert up.status_code == 201
    rid = up.json()['report_id']
    assert up.json()['review_status'] == 'needs_review'
    assert up.json()['name_mismatch_warning'] is not None

    detail_before = client.get(f'/api/reports/{rid}', headers=_auth(tok_a)).json()
    assert detail_before['report']['patient_id'] == alice['profile']['id']
    assert detail_before['report']['printed_patient_id'] == 'patient-p001'
    assert detail_before['report']['synthetic'] is False
    stored_path = (data_dir / 'uploads' / detail_before['report']['stored_filename']).resolve()
    assert str(stored_path).startswith(str((data_dir / 'uploads' / alice['profile']['id']).resolve()))
    assert '..' not in detail_before['report']['stored_filename']

    # Under synthetic demo rules, personal uploaded report must NOT be classified with synthetic thresholds
    assert detail_before['analysis']['results'][0]['status'] == 'Cannot Be Classified'
    assert 'Synthetic demonstration' in detail_before['analysis']['results'][0]['reason']

    # Review without confirming name mismatch is rejected
    old_rev = detail_before['analysis_revision']
    unconfirmed = client.patch(
        f'/api/reports/{rid}/review',
        headers=_auth(tok_a),
        json={
            'measurements': [{'id': 'm1', 'test': 'ALT', 'value': '42', 'unit': 'U/L'}],
            'confirm_name_mismatch': False,
        },
    )
    assert unconfirmed.status_code == 422

    # Confirming mismatch & correcting measurement updates audit trail, PDF, and revision
    confirmed = client.patch(
        f'/api/reports/{rid}/review',
        headers=_auth(tok_a),
        json={
            'measurements': [{'id': 'm1', 'test': 'ALT', 'value': '48', 'unit': 'U/L'}],
            'age_at_report': 29,
            'sex_at_report': 'female',
            'confirm_name_mismatch': True,
        },
    )
    assert confirmed.status_code == 200
    conf_json = confirmed.json()
    assert conf_json['report']['review_status'] == 'ready'
    assert conf_json['report']['name_mismatch_confirmed'] is True
    m1 = conf_json['report']['measurements'][0]
    assert m1['user_corrected'] is True
    assert m1['original_value'] == '42'
    assert m1['value'] == '48'
    assert any('User-corrected measurement' in a for a in conf_json['analysis']['results'][0]['audit'])
    assert conf_json['analysis_revision'] != old_rev

    # Stale revision sent to chat after edit asks clarification instead of answering on stale test context
    stale_chat = client.post(
        f'/api/reports/{rid}/chat',
        headers=_auth(tok_a),
        json={'question': 'Is it high?', 'active_measurement_ids': ['m1'], 'context_revision': old_rev},
    ).json()
    assert stale_chat['intent'] == 'clarification'

    # PDF includes User corrected marker and Original Report Date note
    pdf_dl = client.get(f'/api/reports/{rid}/download', headers=_auth(tok_a))
    assert pdf_dl.status_code == 200 and pdf_dl.content.startswith(b'%PDF-')
    from pypdf import PdfReader
    pdf_text = '\n'.join((p.extract_text() or '') for p in PdfReader(BytesIO(pdf_dl.content)).pages)
    assert 'User corrected' in pdf_text
    assert 'Not listed on document' in pdf_text

    # Cross-profile isolation: Profile B gets 404 across every endpoint
    for method, url, payload in [
        ('get', f'/api/reports/{rid}', None),
        ('get', f'/api/reports/{rid}/results', None),
        ('get', f'/api/reports/{rid}/source', None),
        ('get', f'/api/reports/{rid}/download', None),
        ('post', f'/api/reports/{rid}/chat', {'question': 'Explain ALT'}),
        ('post', f'/api/reports/{rid}/demographics', {'age_at_report': 30, 'sex_at_report': 'male'}),
        ('post', f'/api/reports/{rid}/analyze', None),
        ('patch', f'/api/reports/{rid}/review', {'measurements': [{'id': 'm1', 'test': 'ALT', 'value': '1', 'unit': 'U/L'}], 'confirm_name_mismatch': True}),
    ]:
        resp = getattr(client, method)(url, headers=_auth(tok_b), json=payload) if payload else getattr(client, method)(url, headers=_auth(tok_b))
        assert resp.status_code == 404


def test_upload_rollback_leaves_no_orphan_file_on_storage_error(personal_env, monkeypatch):
    client, data_dir, _ = personal_env
    reg = client.post('/api/auth/register', json={'name': 'Rollback Tester'}).json()
    tok = reg['session_token']
    pid = reg['profile']['id']
    uploads_subdir = data_dir / 'uploads' / pid
    assert not uploads_subdir.exists()

    orig_update = client.app.state.repo.update

    def boom(_fn):
        raise StorageError('Simulated write failure')

    monkeypatch.setattr(client.app.state.repo, 'update', boom)
    failed = client.post(
        '/api/reports/upload',
        headers=_auth(tok),
        files={'file': ('roll.txt', b'Test | Value | Unit\nALT | 25 | U/L', 'text/plain')},
    )
    assert failed.status_code == 503
    remaining = list(uploads_subdir.glob('*')) if uploads_subdir.exists() else []
    assert remaining == []
    monkeypatch.setattr(client.app.state.repo, 'update', orig_update)
