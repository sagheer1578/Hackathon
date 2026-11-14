"""Enterprise flat-styled clinical PDF report generator using ReportLab."""
from html import escape
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from .models import Analysis, Patient, Report


STATUS_HEX = {
    'Normal': '#15803d',
    'Low': '#b45309',
    'High': '#b45309',
    'Urgent': '#b91c1c',
    'Cannot Be Classified': '#475569',
}


def generate_pdf(patient: Patient, report: Report, analysis: Analysis) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name='BrandHeader',
            fontName='Helvetica-Bold',
            fontSize=20,
            leading=25,
            textColor=colors.HexColor('#0f172a'),
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name='DocSubtitle',
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#0f766e'),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name='SectionTitle',
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=16,
            textColor=colors.HexColor('#0f172a'),
            spaceBefore=12,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name='ItemTitle',
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#1e293b'),
            spaceBefore=6,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name='BodyTextSmall',
            fontName='Helvetica',
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor('#334155'),
            spaceAfter=4,
            wordWrap='CJK',
        )
    )
    styles.add(
        ParagraphStyle(
            name='MonoSmall',
            fontName='Courier',
            fontSize=7.5,
            leading=10.5,
            textColor=colors.HexColor('#475569'),
            spaceAfter=4,
            wordWrap='CJK',
        )
    )
    styles.add(
        ParagraphStyle(
            name='UrgentBoxText',
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=12.5,
            textColor=colors.HexColor('#991b1b'),
            spaceAfter=2,
            wordWrap='CJK',
        )
    )

    def p(text: str, style: str = 'BodyTextSmall') -> Paragraph:
        return Paragraph(escape(str(text)).replace('\n', '<br/>'), styles[style])

    age_str = str(report.age_at_report) if report.age_at_report is not None else 'Not provided'
    sex_str = report.sex_at_report
    if report.demographics_overridden:
        age_str = f'{age_str} (user-supplied)'
        sex_str = f'{sex_str} (user-supplied)'
    orig_age_str = str(report.original_age_at_report) if report.original_age_at_report is not None else 'Not provided'
    orig_sex_str = report.original_sex_at_report
    report_date_str = str(report.report_date) if report.report_date else 'Not provided'

    story: list = [
        p('CityLab Diagnostics', 'BrandHeader'),
        p('PATIENT LABORATORY REPORT ANALYSIS & EXPLANATION', 'DocSubtitle'),
    ]

    # Patient & Report Metadata Card Table
    meta_rows = [
        [p('Patient Name'), p(patient.name), p('Patient ID'), p(patient.id)],
        [p('Age Used for Analysis'), p(age_str), p('Sex Used for Analysis'), p(sex_str)],
        [p('Original Report Date'), p(report_date_str), p('Generated (UTC)'), p(f'{analysis.generated_at:%Y-%m-%d %H:%M}')],
        [p('Report ID'), p(report.id), p('Knowledge Version'), p(f'{analysis.knowledge_version} ({analysis.knowledge_provenance})')],
    ]
    if report.demographics_overridden:
        meta_rows.insert(
            2,
            [p('Original Source Age'), p(orig_age_str), p('Original Source Sex'), p(orig_sex_str)],
        )
    meta_table = Table(meta_rows, colWidths=[95, 161, 95, 161], hAlign='LEFT')
    meta_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
                ('LEFTPADDING', (0, 0), (-1, -1), 7),
                ('RIGHTPADDING', (0, 0), (-1, -1), 7),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(meta_table)

    if report.synthetic or analysis.knowledge_provenance == 'synthetic':
        story.append(Spacer(1, 6))
        synth_table = Table(
            [
                [
                    p(
                        'SYNTHETIC DEMONSTRATION — Fictional sample patient and demonstration reference rules. '
                        'Not a real patient record or clinically validated guideline.',
                        'ItemTitle',
                    )
                ]
            ],
            colWidths=[512],
            hAlign='LEFT',
        )
        synth_table.setStyle(
            TableStyle(
                [
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fffbeb')),
                    ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#d97706')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 9),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 9),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(synth_table)

    # Summary counts
    story.append(p('1. Summary of Findings', 'SectionTitle'))
    counts = analysis.counts
    count_rows = [
        [p(h) for h in ['Total Tests', 'Normal', 'Low', 'High', 'Urgent', 'Cannot Be Classified']],
        [
            p(str(len(analysis.results))),
            p(str(counts.get('Normal', 0))),
            p(str(counts.get('Low', 0))),
            p(str(counts.get('High', 0))),
            p(str(counts.get('Urgent', 0))),
            p(str(counts.get('Cannot Be Classified', 0))),
        ],
    ]
    count_table = Table(count_rows, colWidths=[85, 75, 75, 75, 75, 127], hAlign='LEFT')
    count_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
                ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(count_table)

    # Urgent Warnings Box
    warnings = list(dict.fromkeys(w for r in analysis.results for w in r.warnings))
    if warnings:
        story.append(p('2. Urgent Warnings Requiring Prompt Attention', 'SectionTitle'))
        warn_rows = [[p(w, 'UrgentBoxText')] for w in warnings]
        warn_table = Table(warn_rows, colWidths=[512], hAlign='LEFT')
        warn_table.setStyle(
            TableStyle(
                [
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fef2f2')),
                    ('BOX', (0, 0), (-1, -1), 1.0, colors.HexColor('#dc2626')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 9),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 9),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(warn_table)

    # Detailed Results Table
    story.append(p('3. Detailed Laboratory Results', 'SectionTitle'))
    rows = [[p(h) for h in ['Test Name', 'Original Value', 'Converted / Eval', 'Reference Interval', 'Classification']]]
    for r in analysis.results:
        conv_str = f'{r.converted_value} {r.converted_unit}' if r.converted_value and r.converted_unit else '—'
        status_hex = STATUS_HEX.get(r.status, '#334155')
        status_para = Paragraph(
            f'<font color="{status_hex}"><b>{escape(r.status)}</b></font>',
            styles['BodyTextSmall'],
        )
        label = r.test
        if r.canonical_test_name and r.canonical_test_name.casefold() != r.test.casefold():
            label = f'{r.test} ({r.canonical_test_name})'
        rows.append(
            [
                p(label),
                p(f'{r.value} {r.unit}'.strip() or '—'),
                p(conv_str),
                p(r.reference),
                status_para,
            ]
        )

    results_table = Table(rows, colWidths=[125, 82, 85, 130, 90], repeatRows=1, hAlign='LEFT')
    results_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
                ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
                ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor('#e2e8f0')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(results_table)

    # Plain-Language Explanations, Conversions & Source Evidence
    story.append(p('4. Plain-Language Explanations, Conversions & Source Evidence', 'SectionTitle'))
    for r in analysis.results:
        block = [
            p(f'{r.test} — {r.status}', 'ItemTitle'),
            p(r.explanation or r.reason),
        ]
        if r.converted_value and r.converted_unit:
            block.append(p(f'Unit Conversion Applied: {r.value} {r.unit} -> {r.converted_value} {r.converted_unit}'))
        for line in r.audit:
            block.append(p(f'Rule Audit: {line}'))
        for ev in r.evidence:
            block.append(p(f'Source: {ev.file} ({ev.location})'))
            block.append(p(ev.excerpt, 'MonoSmall'))
        story.append(KeepTogether(block))

    # Missing Information & Unsupported Findings
    unclassified = [r for r in analysis.results if r.status == 'Cannot Be Classified']
    if unclassified or report.issues or report.age_at_report is None or report.sex_at_report == 'unknown':
        story.append(p('5. Missing Information, Unsupported Tests & Extraction Notes', 'SectionTitle'))
        if report.age_at_report is None or report.sex_at_report == 'unknown':
            missing = []
            if report.age_at_report is None:
                missing.append('age')
            if report.sex_at_report == 'unknown':
                missing.append('biological sex')
            story.append(
                p(
                    f'Missing Demographics: Patient {" and ".join(missing)} not provided. '
                    'No default age or sex was assumed.'
                )
            )
        for r in unclassified:
            story.append(p(f'Unclassified — {r.test}: {r.reason}'))
        for issue in report.issues:
            story.append(p(f'Extraction Note: {issue}'))

    # Doctor Questions
    if analysis.doctor_questions:
        story.append(p('6. Questions to Ask Your Doctor', 'SectionTitle'))
        for idx, q in enumerate(analysis.doctor_questions, 1):
            story.append(p(f'{idx}. {q}'))

    # Educational Disclaimer
    story.append(Spacer(1, 10))
    disclaimer_table = Table([[p(analysis.disclaimer)]], colWidths=[512], hAlign='LEFT')
    disclaimer_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#cbd5e1')),
                ('LEFTPADDING', (0, 0), (-1, -1), 9),
                ('RIGHTPADDING', (0, 0), (-1, -1), 9),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(disclaimer_table)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(48, 26, f'CityLab Diagnostics | Confidential — Authorized Patient ID: {patient.id}')
        canvas.drawRightString(564, 26, f'Page {doc.page}')
        canvas.restoreState()

    SimpleDocTemplate(
        output,
        pagesize=(612, 792),
        leftMargin=50,
        rightMargin=50,
        topMargin=42,
        bottomMargin=46,
        title='CityLab Diagnostics Laboratory Report Explanation',
        author='CityLab Diagnostics',
    ).build(story, onFirstPage=footer, onLaterPages=footer)

    return output.getvalue()
