from decimal import Decimal
from pathlib import Path
import pytest
from backend.app.corpus_parser import ingest_corpus_directory
from backend.app.engine import analyze
from backend.app.models import Database
from backend.app.storage import Repository


@pytest.mark.parametrize(
    'test,value,unit,status',
    [
        ('SGPT', '45', 'U/L', 'Normal'),
        ('alt', '45.0001', 'U/L', 'High'),
        (' ALT ', '9.999', 'U/L', 'Low'),
        ('ALT', '10', 'U/L', 'Normal'),
        ('FBS', '200', 'mg/dL', 'Normal'),
        ('Fasting Blood Sugar', '200.01', 'mg/dL', 'High'),
        ('FBS', '10', 'mmol/L', 'Normal'),
        ('FBS', '20', 'mmol/L', 'Urgent'),
        ('FBS', '400', 'mg/dL', 'Urgent'),
        ('FBS', '399.999', 'mg/dL', 'High'),
        ('ALT', '20', 'mmol/L', 'Cannot Be Classified'),
        ('Serum Ferritin', '25', 'ng/mL', 'Cannot Be Classified'),
        ('ALT', 'NaN', 'U/L', 'Cannot Be Classified'),
        ('ALT', 'Infinity', 'U/L', 'Cannot Be Classified'),
        ('ALT', '<10', 'U/L', 'Cannot Be Classified'),
        ('ALT', '10-12', 'U/L', 'Cannot Be Classified'),
        ('ALT', '', 'U/L', 'Cannot Be Classified'),
        ('ALT', '45', '', 'Cannot Be Classified'),
    ],
)
def test_boundaries_aliases_and_units(db_fixture, make_report, test, value, unit, status):
    result = analyze(make_report(test, value, unit), db_fixture).results[0]
    assert result.status == status
    assert result.reason and result.evidence


def test_exclusive_limits(db_fixture, make_report):
    db_fixture.reference_ranges[0].high_inclusive = False
    assert analyze(make_report(value='45'), db_fixture).results[0].status == 'High'
    db_fixture.reference_ranges[0].low_inclusive = False
    assert analyze(make_report(value='10'), db_fixture).results[0].status == 'Low'


@pytest.mark.parametrize(
    'age,sex,status',
    [
        (None, 'female', 'Cannot Be Classified'),
        ('18', 'unknown', 'Cannot Be Classified'),
        ('17.999', 'female', 'Cannot Be Classified'),
        ('18', 'female', 'Normal'),
        ('65', 'female', 'Normal'),
        ('65.001', 'female', 'Cannot Be Classified'),
        ('25', 'male', 'Cannot Be Classified'),
    ],
)
def test_demographics(db_fixture, make_report, age, sex, status):
    rule = db_fixture.reference_ranges[0]
    rule.age_min = Decimal('18')
    rule.age_max = Decimal('65')
    rule.sex = 'female'
    assert analyze(make_report(age_at_report=age, sex_at_report=sex), db_fixture).results[0].status == status


def test_exclusive_age_boundary(db_fixture, make_report):
    rule = db_fixture.reference_ranges[0]
    rule.age_min = Decimal('18')
    rule.age_min_inclusive = False
    assert analyze(make_report(age_at_report='18'), db_fixture).results[0].status == 'Cannot Be Classified'
    assert analyze(make_report(age_at_report='18.001'), db_fixture).results[0].status == 'Normal'


def test_overlap_and_alias_conflicts(db_fixture, make_report):
    db_fixture.reference_ranges.append(db_fixture.reference_ranges[0].model_copy(update={'id': 'conflict'}))
    result = analyze(make_report(), db_fixture).results[0]
    assert result.status == 'Cannot Be Classified' and 'overlapping' in result.reason
    db_fixture.test_aliases['fbs'].aliases.append('ALT')
    assert 'ambiguous' in analyze(make_report(), db_fixture).results[0].reason.casefold()


def test_urgency_independent_of_ranges(db_fixture, make_report):
    db_fixture.reference_ranges = []
    result = analyze(make_report('FBS', '400', 'mg/dL'), db_fixture).results[0]
    assert result.status == 'Urgent' and result.warnings
    assert 'No reference range' in result.reason


def test_urgency_missing_demographics(db_fixture, make_report):
    db_fixture.reference_ranges[1].sex = 'female'
    result = analyze(make_report('FBS', '400', 'mg/dL'), db_fixture).results[0]
    assert result.status == 'Urgent'
    db_fixture.urgent_thresholds[0].sex = 'female'
    result = analyze(make_report('FBS', '400', 'mg/dL'), db_fixture).results[0]
    assert result.status == 'Cannot Be Classified'
    assert 'incomplete' in result.warnings[0]


def test_conversion_audit(db_fixture, make_report):
    result = analyze(make_report('FBS', '10', 'mmol/L'), db_fixture).results[0]
    assert any('10 mmol/L * 20 + 0 = 200 mg/dL' in s for s in result.audit)
    assert result.value == '10' and result.unit == 'mmol/L'
    assert result.converted_value == '200' and result.converted_unit == 'mg/dL'


def test_duplicate_preserves_urgent(db_fixture, make_report):
    report = make_report('FBS', '400', 'mg/dL')
    report.measurements.append(report.measurements[0].model_copy(update={'id': 'm2', 'value': '150'}))
    results = analyze(report, db_fixture).results
    assert results[0].status == 'Urgent' and 'Repeated' in results[0].reason
    assert results[1].status == 'Cannot Be Classified'


def test_empty_and_unreviewed_knowledge(db_fixture, make_report):
    for rules in [Database(), db_fixture.model_copy(update={'reviewed': False})]:
        assert 'No reviewed' in analyze(make_report(), rules).results[0].reason


@pytest.mark.parametrize(
    'operator,value,expected',
    [('<', '400', False), ('<=', '400', True), ('>', '400', False), ('>=', '400', True)],
)
def test_urgent_exact_operators(db_fixture, make_report, operator, value, expected):
    db_fixture.urgent_thresholds[0].operator = operator
    assert (analyze(make_report('FBS', value, 'mg/dL'), db_fixture).results[0].status == 'Urgent') == expected


def test_ambiguous_conversion_rejected(db_fixture, make_report):
    db_fixture.test_aliases['fbs'].conversions.append(db_fixture.test_aliases['fbs'].conversions[0].model_copy())
    result = analyze(make_report('FBS', '10', 'mmol/L'), db_fixture).results[0]
    assert result.status == 'Cannot Be Classified'


def test_real_citylab_corpus_patients(tmp_path):
    corpus_dir = Path(__file__).resolve().parent.parent / 'corpus'
    repo = Repository(tmp_path / 'data')
    db = ingest_corpus_directory(corpus_dir, repo, analyze_fn=analyze)

    assert len(db.patients) == 4
    assert len(db.reports) == 4
    assert len(db.test_aliases) == 17
    assert db.knowledge_provenance == 'synthetic'
    assert all(rep.synthetic for rep in db.reports.values())
    assert all(ana.knowledge_provenance == 'synthetic' for ana in db.analysis_results.values())

    by_patient = {a.patient_id: a for a in db.analysis_results.values()}

    # Patient p001: Arjun Mehta (boundaries & conversions)
    p1 = {r.test: r for r in by_patient['patient-p001'].results}
    assert p1['SGPT'].status == 'Normal' and p1['SGPT'].canonical_test_name == 'ALT'
    assert p1['FBS'].status == 'High' and p1['FBS'].converted_value == '126'
    assert p1['Total Cholesterol'].status == 'Normal'
    assert p1['HDL Cholesterol'].status == 'Low'
    assert p1['TSH'].status == 'High'

    # Patient p002: Fatima Khan (urgent values)
    p2 = {r.test: r for r in by_patient['patient-p002'].results}
    assert p2['Fasting Blood Sugar'].status == 'Urgent' and p2['Fasting Blood Sugar'].converted_value == '405'
    assert p2['Potassium'].status == 'Urgent'
    assert p2['Hb'].status == 'Low'

    # Patient p003: Jordan Patel (missing demographics, independent urgent check)
    p3 = {r.test: r for r in by_patient['patient-p003'].results}
    assert p3['Hemoglobin'].status == 'Cannot Be Classified'
    assert p3['Serum Creatinine'].status == 'Cannot Be Classified'
    assert p3['Serum Potassium'].status == 'Urgent'
    assert p3['ALT'].status == 'Cannot Be Classified'

    # Patient p004: Viktor Chen (noisy doc, injection neutralized, edge cases)
    p4 = {r.test: r for r in by_patient['patient-p004'].results}
    assert p4['Serum Ferritin'].status == 'Cannot Be Classified'
    assert p4['WBC'].status == 'Cannot Be Classified'
    assert p4['TSH'].status == 'Cannot Be Classified'
    assert p4['ALT'].status == 'Cannot Be Classified'
    assert p4['SGPT'].status == 'Cannot Be Classified'
    assert p4['Serum Creatinine'].status == 'Normal'
    assert p4['Total Cholesterol'].status == 'High'


def test_synthetic_rules_not_applied_to_real_report_and_unreviewed_corpus(db_fixture, make_report):
    synthetic_db = db_fixture.model_copy(update={'knowledge_provenance': 'synthetic'})
    real_report = make_report(synthetic=False)
    real_result = analyze(real_report, synthetic_db).results[0]
    assert real_result.status == 'Cannot Be Classified'
    assert 'Synthetic demonstration reference rules cannot be applied' in real_result.reason

    synth_report = make_report(synthetic=True)
    assert analyze(synth_report, synthetic_db).results[0].status == 'Normal'

    unreviewed_db = db_fixture.model_copy(update={'knowledge_provenance': 'organizer_unreviewed'})
    assert 'No reviewed' in analyze(real_report, unreviewed_db).results[0].reason
