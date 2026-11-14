import pytest
from backend.app.models import (
    Conversion,
    Database,
    Evidence,
    GlossaryEntry,
    Measurement,
    Patient,
    ReferenceRange,
    Report,
    SafetyRule,
    TestAliasRecord,
    UrgentThreshold,
)


@pytest.fixture
def evidence():
    return Evidence(
        file='SYNTHETIC_FIXTURE.md',
        location='line 1',
        excerpt='Synthetic engineering fixture rule. Not for clinical use.',
    )


@pytest.fixture
def db_fixture(evidence):
    return Database(
        knowledge_version='synthetic-test-v1',
        reviewed=True,
        patients={
            'patient-a': Patient(id='patient-a', name='Patient A'),
            'patient-b': Patient(id='patient-b', name='PRIVATE OTHER NAME'),
        },
        test_aliases={
            'alt': TestAliasRecord(
                id='alt',
                name='ALT',
                aliases=['SGPT', 'Alanine Aminotransferase'],
                conversions=[],
                evidence=evidence,
            ),
            'fbs': TestAliasRecord(
                id='fbs',
                name='FBS',
                aliases=['Fasting Blood Sugar'],
                conversions=[
                    Conversion(
                        test_id='fbs',
                        from_unit='mmol/L',
                        to_unit='mg/dL',
                        multiplier='20',
                        offset='0',
                        evidence=evidence,
                    )
                ],
                evidence=evidence,
            ),
        },
        medical_glossary={
            'alt': GlossaryEntry(
                test_id='alt',
                test_name='ALT',
                simple_explanation='ALT is a liver enzyme.',
                low_meaning='Low ALT is rarely concerning.',
                high_meaning='High ALT can show liver stress.',
                evidence=evidence,
            ),
            'fbs': GlossaryEntry(
                test_id='fbs',
                test_name='FBS',
                simple_explanation='FBS measures fasting blood sugar.',
                low_meaning='Low FBS means less blood fuel.',
                high_meaning='High FBS means extra glucose in blood.',
                evidence=evidence,
            ),
        },
        reference_ranges=[
            ReferenceRange(
                id='alt-range',
                test_id='alt',
                unit='U/L',
                low='10',
                high='45',
                evidence=evidence,
            ),
            ReferenceRange(
                id='fbs-range',
                test_id='fbs',
                unit='mg/dL',
                low='100',
                high='200',
                evidence=evidence,
            ),
        ],
        urgent_thresholds=[
            UrgentThreshold(
                id='fbs-urgent',
                test_id='fbs',
                unit='mg/dL',
                operator='>=',
                value='400',
                warning='URGENT VALUE: Critical high sugar. See a doctor today.',
                evidence=evidence,
            )
        ],
        safety_rules={
            'SR-001': SafetyRule(
                id='SR-001',
                category='Privacy',
                rule_text='Strictly isolate patient records.',
                evidence=evidence,
            )
        },
    )


@pytest.fixture
def make_report(evidence):
    def factory(test='ALT', value='45', unit='U/L', patient_id='patient-a', report_id='report-a', **kwargs):
        return Report(
            id=report_id,
            patient_id=patient_id,
            measurements=[
                Measurement(
                    id='m1',
                    test=test,
                    value=value,
                    unit=unit,
                    evidence=evidence,
                )
            ],
            **kwargs,
        )

    return factory
