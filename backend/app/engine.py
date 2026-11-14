"""Deterministic medical rules engine — sole authority for test classification."""
from collections import Counter
from decimal import Decimal, InvalidOperation
from .models import Analysis, Conversion, Database, ReferenceRange, Report, Result


def normalize(text: str) -> str:
    return ' '.join(text.casefold().split())


def fmt_dec(value: Decimal) -> str:
    rendered = format(value, 'f')
    if '.' in rendered:
        rendered = rendered.rstrip('0').rstrip('.')
    return rendered or '0'


def demographic_match(rule, report: Report) -> bool | None:
    """Return False if definitely excluded, None if required demographics are missing, True if matched."""
    if rule.sex is not None and report.sex_at_report != 'unknown' and rule.sex != report.sex_at_report:
        return False

    age = report.age_at_report
    if age is not None:
        if rule.age_min is not None and (
            age < rule.age_min or (age == rule.age_min and not rule.age_min_inclusive)
        ):
            return False
        if rule.age_max is not None and (
            age > rule.age_max or (age == rule.age_max and not rule.age_max_inclusive)
        ):
            return False

    if rule.sex is not None and report.sex_at_report == 'unknown':
        return None
    if (rule.age_min is not None or rule.age_max is not None) and age is None:
        return None
    return True


def _missing_demographic_fields(rule, report: Report) -> tuple[bool, bool]:
    missing_age = (rule.age_min is not None or rule.age_max is not None) and report.age_at_report is None
    missing_sex = rule.sex is not None and report.sex_at_report == 'unknown'
    return missing_age, missing_sex


def converted(
    value: Decimal,
    unit: str,
    target: str,
    test_id: str,
    conversions: list[Conversion],
) -> tuple[Decimal | None, Conversion | None]:
    if unit == target:
        return value, None
    matches = [
        c
        for c in conversions
        if c.test_id == test_id and c.from_unit == unit and c.to_unit == target
    ]
    if len(matches) != 1:
        return None, None
    rule = matches[0]
    return value * rule.multiplier + rule.offset, rule


def format_interval(rule: ReferenceRange) -> str:
    low = fmt_dec(rule.low) if rule.low is not None else '-infinity'
    high = fmt_dec(rule.high) if rule.high is not None else 'infinity'
    return f"{'[' if rule.low_inclusive else '('}{low}, {high}{']' if rule.high_inclusive else ')'} {rule.unit}"


def _build_doctor_questions(results: list[Result], counts: dict[str, int]) -> list[str]:
    questions: list[str] = []
    urgent_results = [r for r in results if r.status == 'Urgent']
    abnormal_results = [r for r in results if r.status in ('High', 'Low')]
    unclassified = [r for r in results if r.status == 'Cannot Be Classified']

    for r in urgent_results[:2]:
        label = r.canonical_test_name or r.test
        questions.append(
            f'My {label} result was {r.value} {r.unit} and flagged as urgent—do I need immediate testing or care today?'
        )
    for r in abnormal_results:
        if len(questions) >= 3:
            break
        label = r.canonical_test_name or r.test
        questions.append(
            f'My {label} was {r.value} {r.unit} ({r.status.lower()} compared to {r.reference})—what factors could explain this for me?'
        )

    if urgent_results or abnormal_results:
        for candidate in [
            'Should any of these measurements be repeated or followed up with additional lab tests?',
            'Could fasting status, hydration, timing, or current medications have affected these results?',
            'What next steps or timeline do you recommend for reviewing these numbers together?',
        ]:
            if len(questions) < 5:
                questions.append(candidate)
    elif counts['Cannot Be Classified'] > 0:
        missing_demo = any('age' in r.reason.casefold() or 'sex' in r.reason.casefold() for r in unclassified)
        if missing_demo:
            questions.append(
                'Can we confirm my age and biological sex on file so the correct reference ranges can be applied?'
            )
        questions.extend(
            [
                'Some tests could not be matched to standard CityLab reference ranges—how should we interpret those values?',
                'Are any measurement units or repeat tests needed to clarify the unclassified items on this report?',
            ]
        )
    else:
        questions.extend(
            [
                'All classified measurements fell within documented intervals—how often should I repeat routine screening?',
                'Are there any symptoms or personal history factors we should consider alongside these normal numbers?',
                'Do I need any additional follow-up labs before my next routine visit?',
            ]
        )
    return questions[:5]


def analyze(report: Report, db: Database) -> Analysis:
    alias_index: dict[str, list] = {}
    for test in db.test_aliases.values():
        keys = {normalize(a) for a in [test.name, *test.aliases]}
        for key in keys:
            alias_index.setdefault(key, []).append(test)

    conversions = db.all_conversions()
    canonical_counts: Counter[str] = Counter()
    for m in report.measurements:
        matches = alias_index.get(normalize(m.test), [])
        canonical_counts[matches[0].id if len(matches) == 1 else normalize(m.test)] += 1

    results: list[Result] = []
    for m in report.measurements:
        out = Result(
            measurement_id=m.id,
            test=m.test,
            value=m.value,
            unit=m.unit,
            evidence=[m.evidence],
        )
        results.append(out)

        def fail(reason: str) -> None:
            out.status = 'Cannot Be Classified'
            out.reason = reason
            out.explanation = reason

        if m.issue:
            fail(m.issue)
            continue

        try:
            raw_value = Decimal(m.value)
            if not raw_value.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            fail('Invalid or ambiguous numeric value. A single finite number is required.')
            continue

        if not m.unit:
            fail('Measurement unit is missing.')
            continue

        if not db.reviewed or db.knowledge_provenance == 'organizer_unreviewed' or not db.test_aliases:
            fail('No reviewed medical corpus is installed. No clinical classification was attempted.')
            continue
        if db.knowledge_provenance == 'synthetic' and not report.synthetic:
            fail(
                'Synthetic demonstration reference rules cannot be applied to a non-synthetic patient report. '
                'Reviewed clinical reference rules are required.'
            )
            continue

        matched_tests = alias_index.get(normalize(m.test), [])
        if not matched_tests:
            fail(f'"{m.test}" is not covered in the CityLab reference sheets (cannot be classified from the files).')
            continue
        if len(matched_tests) > 1:
            fail(f'Ambiguous test alias "{m.test}" matches multiple definitions and requires clinical review.')
            continue

        test = matched_tests[0]
        glossary = db.get_glossary_for_test(test.id)
        out.canonical_test_id = test.id
        out.canonical_test_name = test.name
        out.evidence.append(test.evidence)
        if normalize(m.test) == normalize(test.name):
            out.audit.append(f'Matched canonical test {test.name} ({test.id}).')
        else:
            out.audit.append(f'Documented alias resolution: "{m.test}" -> {test.name} ({test.id}).')

        duplicate = canonical_counts[test.id] > 1
        recorded_conversions: set[tuple[str, str]] = set()

        def record_conversion(conv: Conversion | None, new_val: Decimal) -> None:
            if conv and (conv.from_unit, conv.to_unit) not in recorded_conversions:
                recorded_conversions.add((conv.from_unit, conv.to_unit))
                out.converted_value = fmt_dec(new_val)
                out.converted_unit = conv.to_unit
                out.audit.append(
                    f'Unit conversion ({test.name}): {fmt_dec(raw_value)} {m.unit} * {fmt_dec(conv.multiplier)}'
                    f' + {fmt_dec(conv.offset)} = {fmt_dec(new_val)} {conv.to_unit}.'
                )
                out.evidence.append(conv.evidence)

        urgent_uncertain = False
        urgent_direction: str | None = None
        for u_rule in db.get_urgent_for_test(test.id):
            applies = demographic_match(u_rule, report)
            if applies is False:
                continue
            v_conv, conv = converted(raw_value, m.unit, u_rule.unit, test.id, conversions)
            if applies is None or v_conv is None:
                urgent_uncertain = True
                continue
            record_conversion(conv, v_conv)
            hit = {
                '<': v_conv < u_rule.value,
                '<=': v_conv <= u_rule.value,
                '>': v_conv > u_rule.value,
                '>=': v_conv >= u_rule.value,
            }[u_rule.operator]
            out.audit.append(
                f'Urgent rule {u_rule.id}: {fmt_dec(v_conv)} {u_rule.unit} {u_rule.operator} '
                f'{fmt_dec(u_rule.value)} {u_rule.unit} -> {hit}.'
            )
            out.evidence.append(u_rule.evidence)
            if hit:
                out.warnings.append(u_rule.warning)
                if u_rule.operator in ('<', '<='):
                    urgent_direction = 'low'
                elif u_rule.operator in ('>', '>='):
                    urgent_direction = 'high'

        candidates = [
            r
            for r in db.get_ranges_for_test(test.id)
            if demographic_match(r, report) is not False
        ]
        matched_ranges: list[tuple[ReferenceRange, Decimal, Conversion | None]] = []
        missing_age = False
        missing_sex = False
        unsupported_unit = False

        for r_rule in candidates:
            demo_ok = demographic_match(r_rule, report)
            if demo_ok is None:
                m_age, m_sex = _missing_demographic_fields(r_rule, report)
                missing_age = missing_age or m_age
                missing_sex = missing_sex or m_sex
                continue
            v_conv, conv = converted(raw_value, m.unit, r_rule.unit, test.id, conversions)
            if v_conv is None:
                unsupported_unit = True
            else:
                matched_ranges.append((r_rule, v_conv, conv))

        direction_note = ''
        if duplicate:
            fail('Repeated measurements for the same test in one report require review; no value was silently selected.')
        elif missing_age or missing_sex:
            if missing_age and missing_sex:
                fail('Age and biological sex at the time of the report are required to select a reference range; please provide both.')
            elif missing_age:
                fail('Age at the time of the report is required to select a reference range; please provide patient age.')
            else:
                fail('Biological sex at the time of the report is required to select a reference range; please provide patient sex.')
        elif len(matched_ranges) > 1:
            fail('Conflicting or overlapping reference ranges require review.')
        elif not matched_ranges:
            fail(
                f'Unit "{m.unit}" is unsupported for {test.name} with no documented conversion.'
                if unsupported_unit
                else 'No reference range matches this test and the available patient demographics.'
            )
        else:
            r_rule, v_conv, conv = matched_ranges[0]
            record_conversion(conv, v_conv)
            out.reference = format_interval(r_rule)
            out.evidence.append(r_rule.evidence)
            is_low = r_rule.low is not None and (
                v_conv < r_rule.low or (v_conv == r_rule.low and not r_rule.low_inclusive)
            )
            is_high = r_rule.high is not None and (
                v_conv > r_rule.high or (v_conv == r_rule.high and not r_rule.high_inclusive)
            )
            out.status = 'Low' if is_low else 'High' if is_high else 'Normal'
            comparator = 'below' if is_low else 'above' if is_high else 'within'
            out.reason = f'{fmt_dec(v_conv)} {r_rule.unit} is {comparator} the documented interval {out.reference}.'
            out.audit.append(f'Reference rule {r_rule.id}: {out.reason}')
            if glossary:
                parts = [glossary.simple_explanation]
                if is_low and glossary.low_meaning:
                    direction_note = glossary.low_meaning
                    parts.append(glossary.low_meaning)
                elif is_high and glossary.high_meaning:
                    direction_note = glossary.high_meaning
                    parts.append(glossary.high_meaning)
                parts.append(out.reason)
                out.explanation = ' '.join(parts)
            else:
                out.explanation = out.reason

        if urgent_uncertain:
            out.audit.append(
                'One or more urgent rules could not be evaluated because demographics or a documented unit conversion are missing.'
            )
            out.warnings.append(
                'Urgency assessment is incomplete because required demographics or a documented conversion are missing.'
            )

        urgent_hits = [
            w
            for w in out.warnings
            if w != 'Urgency assessment is incomplete because required demographics or a documented conversion are missing.'
        ]
        if urgent_hits:
            out.status = 'Urgent'
            out.reason = 'A documented urgent threshold is met. ' + out.reason
            parts = []
            if glossary:
                parts.append(glossary.simple_explanation)
                if not direction_note:
                    if urgent_direction == 'low' and glossary.low_meaning:
                        parts.append(glossary.low_meaning)
                    elif urgent_direction == 'high' and glossary.high_meaning:
                        parts.append(glossary.high_meaning)
                else:
                    parts.append(direction_note)
            parts.append(out.reason)
            parts.extend(urgent_hits)
            out.explanation = ' '.join(p for p in parts if p).strip()

    counts = {
        status: sum(r.status == status for r in results)
        for status in ['Normal', 'Low', 'High', 'Urgent', 'Cannot Be Classified']
    }
    questions = _build_doctor_questions(results, counts)
    return Analysis(
        report_id=report.id,
        patient_id=report.patient_id,
        knowledge_version=db.knowledge_version,
        knowledge_provenance=db.knowledge_provenance,
        results=results,
        counts=counts,
        doctor_questions=questions,
        ai_enhanced=False,
    )
