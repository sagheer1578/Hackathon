"""Structured corpus parser: reads CityLab markdown documents into the 9-file JSON store."""
import re
from decimal import Decimal
from pathlib import Path
from .ingestion import extract_report
from .models import (
    Conversion,
    Database,
    Evidence,
    GlossaryEntry,
    KnowledgeProvenance,
    Patient,
    ReferenceRange,
    SafetyRule,
    TestAliasRecord,
    UrgentThreshold,
)
from .storage import Repository


class CorpusParseError(ValueError):
    pass


def _norm(text: str) -> str:
    return ' '.join(text.casefold().split())


def _parse_bound_interval(token: str) -> tuple[Decimal | None, Decimal | None, bool, bool]:
    token = token.strip()
    if token.casefold() == 'all':
        return None, None, True, True
    match = re.fullmatch(r'([\[(])\s*([^,]+?)\s*,\s*([^\])]+?)\s*([\])])', token)
    if not match:
        raise CorpusParseError(f'Unsupported interval syntax: {token}')
    left_br, low_s, high_s, right_br = match.groups()
    low = None if low_s.casefold() in {'none', '-inf', '-infinity'} else Decimal(low_s)
    high = None if high_s.casefold() in {'none', 'inf', 'infinity'} else Decimal(high_s)
    return low, high, left_br == '[', right_br == ']'


def _split_md_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def _is_separator_row(cells: list[str]) -> bool:
    return all(re.fullmatch(r'[:\-\s]+', c) or c == '' for c in cells)


def _parse_safety_rules(path: Path) -> dict[str, SafetyRule]:
    rules: dict[str, SafetyRule] = {}
    category = 'General Safety'
    for lineno, raw in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = raw.strip()
        if line.startswith('## '):
            category = line[3:].strip()
            continue
        m = re.match(r'^-\s+\*\*(SR-\d+)\s*\(([^)]+)\):\*\*\s*(.+)$', line)
        if m:
            rule_id, title, body = m.groups()
            rules[rule_id] = SafetyRule(
                id=rule_id,
                category=f'{category} — {title.strip()}',
                rule_text=body.strip(),
                evidence=Evidence(file=path.name, location=f'line {lineno}', excerpt=line),
            )
    if not rules:
        raise CorpusParseError(f'No safety rules extracted from {path.name}')
    return rules


def _parse_glossary_and_aliases(
    path: Path,
) -> tuple[dict[str, TestAliasRecord], dict[str, GlossaryEntry], dict[str, str]]:
    aliases: dict[str, TestAliasRecord] = {}
    glossary: dict[str, GlossaryEntry] = {}
    name_to_id: dict[str, str] = {}
    section = 0
    header: list[str] | None = None

    for lineno, raw in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = raw.strip()
        if line.startswith('## Section 1'):
            section = 1
            header = None
            continue
        if line.startswith('## Section 2'):
            section = 2
            header = None
            continue
        if not line.startswith('|'):
            continue

        cells = _split_md_row(line)
        if _is_separator_row(cells):
            continue

        if header is None:
            header = [c.casefold() for c in cells]
            continue

        if section == 1 and len(cells) >= 6:
            test_id, canonical, alias_str, simple_exp, low_m, high_m = cells[:6]
            alias_list = [a.strip() for a in alias_str.split(';') if a.strip()]
            evidence = Evidence(file=path.name, location=f'line {lineno}', excerpt=line)
            aliases[test_id] = TestAliasRecord(
                id=test_id,
                name=canonical,
                aliases=alias_list,
                conversions=[],
                evidence=evidence,
            )
            glossary[test_id] = GlossaryEntry(
                test_id=test_id,
                test_name=canonical,
                simple_explanation=simple_exp,
                low_meaning=low_m,
                high_meaning=high_m,
                evidence=evidence,
            )
            for candidate in [canonical, *alias_list]:
                name_to_id[_norm(candidate)] = test_id

        elif section == 2 and len(cells) >= 5:
            test_id, from_unit, to_unit, multiplier_s, offset_s = cells[:5]
            if test_id not in aliases:
                raise CorpusParseError(f'Conversion references unknown test_id {test_id} at {path.name}:{lineno}')
            conv = Conversion(
                test_id=test_id,
                from_unit=from_unit,
                to_unit=to_unit,
                multiplier=Decimal(multiplier_s),
                offset=Decimal(offset_s),
                evidence=Evidence(file=path.name, location=f'line {lineno}', excerpt=line),
            )
            aliases[test_id].conversions.append(conv)

    if not aliases or not glossary:
        raise CorpusParseError(f'Failed to extract tests and glossary from {path.name}')
    return aliases, glossary, name_to_id


def _parse_urgent_thresholds(path: Path, name_to_id: dict[str, str]) -> list[UrgentThreshold]:
    thresholds: list[UrgentThreshold] = []
    header: list[str] | None = None

    for lineno, raw in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = raw.strip()
        if not line.startswith('|'):
            continue
        cells = _split_md_row(line)
        if _is_separator_row(cells):
            continue
        if header is None:
            header = [c.casefold() for c in cells]
            continue
        if len(cells) < 9:
            continue

        rule_id, test_name, sex_s, age_min_s, age_max_s, op, val_s, unit, warning = cells[:9]
        test_id = name_to_id.get(_norm(test_name))
        if not test_id:
            raise CorpusParseError(f'Unknown test "{test_name}" in {path.name}:{lineno}')

        sex = None if sex_s.casefold() == 'all' else sex_s.casefold()
        age_min = None if age_min_s.casefold() == 'all' else Decimal(age_min_s)
        age_max = None if age_max_s.casefold() == 'all' else Decimal(age_max_s)

        thresholds.append(
            UrgentThreshold(
                id=rule_id,
                test_id=test_id,
                sex=sex,
                age_min=age_min,
                age_max=age_max,
                operator=op,
                value=Decimal(val_s),
                unit=unit,
                warning=warning,
                evidence=Evidence(file=path.name, location=f'line {lineno}', excerpt=line),
            )
        )

    if not thresholds:
        raise CorpusParseError(f'No urgent thresholds found in {path.name}')
    return thresholds


def _parse_reference_ranges(path: Path, name_to_id: dict[str, str]) -> list[ReferenceRange]:
    ranges: list[ReferenceRange] = []
    header: list[str] | None = None

    for lineno, raw in enumerate(path.read_text(encoding='utf-8-sig').splitlines(), 1):
        line = raw.strip()
        if not line.startswith('|'):
            continue
        cells = _split_md_row(line)
        if _is_separator_row(cells):
            continue
        if header is None:
            if 'rule id' in [c.casefold() for c in cells]:
                header = [c.casefold() for c in cells]
            continue
        if len(cells) < 8:
            continue

        rule_id, test_name, sex_s, age_scope, _low_s, _high_s, bounds_s, unit = cells[:8]
        test_id = name_to_id.get(_norm(test_name))
        if not test_id:
            raise CorpusParseError(f'Unknown test "{test_name}" in {path.name}:{lineno}')

        sex = None if sex_s.casefold() == 'all' else sex_s.casefold()
        age_min, age_max, age_min_inc, age_max_inc = _parse_bound_interval(age_scope)
        low, high, low_inc, high_inc = _parse_bound_interval(bounds_s)

        ranges.append(
            ReferenceRange(
                id=rule_id,
                test_id=test_id,
                sex=sex,
                age_min=age_min,
                age_max=age_max,
                age_min_inclusive=age_min_inc,
                age_max_inclusive=age_max_inc,
                low=low,
                high=high,
                low_inclusive=low_inc,
                high_inclusive=high_inc,
                unit=unit,
                evidence=Evidence(file=path.name, location=f'line {lineno}', excerpt=line),
            )
        )

    return ranges


def verify_corpus_evidence(db: Database, corpus_dir: Path) -> int:
    """Verify every medical rule, alias, conversion, and glossary excerpt literally exists in corpus_dir."""
    corpus_root = corpus_dir.resolve()
    text_cache: dict[Path, str] = {}
    evidences: list[Evidence] = [
        *[s.evidence for s in db.safety_rules.values()],
        *[t.evidence for t in db.test_aliases.values()],
        *[c.evidence for t in db.test_aliases.values() for c in t.conversions],
        *[g.evidence for g in db.medical_glossary.values()],
        *[r.evidence for r in db.reference_ranges],
        *[u.evidence for u in db.urgent_thresholds],
    ]
    for ev in evidences:
        target = (corpus_root / ev.file).resolve()
        if not target.is_relative_to(corpus_root) or not target.is_file():
            raise CorpusParseError(f'Evidence source file not found inside corpus: {ev.file}')
        if target not in text_cache:
            if target.suffix.lower() == '.pdf':
                from pypdf import PdfReader
                text_cache[target] = '\n'.join(page.extract_text() or '' for page in PdfReader(target).pages)
            else:
                text_cache[target] = target.read_text(encoding='utf-8-sig')
        if ev.excerpt not in text_cache[target]:
            raise CorpusParseError(f'Evidence excerpt not found in {ev.file} ({ev.location})')
    return len(evidences)


def _detect_corpus_provenance(files: list[Path]) -> KnowledgeProvenance:
    for p in files:
        head = '\n'.join(p.read_text(encoding='utf-8-sig').splitlines()[:10]).casefold()
        if 'provenance: synthetic' in head or 'synthetic demonstration' in head:
            return 'synthetic'
    return 'organizer_reviewed'


def ingest_corpus_directory(
    corpus_dir: Path,
    repo: Repository,
    analyze_fn=None,
    provenance: KnowledgeProvenance | None = None,
) -> Database:
    """Ingest corpus markdown files into canonical JSON storage without altering source files."""
    if not corpus_dir.is_dir():
        raise CorpusParseError(f'Corpus directory does not exist: {corpus_dir}')

    files = sorted(p for p in corpus_dir.iterdir() if p.is_file() and not p.name.startswith('.'))
    safety_files = [p for p in files if 'safety_rules' in p.name]
    glossary_files = [p for p in files if 'medical_glossary' in p.name]
    urgent_files = [p for p in files if 'urgent_values' in p.name]
    range_files = [p for p in files if 'reference_ranges' in p.name]
    report_files = [p for p in files if 'report' in p.name]

    if not safety_files or not glossary_files or not urgent_files or not range_files:
        raise CorpusParseError('Corpus directory is missing mandatory CityLab rule/reference documents.')

    resolved_provenance: KnowledgeProvenance = provenance or _detect_corpus_provenance(
        [*safety_files, *glossary_files, *urgent_files, *range_files]
    )
    reviewed_flag = resolved_provenance != 'organizer_unreviewed'

    safety_rules: dict[str, SafetyRule] = {}
    for p in safety_files:
        safety_rules.update(_parse_safety_rules(p))

    test_aliases: dict[str, TestAliasRecord] = {}
    medical_glossary: dict[str, GlossaryEntry] = {}
    name_to_id: dict[str, str] = {}
    for p in glossary_files:
        aliases, glossary, mapping = _parse_glossary_and_aliases(p)
        test_aliases.update(aliases)
        medical_glossary.update(glossary)
        name_to_id.update(mapping)

    urgent_thresholds: list[UrgentThreshold] = []
    for p in urgent_files:
        urgent_thresholds.extend(_parse_urgent_thresholds(p, name_to_id))

    reference_ranges: list[ReferenceRange] = []
    for p in range_files:
        reference_ranges.extend(_parse_reference_ranges(p, name_to_id))

    patients: dict[str, Patient] = {}
    reports = {}
    report_metadata = {}
    for p in report_files:
        report, meta, patient = extract_report(
            p.read_bytes(),
            p.name,
            authorized_patient=None,
            synthetic=(True if resolved_provenance == 'synthetic' else None),
        )
        if patient is None:
            patient = Patient(
                id=report.patient_id,
                name=f'Patient {report.patient_id}',
                age=report.age_at_report,
                sex=report.sex_at_report,
            )
        patients.setdefault(patient.id, patient)
        reports[report.id] = report
        report_metadata[report.id] = meta

    candidate_knowledge = Database(
        reviewed=reviewed_flag,
        knowledge_provenance=resolved_provenance,
        safety_rules=safety_rules,
        test_aliases=test_aliases,
        medical_glossary=medical_glossary,
        urgent_thresholds=urgent_thresholds,
        reference_ranges=reference_ranges,
    )
    verify_corpus_evidence(candidate_knowledge, corpus_dir)

    def apply_corpus(db: Database) -> None:
        db.reviewed = reviewed_flag
        db.knowledge_provenance = resolved_provenance
        db.safety_rules = safety_rules
        db.test_aliases = test_aliases
        db.medical_glossary = medical_glossary
        db.urgent_thresholds = urgent_thresholds
        db.reference_ranges = reference_ranges
        for pid, pat in patients.items():
            db.patients[pid] = pat
        for rid, rep in reports.items():
            db.reports[rid] = rep
        for rid, meta in report_metadata.items():
            db.report_metadata[rid] = meta
        db.analysis_results = {}

    db = repo.update(apply_corpus)

    if analyze_fn is not None:
        def save_analyses(current: Database) -> None:
            for rid, rep in current.reports.items():
                current.analysis_results[rid] = analyze_fn(rep, current)

        db = repo.update(save_analyses)

    return db
