"""Conservative report extraction with noise filtering, prompt-injection defense, optional local OCR, and source coordinates."""
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from .models import Evidence, Measurement, Patient, Report, ReportMetadata
from .storage import _reject_duplicate_keys

MAX_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_DIMENSION = 10_000
SUPPORTED = {'.txt', '.md', '.csv', '.json', '.pdf', '.png', '.jpg', '.jpeg'}
MEDIA_TYPES = {
    '.txt': 'text/plain; charset=utf-8',
    '.md': 'text/markdown; charset=utf-8',
    '.csv': 'text/csv; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.pdf': 'application/pdf',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
}

# Optional test hook for simulating local OCR availability and output deterministically.
OCR_RUNNER: Callable[[bytes, str], str] | None = None

INJECTION_PATTERNS = (
    re.compile(r'ignore\s+(all\s+)?(previous|prior|above)\s+instructions', re.I),
    re.compile(r'system\s+(override|prompt)', re.I),
    re.compile(r'mark\s+(every|all)\s+tests?\s+normal', re.I),
    re.compile(r'output\s+diagnosis\s*=', re.I),
    re.compile(r'do\s+not\s+flag\s+any\s+(abnormal|urgent)', re.I),
    re.compile(r'override\s+classification', re.I),
)


class ExtractionError(ValueError):
    pass


TEST_COL_ALIASES = ('test', 'test name', 'analyte', 'parameter', 'investigation', 'component', 'assay')
VALUE_COL_ALIASES = ('value', 'result', 'measured value', 'observed value', 'reading', 'finding')
UNIT_COL_ALIASES = ('unit', 'units', 'measurement unit', 'uom')

NON_RESULT_PREFIXES = (
    'invoice',
    'total',
    'subtotal',
    'amount',
    'balance',
    'tax',
    'fee',
    'phone',
    'tel',
    'fax',
    'page ',
    'patient id',
    'patient name',
    'report date',
    'collection date',
    'printed',
    'accession',
    'specimen',
    'billing',
    'hospital',
    'clinic',
    'doctor',
    'dr.',
    'address',
)

METADATA_KEY_MAP = {
    'patient id': 'patient id',
    'patient_id': 'patient id',
    'patientid': 'patient id',
    'mrn': 'patient id',
    'patient name': 'patient name',
    'name': 'patient name',
    'report date': 'report date',
    'collection date': 'report date',
    'date': 'report date',
    'age': 'age',
    'sex': 'sex',
    'gender': 'sex',
    'provenance': 'provenance',
    'report status': 'report status',
}


def find_tesseract_binary() -> str | None:
    configured = os.getenv('TESSERACT_CMD', '').strip()
    if configured and Path(configured).is_file():
        return configured
    which_hit = shutil.which('tesseract')
    if which_hit:
        return which_hit
    for candidate in (
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        os.path.expanduser(r'~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'),
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def ocr_available() -> bool:
    return OCR_RUNNER is not None or find_tesseract_binary() is not None


def _normalize_sex(raw: str | None) -> str:
    val = (raw or '').strip().casefold()
    if val in {'m', 'male'}:
        return 'male'
    if val in {'f', 'female'}:
        return 'female'
    if val in {'', 'unknown', 'not provided', 'n/a', 'na', 'none', 'unspecified'}:
        return 'unknown'
    return val


def _normalize_age(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    val = raw.strip()
    if val.casefold() in {'not provided', 'n/a', 'na', 'none', 'unknown', 'missing'}:
        return None
    m = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:years?|yrs?|y)?', val, re.I)
    return m.group(1) if m else val


def _normalize_report_date(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    val = raw.strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', val):
        return val
    for fmt in ('%Y/%m/%d', '%d-%b-%Y', '%d %b %Y', '%b %d, %Y', '%B %d, %Y'):
        try:
            return datetime.strptime(val, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return val


def _find_col(normalized: list[str], candidates: tuple[str, ...]) -> int | None:
    for cand in candidates:
        if cand in normalized:
            return normalized.index(cand)
    return None


def _is_prompt_injection(line: str) -> bool:
    return any(pattern.search(line) for pattern in INJECTION_PATTERNS)


def _validate_image_bytes(content: bytes, suffix: str) -> None:
    if suffix == '.png' and not content.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ExtractionError('Invalid PNG image file.')
    if suffix in {'.jpg', '.jpeg'} and not content.startswith(b'\xff\xd8\xff'):
        raise ExtractionError('Invalid JPEG image file.')
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
        with Image.open(io.BytesIO(content)) as img:
            width, height = img.size
            fmt = (img.format or '').upper()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise ExtractionError('Uploaded image file is unreadable or exceeds pixel limits.') from exc

    expected_fmt = 'PNG' if suffix == '.png' else 'JPEG'
    if fmt != expected_fmt:
        raise ExtractionError('Image content does not match the declared file extension.')
    if width < 1 or height < 1 or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise ExtractionError('Image dimensions exceed supported security limits.')


def _run_ocr_on_image(content: bytes, suffix: str) -> str:
    clean_suffix = '.png' if suffix == '.png' else '.jpg'
    _validate_image_bytes(content, clean_suffix)

    if OCR_RUNNER is not None:
        return OCR_RUNNER(content, clean_suffix)

    binary = find_tesseract_binary()
    if not binary:
        raise ExtractionError(
            'Could not read this image report because local Tesseract OCR is not installed on this server. '
            'Upload a text-based PDF, CSV, TXT, or Markdown report instead.'
        )

    temp_path = None
    try:
        fd, temp_path = tempfile.mkstemp(prefix='citylab-ocr-', suffix=clean_suffix)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(content)
        proc = subprocess.run(
            [binary, temp_path, 'stdout', '--oem', '1', '-l', 'eng'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=20,
            check=True,
        )
        return proc.stdout
    except (subprocess.SubprocessError, OSError) as exc:
        raise ExtractionError(
            'Local OCR failed to read this image. Upload a clearer image or a text-based PDF/CSV.'
        ) from exc
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def _extract_lines(content: bytes, filename: str) -> tuple[list[tuple[str, str]], bool]:
    suffix = Path(filename).suffix.lower()
    if suffix in {'.png', '.jpg', '.jpeg'}:
        text = _run_ocr_on_image(content, suffix)
        lines = [(f'ocr line {i}', line) for i, line in enumerate(text.splitlines(), 1)]
        if not any(line.strip() for _, line in lines):
            raise ExtractionError('OCR did not detect any readable text in the uploaded image.')
        return lines, True

    if suffix == '.pdf':
        if not content.startswith(b'%PDF-'):
            raise ExtractionError('PDF file signature is invalid. Upload a valid text-based PDF.')
        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > 100:
                raise ExtractionError('Encrypted PDFs and PDFs over 100 pages are unsupported.')
            total = 0
            lines: list[tuple[str, str]] = []
            for page_num, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ''
                total += len(text)
                if total > 4_000_000:
                    raise ExtractionError('Extracted PDF text exceeds the supported size.')
                lines.extend((f'page {page_num}, line {i}', line) for i, line in enumerate(text.splitlines(), 1))

            non_ws = sum(len(line.strip()) for _, line in lines)
            if non_ws >= 10:
                return lines, False

            # Scanned/image-only PDF fallback via optional local OCR
            if ocr_available():
                ocr_lines: list[tuple[str, str]] = []
                img_count = 0
                for page_num, page in enumerate(reader.pages, 1):
                    for img in getattr(page, 'images', []):
                        img_bytes = getattr(img, 'data', b'')
                        img_name = str(getattr(img, 'name', 'page.png'))
                        img_suffix = Path(img_name).suffix.lower()
                        if img_suffix not in {'.png', '.jpg', '.jpeg'}:
                            img_suffix = '.png' if img_bytes.startswith(b'\x89PNG') else '.jpg'
                        img_count += 1
                        if img_count > 20:
                            break
                        if not img_bytes:
                            continue
                        ocr_text = _run_ocr_on_image(img_bytes, img_suffix)
                        ocr_lines.extend(
                            (f'page {page_num}, ocr line {i}', line)
                            for i, line in enumerate(ocr_text.splitlines(), 1)
                        )
                if any(line.strip() for _, line in ocr_lines):
                    return ocr_lines, True

            raise ExtractionError(
                'This PDF appears to be a scanned image without selectable text, and local Tesseract OCR is not available. '
                'Upload a text-based PDF, CSV, TXT, or Markdown report instead.'
            )
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError('PDF could not be read. Use a text-based PDF or export as CSV.') from exc

    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ExtractionError('Text documents must use UTF-8 encoding.') from exc
    return [(f'line {i}', line) for i, line in enumerate(text.splitlines(), 1)], False


def _parse_table_row(text: str, in_table: bool = False) -> list[str] | None:
    if '|' in text:
        return [x.strip() for x in text.strip('|').split('|')]
    if ',' in text:
        cells = next(csv.reader([text]))
        if len(cells) >= 3 and all(len(c.strip()) <= 160 for c in cells):
            return [x.strip() for x in cells]
        if in_table and len(cells) >= 2 and len(text) <= 120 and not text.endswith('.'):
            return [x.strip() for x in cells]
        return None
    if '\t' in text:
        return [x.strip() for x in text.split('\t')]
    if re.search(r'\s{2,}', text):
        parts = [p.strip() for p in re.split(r'\s{2,}', text.strip()) if p.strip()]
        if len(parts) >= 3:
            return parts
    header_match = re.fullmatch(
        r'(Test(?:\s+Name)?|Analyte|Parameter|Investigation|Component|Assay)\s+'
        r'(Value|Result|Measured\s+Value|Observed\s+Value|Reading|Finding)'
        r'(?:\s+(Unit|Units|Measurement\s+Unit|UOM))?'
        r'(?:\s+(?:Reference(?:\s+(?:Range|Interval))?|Normal\s+Range|Flag|Status|Notes?))*',
        text.strip(),
        re.I,
    )
    if header_match:
        cols = [header_match.group(1), header_match.group(2)]
        if header_match.group(3):
            cols.append(header_match.group(3))
        return cols
    if in_table:
        low = text.casefold()
        if any(low.startswith(prefix) for prefix in NON_RESULT_PREFIXES):
            return None
        match = re.fullmatch(
            r'([A-Za-z][A-Za-z0-9\s\(\)/+_-]{1,60}?)\s+([<>]?\d+(?:\.\d+)?)\s+([A-Za-z%/\^0-9\xb5\u03bc._-]+)(?:\s+(?:\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?|\[.*|\(.*))?',
            text.strip(),
        )
        if match:
            return [match.group(1).strip(), match.group(2).strip(), match.group(3).strip()]
    return None


def extract_report(
    content: bytes,
    filename: str,
    authorized_patient: str | None = None,
    synthetic: bool | None = False,
    authenticated_patient_name: str | None = None,
    strict_patient_id: bool = True,
) -> tuple[Report, ReportMetadata, Patient | None]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED or not content or len(content) > MAX_BYTES:
        raise ExtractionError('Use a nonempty PDF, PNG, JPG, TXT, MD, CSV, or JSON file no larger than 8 MiB.')

    digest = hashlib.sha256(content).hexdigest()
    clean_name = Path(filename.replace('\\', '/')).name[:200]

    if suffix == '.json':
        try:
            raw_obj = json.loads(content.decode('utf-8-sig'), object_pairs_hook=_reject_duplicate_keys)
            report = Report.model_validate(raw_obj)
        except Exception as exc:
            raise ExtractionError('JSON does not match the documented report schema.') from exc
        printed_id = report.patient_id
        target_patient = authorized_patient or report.patient_id
        if strict_patient_id and authorized_patient is not None and printed_id != authorized_patient:
            raise ExtractionError('Report patient does not match the authorized session.')
        issues = list(report.issues)
        if authorized_patient is not None and printed_id and printed_id != authorized_patient:
            issues.append(f'Printed patient ID "{printed_id}" recorded as source metadata; report bound to authenticated profile.')
        report.patient_id = target_patient
        for index, m in enumerate(report.measurements):
            m.evidence = Evidence(
                file=clean_name,
                location=f'measurements[{index}]',
                excerpt=f'{m.test} | {m.value} | {m.unit}',
            )
            m.original_test = m.test
            m.original_value = m.value
            m.original_unit = m.unit
            m.user_corrected = False
            m.corrected_at = None
        report.id = 'r-' + hashlib.sha256((target_patient + digest).encode()).hexdigest()[:24]
        report.title = clean_name
        report.source_file = clean_name
        report.source_hash = digest
        report.synthetic = bool(synthetic) if synthetic is not None else False
        report.original_age_at_report = report.age_at_report
        report.original_sex_at_report = report.sex_at_report
        report.demographics_overridden = False
        report.printed_patient_id = printed_id or None
        report.issues = issues
        report.review_status = 'needs_review' if issues else 'ready'
        metadata = ReportMetadata(
            report_id=report.id,
            patient_id=target_patient,
            source_file=clean_name,
            source_hash=digest,
            line_count=len(report.measurements),
            noise_lines_skipped=0,
            prompt_injection_detected=False,
            extraction_issues=list(issues),
        )
        return report, metadata, None

    lines, used_ocr = _extract_lines(content, clean_name)
    metadata_fields: dict[str, str] = {}
    issues: list[str] = []
    if used_ocr:
        issues.append('Text extracted using local OCR; please review values and units before saving.')
    measurements: list[Measurement] = []
    header: tuple[int, int, int | None] | None = None
    noise_lines_skipped = 0
    prompt_injection_detected = False

    for location, raw in lines:
        text = raw.strip()
        if not text:
            noise_lines_skipped += 1
            continue

        if _is_prompt_injection(text):
            prompt_injection_detected = True
            issues.append(f'{location}: untrusted prompt-injection text neutralized and ignored')
            noise_lines_skipped += 1
            continue

        meta = re.fullmatch(
            r'(Patient\s*ID|Patient_ID|PatientID|MRN|Patient\s*Name|Name|Report\s*Date|Collection\s*Date|Date|Age|Sex|Gender|Provenance|Report\s*Status)\s*:\s*(.*?)\s*',
            text,
            re.I,
        )
        if meta:
            raw_key = ' '.join(meta.group(1).casefold().split())
            key = METADATA_KEY_MAP[raw_key]
            value = meta.group(2)
            if key in metadata_fields and metadata_fields[key] != value:
                raise ExtractionError('Conflicting patient or report metadata. Split documents into individual reports.')
            metadata_fields[key] = value
            continue

        if len(text) > 6000:
            issues.append(f'{location}: long non-tabular line skipped')
            noise_lines_skipped += 1
            continue

        cells = _parse_table_row(text, in_table=(header is not None))
        if cells is None:
            noise_lines_skipped += 1
            continue

        normalized = [' '.join(c.casefold().split()) for c in cells]
        test_idx = _find_col(normalized, TEST_COL_ALIASES)
        val_idx = _find_col(normalized, VALUE_COL_ALIASES)
        unit_idx = _find_col(normalized, UNIT_COL_ALIASES)
        if test_idx is not None and val_idx is not None:
            header = (test_idx, val_idx, unit_idx)
            continue

        if not header or all(re.fullmatch(r'[:\-\s]*', c) for c in cells):
            noise_lines_skipped += 1
            continue

        required_cols = [i for i in header if i is not None]
        if len(cells) <= max(required_cols):
            issues.append(f'{location}: malformed table row skipped')
            continue

        name = cells[header[0]]
        value = cells[header[1]]
        unit = cells[header[2]] if header[2] is not None else ''
        if not name:
            issues.append(f'{location}: unnamed result skipped')
            continue
        if len(name) > 160 or len(value) > 80 or len(unit) > 80:
            issues.append(f'{location}: oversized table row skipped')
            continue

        uncertain = used_ocr or not unit or not re.fullmatch(r'-?\d+(?:\.\d+)?', value.strip())
        measurements.append(
            Measurement(
                id=f'm{len(measurements) + 1}',
                test=name,
                value=value,
                unit=unit,
                evidence=Evidence(file=clean_name, location=location, excerpt=text),
                original_test=name,
                original_value=value,
                original_unit=unit,
                user_corrected=False,
                uncertain=uncertain,
            )
        )
        if len(measurements) > 500:
            raise ExtractionError('A report may contain at most 500 measurements.')

    printed_id = metadata_fields.get('patient id')
    if strict_patient_id:
        if authorized_patient is not None:
            if printed_id != authorized_patient:
                raise ExtractionError('A unique Patient ID matching the authorized session is required.')
        elif not printed_id:
            raise ExtractionError('Patient ID metadata line is required in corpus reports.')
        patient_id = printed_id  # type: ignore[assignment]
    else:
        patient_id = authorized_patient or printed_id
        if not patient_id:
            raise ExtractionError('An authenticated patient session is required.')
        if printed_id and authorized_patient and printed_id != authorized_patient:
            issues.append(
                f'Printed patient ID "{printed_id}" recorded as source metadata; report bound to authenticated profile.'
            )

    if not measurements:
        raise ExtractionError(
            'No supported result table found. Use columns Test, Value, Unit. '
            'Check the uploaded file format or enter values manually.'
        )

    report_id = 'r-' + hashlib.sha256((patient_id + digest).encode()).hexdigest()[:24]
    sex_raw = _normalize_sex(metadata_fields.get('sex'))
    age_raw = _normalize_age(metadata_fields.get('age'))
    date_raw = _normalize_report_date(metadata_fields.get('report date'))

    printed_name = (metadata_fields.get('patient name') or '').strip() or None
    name_mismatch_warning: str | None = None
    if (
        printed_name
        and authenticated_patient_name
        and ' '.join(printed_name.casefold().split()) != ' '.join(authenticated_patient_name.casefold().split())
    ):
        name_mismatch_warning = (
            f'The uploaded report lists patient name "{printed_name}", which differs from your profile name '
            f'"{authenticated_patient_name}". Confirm before saving to this workspace.'
        )
        issues.append(name_mismatch_warning)

    declares_synthetic = (
        'synthetic' in metadata_fields.get('provenance', '').casefold()
        or 'synthetic' in metadata_fields.get('report status', '').casefold()
    )
    is_synthetic = bool(synthetic) if synthetic is not None else declares_synthetic
    needs_review = bool(used_ocr or name_mismatch_warning or issues or any(m.uncertain for m in measurements))

    try:
        report = Report(
            id=report_id,
            patient_id=patient_id,
            title=clean_name,
            report_date=date_raw,
            age_at_report=age_raw,
            sex_at_report=sex_raw,
            original_age_at_report=age_raw,
            original_sex_at_report=sex_raw,
            demographics_overridden=False,
            review_status='needs_review' if needs_review else 'ready',
            printed_patient_name=printed_name,
            printed_patient_id=printed_id or None,
            name_mismatch_warning=name_mismatch_warning,
            name_mismatch_confirmed=(name_mismatch_warning is None),
            measurements=measurements,
            issues=issues,
            source_file=clean_name,
            source_hash=digest,
            synthetic=is_synthetic,
        )
        patient_record = (
            Patient(
                id=patient_id,
                name=printed_name,
                age=report.age_at_report,
                sex=report.sex_at_report,
            )
            if printed_name
            else None
        )
    except Exception as exc:
        raise ExtractionError(
            'Invalid demographics or report date. Use numeric age, male/female/unknown, and YYYY-MM-DD.'
        ) from exc

    meta_record = ReportMetadata(
        report_id=report.id,
        patient_id=patient_id,
        source_file=clean_name,
        source_hash=digest,
        line_count=len(lines),
        noise_lines_skipped=noise_lines_skipped,
        prompt_injection_detected=prompt_injection_detected,
        extraction_issues=list(issues),
    )
    return report, meta_record, patient_record


def inventory(folder: Path) -> list[dict]:
    """Record every corpus file without treating any of its contents as instructions."""
    records = []
    for path in sorted(folder.rglob('*')):
        if not path.is_file() or path.name.startswith('.'):
            continue
        data = path.read_bytes()
        records.append(
            {
                'file': str(path.relative_to(folder)),
                'bytes': len(data),
                'sha256': hashlib.sha256(data).hexdigest(),
                'supported': path.suffix.lower() in SUPPORTED,
            }
        )
    return records
