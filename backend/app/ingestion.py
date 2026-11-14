"""Conservative report extraction with noise filtering, prompt-injection defense, and source coordinates."""
import csv
import hashlib
import io
import re
from pathlib import Path
from pypdf import PdfReader
from .models import Evidence, Measurement, Patient, Report, ReportMetadata

MAX_BYTES = 8 * 1024 * 1024
SUPPORTED = {'.txt', '.md', '.csv', '.json', '.pdf'}

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


TEST_COL_ALIASES = ('test', 'test name', 'analyte', 'parameter', 'investigation', 'component')
VALUE_COL_ALIASES = ('value', 'result', 'measured value', 'observed value', 'reading')
UNIT_COL_ALIASES = ('unit', 'units', 'measurement unit')

METADATA_KEY_MAP = {
    'patient id': 'patient id',
    'patient_id': 'patient id',
    'patientid': 'patient id',
    'patient name': 'patient name',
    'name': 'patient name',
    'report date': 'report date',
    'collection date': 'report date',
    'date': 'report date',
    'age': 'age',
    'sex': 'sex',
    'gender': 'sex',
}


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


def _find_col(normalized: list[str], candidates: tuple[str, ...]) -> int | None:
    for cand in candidates:
        if cand in normalized:
            return normalized.index(cand)
    return None


def _is_prompt_injection(line: str) -> bool:
    return any(pattern.search(line) for pattern in INJECTION_PATTERNS)


def _extract_lines(content: bytes, filename: str) -> list[tuple[str, str]]:
    suffix = Path(filename).suffix.lower()
    if suffix == '.pdf':
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
            return lines
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError('PDF could not be read. Use a text-based PDF or export as CSV.') from exc
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ExtractionError('Text documents must use UTF-8 encoding.') from exc
    return [(f'line {i}', line) for i, line in enumerate(text.splitlines(), 1)]


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
    return None


def extract_report(
    content: bytes,
    filename: str,
    authorized_patient: str | None = None,
) -> tuple[Report, ReportMetadata, Patient | None]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED or not content or len(content) > MAX_BYTES:
        raise ExtractionError('Use a nonempty TXT, MD, CSV, JSON, or text PDF file no larger than 8 MiB.')

    digest = hashlib.sha256(content).hexdigest()
    clean_name = Path(filename.replace('\\', '/')).name[:200]

    if suffix == '.json':
        try:
            report = Report.model_validate_json(content)
        except Exception as exc:
            raise ExtractionError('JSON does not match the documented report schema.') from exc
        target_patient = authorized_patient or report.patient_id
        if report.patient_id != target_patient:
            raise ExtractionError('Report patient does not match the authorized session.')
        for index, m in enumerate(report.measurements):
            m.evidence = Evidence(
                file=clean_name,
                location=f'measurements[{index}]',
                excerpt=f'{m.test} | {m.value} | {m.unit}',
            )
        report.id = 'r-' + hashlib.sha256((target_patient + digest).encode()).hexdigest()[:24]
        report.source_file = clean_name
        report.source_hash = digest
        report.synthetic = False
        metadata = ReportMetadata(
            report_id=report.id,
            patient_id=target_patient,
            source_file=clean_name,
            source_hash=digest,
            line_count=len(report.measurements),
            noise_lines_skipped=0,
            prompt_injection_detected=False,
            extraction_issues=list(report.issues),
        )
        return report, metadata, None

    lines = _extract_lines(content, clean_name)
    metadata_fields: dict[str, str] = {}
    issues: list[str] = []
    measurements: list[Measurement] = []
    header: tuple[int, int, int] | None = None
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
            r'(Patient\s*ID|Patient_ID|PatientID|Patient\s*Name|Name|Report\s*Date|Collection\s*Date|Date|Age|Sex|Gender)\s*:\s*(.*?)\s*',
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
        if test_idx is not None and val_idx is not None and unit_idx is not None:
            header = (test_idx, val_idx, unit_idx)
            continue

        if not header or all(re.fullmatch(r'[:\-\s]*', c) for c in cells):
            noise_lines_skipped += 1
            continue

        if len(cells) <= max(header):
            issues.append(f'{location}: malformed table row skipped')
            continue

        name, value, unit = (cells[i] for i in header)
        if not name:
            issues.append(f'{location}: unnamed result skipped')
            continue
        if len(name) > 160 or len(value) > 80 or len(unit) > 80:
            issues.append(f'{location}: oversized table row skipped')
            continue

        measurements.append(
            Measurement(
                id=f'm{len(measurements) + 1}',
                test=name,
                value=value,
                unit=unit,
                evidence=Evidence(file=clean_name, location=location, excerpt=text),
            )
        )
        if len(measurements) > 500:
            raise ExtractionError('A report may contain at most 500 measurements.')

    patient_id = metadata_fields.get('patient id')
    if authorized_patient is not None:
        if patient_id != authorized_patient:
            raise ExtractionError('A unique Patient ID matching the authorized session is required.')
    elif not patient_id:
        raise ExtractionError('Patient ID metadata line is required in corpus reports.')

    if not measurements:
        raise ExtractionError(
            'No supported result table found. Use columns Test, Value, Unit. '
            'Scanned PDFs need manual transcription; OCR is not enabled.'
        )

    report_id = 'r-' + hashlib.sha256((patient_id + digest).encode()).hexdigest()[:24]
    sex_raw = _normalize_sex(metadata_fields.get('sex'))
    age_raw = _normalize_age(metadata_fields.get('age'))
    date_raw = metadata_fields.get('report date') or None

    try:
        report = Report(
            id=report_id,
            patient_id=patient_id,
            report_date=date_raw,
            age_at_report=age_raw,
            sex_at_report=sex_raw,
            measurements=measurements,
            issues=issues,
            source_file=clean_name,
            source_hash=digest,
            synthetic=False,
        )
        patient_name = metadata_fields.get('patient name')
        patient_record = (
            Patient(
                id=patient_id,
                name=patient_name,
                age=report.age_at_report,
                sex=report.sex_at_report,
            )
            if patient_name
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
