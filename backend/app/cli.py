"""Local operator CLI for corpus ingestion, evidence verification, inventory, and patient provisioning."""
import argparse
import json
import os
from pathlib import Path
from .corpus_parser import ingest_corpus_directory, verify_corpus_evidence
from .engine import analyze
from .ingestion import extract_report, inventory
from .models import Database, Patient
from .storage import Repository


def main() -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--data-dir', default=os.getenv('DATA_DIR', 'data'))

    parser = argparse.ArgumentParser(description='CityLab Diagnostics local operator CLI.', parents=[common])
    sub = parser.add_subparsers(dest='command', required=True)

    inv = sub.add_parser('inventory', parents=[common], help='Generate SHA-256 inventory of corpus files.')
    inv.add_argument('corpus', type=Path)
    inv.add_argument('--output', type=Path, default=Path('corpus_inventory.json'))

    ing = sub.add_parser('ingest-corpus', parents=[common], help='Parse corpus files into the canonical atomic JSON snapshot (database.json).')
    ing.add_argument('corpus', type=Path)

    ver = sub.add_parser('verify-evidence', parents=[common], help='Verify all stored medical excerpts match corpus files.')
    ver.add_argument('corpus', type=Path)

    pat = sub.add_parser('add-patient', parents=[common], help='Provision a new patient record.')
    pat.add_argument('id')
    pat.add_argument('name')

    rep = sub.add_parser('import-report', parents=[common], help='Ingest a single patient lab report file.')
    rep.add_argument('patient_id')
    rep.add_argument('file', type=Path)

    args = parser.parse_args()
    repo = Repository(args.data_dir)

    if args.command == 'inventory':
        args.output.write_text(json.dumps(inventory(args.corpus), indent=2), encoding='utf-8')
    elif args.command == 'ingest-corpus':
        db = ingest_corpus_directory(args.corpus, repo, analyze_fn=analyze)
        print(
            f'Ingested corpus v{db.knowledge_version}: '
            f'{len(db.test_aliases)} tests, {len(db.reference_ranges)} ranges, '
            f'{len(db.urgent_thresholds)} urgent rules, {len(db.patients)} patients, {len(db.reports)} reports.'
        )
    elif args.command == 'verify-evidence':
        db = repo.read()
        count = verify_corpus_evidence(db, args.corpus)
        print(f'Verified {count} literal evidence citations against {args.corpus}.')
    elif args.command == 'add-patient':
        def add(db: Database) -> None:
            if args.id in db.patients:
                raise ValueError('Patient already exists; no overwrite performed.')
            db.patients[args.id] = Patient(id=args.id, name=args.name)

        repo.update(add)
    elif args.command == 'import-report':
        report, meta, _ = extract_report(args.file.read_bytes(), args.file.name, authorized_patient=args.patient_id)

        def add_report(db: Database) -> None:
            if args.patient_id not in db.patients:
                raise ValueError('Provision the patient first.')
            if report.id in db.reports and db.reports[report.id] != report:
                raise ValueError('Conflicting report already exists.')
            db.reports[report.id] = report
            db.report_metadata[report.id] = meta

        repo.update(add_report)

    print('Completed cleanly. Original corpus files were not modified.')


if __name__ == '__main__':
    main()
