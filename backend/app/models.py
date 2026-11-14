"""Pydantic domain models and cross-collection integrity checks."""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Evidence(Model):
    file: str = Field(min_length=1, max_length=240)
    location: str = Field(min_length=1, max_length=160)
    excerpt: str = Field(min_length=1, max_length=6000)


class Patient(Model):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    name: str = Field(min_length=1, max_length=160)
    age: Decimal | None = Field(default=None, ge=0, le=150)
    sex: Literal['female', 'male', 'unknown'] = 'unknown'
    profile_type: Literal['demo', 'personal'] = 'demo'
    created_at: datetime | None = None


class AccessCredential(Model):
    patient_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    code_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SessionRecord(Model):
    session_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    patient_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    token_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime


class Measurement(Model):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    test: str = Field(min_length=1, max_length=160)
    value: str = Field(max_length=80)
    unit: str = Field(default='', max_length=80)
    evidence: Evidence
    issue: str | None = None
    original_test: str | None = Field(default=None, max_length=160)
    original_value: str | None = Field(default=None, max_length=80)
    original_unit: str | None = Field(default=None, max_length=80)
    user_corrected: bool = False
    corrected_at: datetime | None = None
    uncertain: bool = False


KnowledgeProvenance = Literal['synthetic', 'organizer_unreviewed', 'organizer_reviewed']


class Report(Model):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    patient_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    title: str = Field(default='', max_length=240)
    report_date: date | None = None
    uploaded_at: datetime | None = None
    age_at_report: Decimal | None = Field(default=None, ge=0, le=150)
    sex_at_report: Literal['female', 'male', 'unknown'] = 'unknown'
    original_age_at_report: Decimal | None = Field(default=None, ge=0, le=150)
    original_sex_at_report: Literal['female', 'male', 'unknown'] = 'unknown'
    demographics_overridden: bool = False
    review_status: Literal['ready', 'needs_review'] = 'ready'
    reviewed_at: datetime | None = None
    printed_patient_name: str | None = Field(default=None, max_length=160)
    printed_patient_id: str | None = Field(default=None, max_length=160)
    name_mismatch_warning: str | None = Field(default=None, max_length=500)
    name_mismatch_confirmed: bool = False
    stored_filename: str | None = Field(default=None, max_length=240)
    source_media_type: str | None = Field(default=None, max_length=120)
    measurements: list[Measurement] = Field(min_length=1, max_length=500)
    issues: list[str] = Field(default_factory=list)
    source_file: str = ''
    source_hash: str = ''
    synthetic: bool = False

    @model_validator(mode='after')
    def unique_measurements(self):
        if len({m.id for m in self.measurements}) != len(self.measurements):
            raise ValueError('Duplicate measurement IDs in report')
        return self


class ReportMetadata(Model):
    report_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    patient_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    source_file: str = Field(min_length=1, max_length=240)
    source_hash: str = Field(default='', max_length=128)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    line_count: int = Field(default=0, ge=0)
    noise_lines_skipped: int = Field(default=0, ge=0)
    prompt_injection_detected: bool = False
    extraction_issues: list[str] = Field(default_factory=list)


class DemographicRule(Model):
    age_min: Decimal | None = Field(default=None, ge=0)
    age_max: Decimal | None = Field(default=None, ge=0)
    age_min_inclusive: bool = True
    age_max_inclusive: bool = True
    sex: Literal['female', 'male'] | None = None

    @model_validator(mode='after')
    def valid_age(self):
        if self.age_min is not None and self.age_max is not None and self.age_min > self.age_max:
            raise ValueError('Reversed age interval')
        return self


class ReferenceRange(DemographicRule):
    id: str = Field(min_length=1, max_length=100)
    test_id: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=60)
    low: Decimal | None = None
    high: Decimal | None = None
    low_inclusive: bool = True
    high_inclusive: bool = True
    evidence: Evidence

    @model_validator(mode='after')
    def valid_interval(self):
        if self.low is None and self.high is None:
            raise ValueError('At least one reference bound is required')
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError('Reversed reference interval')
        return self


class Conversion(Model):
    test_id: str = Field(min_length=1, max_length=80)
    from_unit: str = Field(min_length=1, max_length=60)
    to_unit: str = Field(min_length=1, max_length=60)
    multiplier: Decimal = Field(gt=0)
    offset: Decimal = Decimal('0')
    evidence: Evidence


class TestAliasRecord(Model):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(default_factory=list)
    conversions: list[Conversion] = Field(default_factory=list)
    evidence: Evidence


class GlossaryEntry(Model):
    test_id: str = Field(min_length=1, max_length=80)
    test_name: str = Field(min_length=1, max_length=160)
    simple_explanation: str = Field(min_length=1, max_length=2000)
    low_meaning: str = Field(default='', max_length=2000)
    high_meaning: str = Field(default='', max_length=2000)
    evidence: Evidence


class UrgentThreshold(DemographicRule):
    id: str = Field(min_length=1, max_length=100)
    test_id: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=60)
    operator: Literal['<', '<=', '>', '>=']
    value: Decimal
    warning: str = Field(min_length=1, max_length=2000)
    evidence: Evidence


class SafetyRule(Model):
    id: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=160)
    rule_text: str = Field(min_length=1, max_length=3000)
    evidence: Evidence


Status = Literal['Normal', 'Low', 'High', 'Urgent', 'Cannot Be Classified']


class Result(Model):
    measurement_id: str
    test: str
    canonical_test_id: str | None = None
    canonical_test_name: str | None = None
    value: str
    unit: str
    converted_value: str | None = None
    converted_unit: str | None = None
    status: Status = 'Cannot Be Classified'
    reference: str = 'Unavailable'
    explanation: str = ''
    reason: str = ''
    warnings: list[str] = Field(default_factory=list)
    audit: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class Analysis(Model):
    report_id: str
    patient_id: str
    knowledge_version: str
    knowledge_provenance: KnowledgeProvenance = 'organizer_reviewed'
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    results: list[Result]
    counts: dict[str, int]
    doctor_questions: list[str]
    ai_enhanced: bool = False
    disclaimer: str = (
        'Educational information only. This report does not diagnose a medical condition '
        'or recommend treatment. Please discuss these results with a licensed physician.'
    )


class Database(Model):
    schema_version: Literal[1] = 1
    knowledge_version: str = 'empty-no-corpus'
    reviewed: bool = False
    knowledge_provenance: KnowledgeProvenance = 'organizer_reviewed'
    patients: dict[str, Patient] = Field(default_factory=dict)
    credentials: dict[str, AccessCredential] = Field(default_factory=dict)
    sessions: dict[str, SessionRecord] = Field(default_factory=dict)
    reports: dict[str, Report] = Field(default_factory=dict)
    report_metadata: dict[str, ReportMetadata] = Field(default_factory=dict)
    test_aliases: dict[str, TestAliasRecord] = Field(default_factory=dict)
    reference_ranges: list[ReferenceRange] = Field(default_factory=list)
    urgent_thresholds: list[UrgentThreshold] = Field(default_factory=list)
    medical_glossary: dict[str, GlossaryEntry] = Field(default_factory=dict)
    safety_rules: dict[str, SafetyRule] = Field(default_factory=dict)
    analysis_results: dict[str, Analysis] = Field(default_factory=dict)

    @model_validator(mode='after')
    def integrity(self):
        if any(key != p.id for key, p in self.patients.items()):
            raise ValueError('Patient dictionary key mismatch')
        if any(key != c.patient_id or c.patient_id not in self.patients for key, c in self.credentials.items()):
            raise ValueError('Invalid credential-patient relationship')
        if any(key != s.session_id or s.patient_id not in self.patients for key, s in self.sessions.items()):
            raise ValueError('Invalid session-patient relationship')
        if any(key != r.id or r.patient_id not in self.patients for key, r in self.reports.items()):
            raise ValueError('Invalid report-patient relationship')
        for key, meta in self.report_metadata.items():
            if key != meta.report_id or key not in self.reports or meta.patient_id != self.reports[key].patient_id:
                raise ValueError('Invalid report metadata relationship')
        for key, analysis in self.analysis_results.items():
            if key != analysis.report_id or key not in self.reports or analysis.patient_id != self.reports[key].patient_id:
                raise ValueError('Invalid analysis relationship')
        if any(key != t.id for key, t in self.test_aliases.items()):
            raise ValueError('Test alias dictionary key mismatch')
        if any(key != g.test_id or key not in self.test_aliases for key, g in self.medical_glossary.items()):
            raise ValueError('Glossary entry references unknown test ID')
        if any(key != s.id for key, s in self.safety_rules.items()):
            raise ValueError('Safety rule dictionary key mismatch')
        if len({r.id for r in self.reference_ranges}) != len(self.reference_ranges):
            raise ValueError('Duplicate reference range IDs')
        if len({u.id for u in self.urgent_thresholds}) != len(self.urgent_thresholds):
            raise ValueError('Duplicate urgent threshold IDs')
        known_tests = set(self.test_aliases.keys())
        if any(r.test_id not in known_tests for r in self.reference_ranges):
            raise ValueError('Reference range references unknown test ID')
        if any(u.test_id not in known_tests for u in self.urgent_thresholds):
            raise ValueError('Urgent threshold references unknown test ID')
        for alias_rec in self.test_aliases.values():
            if any(c.test_id != alias_rec.id for c in alias_rec.conversions):
                raise ValueError('Conversion test_id mismatch inside test alias record')
        return self

    def all_conversions(self) -> list[Conversion]:
        return [conv for rec in self.test_aliases.values() for conv in rec.conversions]

    def get_ranges_for_test(self, test_id: str) -> list[ReferenceRange]:
        return [r for r in self.reference_ranges if r.test_id == test_id]

    def get_urgent_for_test(self, test_id: str) -> list[UrgentThreshold]:
        return [u for u in self.urgent_thresholds if u.test_id == test_id]

    def get_glossary_for_test(self, test_id: str) -> GlossaryEntry | None:
        return self.medical_glossary.get(test_id)
