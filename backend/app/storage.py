"""Nine-file atomic JSON persistence layer with file locking and integrity validation.

Note: Filesystem-backed JSON storage is intentionally designed for this hackathon dataset
and single-node container deployment; it is not a replacement for a transactional RDBMS in
high-concurrency production healthcare systems.
"""
import hashlib
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
    Patient,
    ReferenceRange,
    Report,
    ReportMetadata,
    SafetyRule,
    TestAliasRecord,
    UrgentThreshold,
)


class StorageError(Exception):
    pass


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


def compute_knowledge_version(db: Database) -> str:
    if not db.reviewed and not db.test_aliases and not db.reference_ranges and not db.urgent_thresholds:
        return 'empty-no-corpus'
    payload = (
        _AliasesFile(knowledge_version='', reviewed=db.reviewed, records=db.test_aliases).model_dump_json()
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
        self.files = {name: self.directory / name for name in JSON_FILENAMES}

    def initialized(self) -> bool:
        return self.files['patients.json'].exists() and self.files['test_aliases.json'].exists()

    def _load_file(self, filename: str, model_cls):
        path = self.files[filename]
        if not path.exists():
            return model_cls()
        try:
            raw = path.read_text(encoding='utf-8')
            return model_cls.model_validate_json(raw)
        except (OSError, ValidationError, ValueError) as exc:
            raise StorageError(f'Storage file {filename} is unreadable; existing data has been preserved.') from exc

    def _read_unlocked(self) -> Database:
        patients_f = self._load_file('patients.json', _PatientsFile)
        reports_f = self._load_file('reports.json', _ReportsFile)
        ranges_f = self._load_file('reference_ranges.json', _RangesFile)
        aliases_f = self._load_file('test_aliases.json', _AliasesFile)
        urgent_f = self._load_file('urgent_thresholds.json', _UrgentFile)
        glossary_f = self._load_file('medical_glossary.json', _GlossaryFile)
        safety_f = self._load_file('safety_rules.json', _SafetyFile)
        analyses_f = self._load_file('analysis_results.json', _AnalysisFile)
        meta_f = self._load_file('report_metadata.json', _MetadataFile)

        reviewed = aliases_f.reviewed
        kver = aliases_f.knowledge_version
        try:
            return Database(
                reviewed=reviewed,
                knowledge_version=kver,
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
            raise StorageError('Cross-file JSON integrity check failed; existing data has been preserved.') from exc

    def read(self) -> Database:
        with self.lock:
            return self._read_unlocked()

    def _atomic_write_json(self, filename: str, content: str) -> None:
        target = self.files[filename]
        temp = None
        try:
            fd, temp = tempfile.mkstemp(prefix=f'{filename}-', suffix='.tmp', dir=self.directory)
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
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

            payloads = {
                'patients.json': _PatientsFile(records=db.patients).model_dump_json(indent=2),
                'reports.json': _ReportsFile(records=db.reports).model_dump_json(indent=2),
                'report_metadata.json': _MetadataFile(records=db.report_metadata).model_dump_json(indent=2),
                'analysis_results.json': _AnalysisFile(records=db.analysis_results).model_dump_json(indent=2),
                'test_aliases.json': _AliasesFile(
                    knowledge_version=db.knowledge_version,
                    reviewed=db.reviewed,
                    records=db.test_aliases,
                ).model_dump_json(indent=2),
                'reference_ranges.json': _RangesFile(
                    knowledge_version=db.knowledge_version,
                    reviewed=db.reviewed,
                    records=db.reference_ranges,
                ).model_dump_json(indent=2),
                'urgent_thresholds.json': _UrgentFile(
                    knowledge_version=db.knowledge_version,
                    reviewed=db.reviewed,
                    records=db.urgent_thresholds,
                ).model_dump_json(indent=2),
                'medical_glossary.json': _GlossaryFile(
                    knowledge_version=db.knowledge_version,
                    reviewed=db.reviewed,
                    records=db.medical_glossary,
                ).model_dump_json(indent=2),
                'safety_rules.json': _SafetyFile(
                    knowledge_version=db.knowledge_version,
                    reviewed=db.reviewed,
                    records=db.safety_rules,
                ).model_dump_json(indent=2),
            }

            for filename, content in payloads.items():
                current = self.files[filename]
                if current.exists():
                    try:
                        if current.read_text(encoding='utf-8') == content:
                            continue
                    except OSError:
                        pass
                self._atomic_write_json(filename, content)
            return db

    def get_patient(self, patient_id: str) -> Patient | None:
        return self.read().patients.get(patient_id)

    def get_reports_for_patient(self, patient_id: str) -> list[Report]:
        db = self.read()
        return [r for r in db.reports.values() if r.patient_id == patient_id]

    def get_report(self, report_id: str) -> Report | None:
        return self.read().reports.get(report_id)
