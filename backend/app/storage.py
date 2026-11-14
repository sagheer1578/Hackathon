"""Canonical atomic JSON snapshot persistence layer with file locking and legacy migration.

Note: Filesystem-backed JSON storage is intentionally designed for this hackathon dataset
and single-node deployment; it is not a replacement for a transactional RDBMS in
high-concurrency production healthcare systems.
"""
import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .models import (
    Analysis,
    Database,
    GlossaryEntry,
    KnowledgeProvenance,
    Patient,
    ReferenceRange,
    Report,
    ReportMetadata,
    SafetyRule,
    TestAliasRecord,
    UrgentThreshold,
)

CANONICAL_FILENAME = 'database.json'

JSON_FILENAMES = (
    'patients.json',
    'reports.json',
    'reference_ranges.json',
    'test_aliases.json',
    'urgent_thresholds.json',
    'medical_glossary.json',
    'safety_rules.json',
    'analysis_results.json',
    'report_metadata.json',
)


class StorageError(Exception):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f'Duplicate JSON key detected: {key}')
        out[key] = value
    return out


def _loads_strict(raw: str) -> object:
    if not raw or not raw.strip():
        raise ValueError('Empty JSON content')
    return json.loads(raw, object_pairs_hook=_reject_duplicate_keys)


class _Envelope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1


class _PatientsFile(_Envelope):
    records: dict[str, Patient] = Field(default_factory=dict)


class _ReportsFile(_Envelope):
    records: dict[str, Report] = Field(default_factory=dict)


class _MetadataFile(_Envelope):
    records: dict[str, ReportMetadata] = Field(default_factory=dict)


class _AnalysisFile(_Envelope):
    records: dict[str, Analysis] = Field(default_factory=dict)


class _KnowledgeMetaEnvelope(_Envelope):
    knowledge_version: str = 'empty-no-corpus'
    reviewed: bool = False


class _AliasesFile(_KnowledgeMetaEnvelope):
    records: dict[str, TestAliasRecord] = Field(default_factory=dict)


class _RangesFile(_KnowledgeMetaEnvelope):
    records: list[ReferenceRange] = Field(default_factory=list)


class _UrgentFile(_KnowledgeMetaEnvelope):
    records: list[UrgentThreshold] = Field(default_factory=list)


class _GlossaryFile(_KnowledgeMetaEnvelope):
    records: dict[str, GlossaryEntry] = Field(default_factory=dict)


class _SafetyFile(_KnowledgeMetaEnvelope):
    records: dict[str, SafetyRule] = Field(default_factory=dict)


def compute_knowledge_version(db: Database) -> str:
    if not db.reviewed and not db.test_aliases and not db.reference_ranges and not db.urgent_thresholds:
        return 'empty-no-corpus'
    payload = (
        db.knowledge_provenance
        + _AliasesFile(knowledge_version='', reviewed=db.reviewed, records=db.test_aliases).model_dump_json()
        + _RangesFile(knowledge_version='', reviewed=db.reviewed, records=db.reference_ranges).model_dump_json()
        + _UrgentFile(knowledge_version='', reviewed=db.reviewed, records=db.urgent_thresholds).model_dump_json()
        + _GlossaryFile(knowledge_version='', reviewed=db.reviewed, records=db.medical_glossary).model_dump_json()
        + _SafetyFile(knowledge_version='', reviewed=db.reviewed, records=db.safety_rules).model_dump_json()
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


class Repository:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = FileLock(str(self.directory / '.storage.lock'), timeout=10)
        self.snapshot_file = self.directory / CANONICAL_FILENAME
        self.files = {name: self.directory / name for name in JSON_FILENAMES}

    def initialized(self) -> bool:
        return self.snapshot_file.exists() or all(path.exists() for path in self.files.values())

    def _load_legacy_file(self, filename: str, model_cls):
        path = self.files[filename]
        try:
            raw = path.read_text(encoding='utf-8')
            parsed = _loads_strict(raw)
            return model_cls.model_validate(parsed)
        except (OSError, ValidationError, ValueError) as exc:
            raise StorageError(f'Legacy storage file {filename} is unreadable; existing data has been preserved.') from exc

    def _migrate_legacy_unlocked(self) -> Database:
        missing = [name for name, path in self.files.items() if not path.exists()]
        if missing:
            raise StorageError(
                f'Incomplete legacy JSON dataset (missing: {", ".join(missing)}). Refusing to guess defaults.'
            )

        patients_f = self._load_legacy_file('patients.json', _PatientsFile)
        reports_f = self._load_legacy_file('reports.json', _ReportsFile)
        ranges_f = self._load_legacy_file('reference_ranges.json', _RangesFile)
        aliases_f = self._load_legacy_file('test_aliases.json', _AliasesFile)
        urgent_f = self._load_legacy_file('urgent_thresholds.json', _UrgentFile)
        glossary_f = self._load_legacy_file('medical_glossary.json', _GlossaryFile)
        safety_f = self._load_legacy_file('safety_rules.json', _SafetyFile)
        analyses_f = self._load_legacy_file('analysis_results.json', _AnalysisFile)
        meta_f = self._load_legacy_file('report_metadata.json', _MetadataFile)

        knowledge_files = (aliases_f, ranges_f, urgent_f, glossary_f, safety_f)
        if len({(f.reviewed, f.knowledge_version) for f in knowledge_files}) != 1:
            raise StorageError('Legacy knowledge files have inconsistent versions or review states.')

        reviewed = aliases_f.reviewed
        kver = aliases_f.knowledge_version
        is_synthetic_legacy = any(
            r.synthetic
            or r.source_file.startswith(('6_report_patient_', '7_report_patient_', '8_report_patient_', '9_report_patient_'))
            for r in reports_f.records.values()
        )
        provenance: KnowledgeProvenance = (
            'synthetic' if is_synthetic_legacy else ('organizer_reviewed' if reviewed else 'organizer_unreviewed')
        )
        if is_synthetic_legacy:
            for rep in reports_f.records.values():
                if rep.source_file.startswith(('6_report_patient_', '7_report_patient_', '8_report_patient_', '9_report_patient_')):
                    rep.synthetic = True
            for ana in analyses_f.records.values():
                ana.knowledge_provenance = 'synthetic'

        try:
            db = Database(
                reviewed=reviewed,
                knowledge_version=kver,
                knowledge_provenance=provenance,
                patients=patients_f.records,
                reports=reports_f.records,
                report_metadata=meta_f.records,
                test_aliases=aliases_f.records,
                reference_ranges=ranges_f.records,
                urgent_thresholds=urgent_f.records,
                medical_glossary=glossary_f.records,
                safety_rules=safety_f.records,
                analysis_results=analyses_f.records,
            )
        except ValidationError as exc:
            raise StorageError('Cross-file legacy JSON integrity check failed; existing data has been preserved.') from exc

        # Persist canonical snapshot once while keeping all 9 legacy files untouched as backup.
        self._atomic_write_snapshot(db.model_dump_json(indent=2))
        return db

    def _read_unlocked(self) -> Database:
        if self.snapshot_file.exists():
            try:
                raw = self.snapshot_file.read_text(encoding='utf-8')
                parsed = _loads_strict(raw)
                return Database.model_validate(parsed)
            except (OSError, ValidationError, ValueError) as exc:
                raise StorageError(
                    f'Canonical storage file {CANONICAL_FILENAME} is unreadable; existing data has been preserved.'
                ) from exc

        if any(path.exists() for path in self.files.values()):
            return self._migrate_legacy_unlocked()

        return Database()

    def init_empty(self) -> Database:
        """Explicitly initialize an empty canonical snapshot when no storage files exist."""
        with self.lock:
            if self.snapshot_file.exists() or any(path.exists() for path in self.files.values()):
                return self._read_unlocked()
            db = Database()
            self._atomic_write_snapshot(db.model_dump_json(indent=2))
            return db

    def read(self) -> Database:
        with self.lock:
            return self._read_unlocked()

    def _atomic_write_snapshot(self, content: str) -> None:
        temp = None
        try:
            fd, temp = tempfile.mkstemp(prefix=f'{CANONICAL_FILENAME}-', suffix='.tmp', dir=self.directory)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.snapshot_file)
            temp = None
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)

    def update(self, mutate: Callable[[Database], None]) -> Database:
        with self.lock:
            db = self._read_unlocked()
            mutate(db)
            db = Database.model_validate(db.model_dump())
            if db.reviewed:
                db.knowledge_version = compute_knowledge_version(db)
            elif not db.test_aliases and not db.reference_ranges and not db.urgent_thresholds:
                db.knowledge_version = 'empty-no-corpus'

            content = db.model_dump_json(indent=2)
            if self.snapshot_file.exists():
                try:
                    if self.snapshot_file.read_text(encoding='utf-8') == content:
                        return db
                except OSError:
                    pass
            self._atomic_write_snapshot(content)
            return db

    def get_patient(self, patient_id: str) -> Patient | None:
        return self.read().patients.get(patient_id)

    def get_reports_for_patient(self, patient_id: str) -> list[Report]:
        db = self.read()
        return [r for r in db.reports.values() if r.patient_id == patient_id]

    def get_report(self, report_id: str) -> Report | None:
        return self.read().reports.get(report_id)
