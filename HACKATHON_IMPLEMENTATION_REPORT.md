# Tech Fusion '26 — Implementation Report
## CityLab Diagnostics Medical Lab Report Explainer (Problem Statement B)

---

## 1. Executive Summary

We built a complete, verified, minimal-enterprise **Medical Lab Report Explainer** for CityLab Diagnostics strictly inside `c:\Users\saqlain\Desktop\hack`. The system separates **deterministic medical classification** (Python `Decimal` rules engine) from **natural-language explanation** (grounded LLM adapter with deterministic fallback), ensuring that no language model can ever invent ranges, compute unit conversions, diagnose diseases, or override critical clinical thresholds.

All state and normalized medical rules are stored in a **9-file atomic JSON database** (`data/`) with `filelock` concurrency control and Pydantic v2 cross-collection validation. On the latest verification run after our final edits, all **78 automated pytest tests passed (0 failed)**, **92 literal evidence citations** were verified against the original corpus files, the TypeScript/Vite frontend compiled cleanly (`0` errors, `0` gradients), and live server measurements confirmed end-to-end health, chat, and PDF export functionality.

---

## 2. Actual Corpus Files Inspected & Utilized

Because `c:\Users\saqlain\Desktop\hack` started empty with no organizer-supplied files inside it, we authored and ingested a self-consistent 9-file CityLab Diagnostics corpus in [`corpus/`](corpus/) covering every clinical and edge-case requirement in Problem Statement B:

| File | Purpose | Key Contents |
|---|---|---|
| `corpus/1_lab_safety_rules.md` | Clinical & privacy governance (`CLD-SOP-001`) | 12 numbered safety rules (`SR-001`–`SR-012`) covering strict patient isolation, non-diagnosis, no guessing demographics, untrusted document handling, and urgent escalation |
| `corpus/2_medical_glossary.md` | Canonical tests, aliases, glossary, conversions (`CLD-GLS-002`) | 17 canonical tests (`alt`, `ast`, `fbs`, `hba1c`, `total_cholesterol`, `hdl`, `ldl`, `triglycerides`, `creatinine`, `bun`, `tsh`, `hemoglobin`, `wbc`, `platelets`, `potassium`, `sodium`, `urine_protein`), documented aliases (`SGPT`, `SGOT`, `Hb`, `K+`, etc.), Class-8 plain-language text, and 8 test-specific unit conversions |
| `corpus/3_dangerous_urgent_values.md` | Critical threshold protocol (`CLD-URG-003`) | 12 independent urgent threshold rules across glucose, potassium, sodium, hemoglobin, platelets, WBC, creatinine, and ALT |
| `corpus/4_reference_ranges_chemistry.md` | Chemistry, lipid & liver intervals (`CLD-RNG-004`) | 13 age/sex-aware reference rules using inclusive `[]` and exclusive `()` bounds |
| `corpus/5_reference_ranges_hematology_endocrine_renal.md` | Hematology, endocrine & renal intervals (`CLD-RNG-005`) | 13 age/sex-aware reference rules (e.g., sex-specific Hemoglobin & Creatinine, age-bracketed TSH) |
| `corpus/6_report_patient_p001_arjun_mehta.md` | Patient report (`patient-p001`) | Exact boundary tests (`SGPT 45 U/L`, `Total Cholesterol 200 mg/dL`), `mmol/L` FBS conversion, `umol/L` Creatinine conversion, elevated TSH, low HDL |
| `corpus/7_report_patient_p002_fatima_khan_urgent.md` | Patient report (`patient-p002`) | Urgent `Fasting Blood Sugar` (`22.5 mmol/L -> 405 mg/dL`), urgent `Potassium` (`6.3 mmol/L`), low `Hb` (`10.2 g/dL`) |
| `corpus/8_report_patient_p003_missing_demographics.md` | Patient report (`patient-p003`) | Omitted `Age` and `Sex: unknown`; tests refusal to guess while flagging urgent `Serum Potassium` (`6.4 mmol/L`) |
| `corpus/9_report_patient_p004_noisy_edge_cases.md` | Noisy archive report (`patient-p004`) | 200+ boilerplate lines, adversarial prompt injection, unsupported `Serum Ferritin`, missing unit on `WBC`, `<0.01` on `TSH`, duplicate `ALT` + `SGPT` |

---

## 3. Completed Features vs. Incomplete / Environment-Limited Items

### Completed & Verified
- Structured markdown/CSV/TXT/JSON/text-PDF report ingestion with boilerplate noise stripping, injection detection, and exact line/page coordinates.
- Corpus parser (`backend/app/corpus_parser.py`) with literal excerpt verification (`verify_corpus_evidence`).
- 9-file atomic JSON repository (`backend/app/storage.py`) with `filelock` and fail-closed corruption guards.
- Deterministic `Decimal` medical rules engine (`backend/app/engine.py`).
- Provider-independent `LLMAdapter` supporting Groq and free-tier OpenRouter (`:free` enforced), plus safety validation and deterministic fallback (`backend/app/ai.py`).
- FastAPI backend (`backend/app/main.py`) with Bearer token patient isolation, rate limiting (120 req/min/host), upload validation, interactive session demographic updates (`/demographics`), and SPA serving.
- Server-side ReportLab multi-page PDF generator (`backend/app/pdf.py`) containing all 17 required clinical sections.
- Enterprise minimal zero-gradient React + TypeScript + Tailwind frontend (`frontend/src/main.tsx`), compiled into `frontend/dist/`.
- 78 automated pytest assertions passing (`0` failures).
- Full Dockerfiles, Nginx config, `.dockerignore`, `.env.example`, and `docker-compose.yml`.

### Incomplete / Not Executed Due to Host Environment
- **Live Docker Compose Runtime Execution:** Docker Desktop / `docker` CLI is not installed on the evaluation Windows host, so `docker compose up --build` could not be executed locally; container definitions were authored and checked against local runtime configuration instead.
- **External Cloud Hosting & Live Remote LLM Calls:** No external hosting (Vercel/Render/Railway) or external Groq/OpenRouter API keys were configured in the local sandbox; AI grounding, safety rejection, and fallback paths were tested deterministically and via schema validation unit tests (`LLM_PROVIDER=disabled` by default).

---

## 4. System Architecture

```text
+----------------------------------------------------------------------+
|                React + TypeScript + Tailwind UI (Flat)               |
|  Login / Demo Switcher | Dashboard | Reports | Chat | PDF Download   |
+----------------------------------+-----------------------------------+
                                   | HTTP / Bearer Token (/api/*)
+----------------------------------v-----------------------------------+
|                        FastAPI Application                           |
|  BodyLimit (8 MiB) | Security Headers | Rate Limiter | Auth Guard    |
+-------+-------------------------+--------------------------+---------+
        |                         |                          |
+-------v--------+      +---------v---------+      +---------v---------+
| Corpus &       |      | Deterministic     |      | Grounded AI /     |
| Report Parser  |      | Rules Engine      |      | Safety Validator  |
| (ingestion.py) |      | (engine.py)       |      | (ai.py)           |
+-------+--------+      +---------+---------+      +---------+---------+
        |                         |                          |
+-------v-------------------------v--------------------------v---------+
|              9-File Atomic JSON Repository (storage.py)              |
|  patients | reports | report_metadata | test_aliases | safety_rules  |
|  reference_ranges | urgent_thresholds | medical_glossary | analyses  |
+----------------------------------------------------------------------+
                                   |
                        +----------v----------+
                        | ReportLab PDF Gen   |
                        | (pdf.py)            |
                        +---------------------+
```

---

## 5. AI Model and Retrieval Strategy

- **Bounded Evidence Retrieval (No Blind Whole-Corpus Vector Search):** In `backend/app/ai.py`, incoming user questions are first screened by `SAFETY_INPUT_RE` for diagnosis requests, dosage/treatment queries, cross-patient access attempts, and prompt-injection patterns. Next, `_match_relevant_results()` tokenizes the question and matches against canonical test names, original test strings, and documented aliases in `test_aliases.json`.
- **Provider-Independent Adapter (`LLMAdapter`):** Supports `groq` (`https://api.groq.com/openai/v1/chat/completions`) and `openrouter` (`https://openrouter.ai/api/v1/chat/completions`, strictly requiring `:free` model suffixes), with `8.0s` timeouts, 1 retry on HTTP `429`/`>=500`, and `response_format: {"type": "json_object"}`.
- **Safety Output Validator (`validate_ai_text` & `GroundedAnswer`):** Rejects outputs containing diagnosis claims, treatment prescriptions, fabricated `evidence_ids`, or other patient IDs, and guarantees urgent warnings are preserved verbatim. Whenever `LLM_PROVIDER=disabled` or an external API fails, the system serves the deterministic plain-language explanation compiled from `medical_glossary.json` and `engine.py`.

---

## 6. Deterministic Rules-Engine Design

Implemented in [`backend/app/engine.py`](backend/app/engine.py):
1. **Exact Decimal Arithmetic:** Parses measurement values, conversion multipliers/offsets, age boundaries, and reference limits via `decimal.Decimal`, eliminating binary floating-point rounding drift.
2. **Documented Alias Resolution:** Builds a casefolded whitespace-normalized index from `test_aliases.json`. Unknown tests return `Cannot Be Classified` (`"not covered in the CityLab reference sheets"`). Ambiguous multi-match aliases also return `Cannot Be Classified`.
3. **Test-Specific Unit Conversion:** Converts units only when a single `(test_id, from_unit, to_unit)` entry exists in `test_aliases.json` (e.g., `FBS: mmol/L -> mg/dL * 18`; `Creatinine: umol/L -> mg/dL * 0.0113`), logging the exact formula into `result.audit`.
4. **Demographic Matching Without Guessing:** `demographic_match()` returns `False` when any known attribute disqualifies a rule, `None` when a required demographic (`age` or `sex`) is missing/unknown, and `True` only when satisfied.
5. **Independent Urgent Thresholds:** `urgent_thresholds.json` rules evaluate independently of reference range availability. Even if a patient lacks demographics (`patient-p003`) or has duplicate entries, triggered urgent rules force `status = "Urgent"` and surface the critical warning.
6. **Boundary Convention:** Supports both inclusive (`[`, `]`) and exclusive (`(`, `)`) bounds for both reference values and age intervals.

---

## 7. JSON Database Structure and Persistence

Implemented in [`backend/app/storage.py`](backend/app/storage.py) using 9 separate JSON files under `DATA_DIR`:
1. `patients.json`
2. `reports.json`
3. `reference_ranges.json`
4. `test_aliases.json`
5. `urgent_thresholds.json`
6. `medical_glossary.json`
7. `safety_rules.json`
8. `analysis_results.json`
9. `report_metadata.json`

Every mutation acquires `FileLock('.storage.lock', timeout=10)`, reads current state, validates cross-collection foreign keys across the unified `Database` Pydantic model, computes deterministic `knowledge_version` SHA-256 hashes, and atomically writes modified files via `tempfile.mkstemp` + `os.fsync` + `os.replace`. Corrupted or schema-mismatched JSON fails closed (`StorageError`) without overwriting disk files.

---

## 8. Frontend Design and UI Decisions

Implemented in [`frontend/src/main.tsx`](frontend/src/main.tsx) and [`frontend/src/styles.css`](frontend/src/styles.css):
- **Minimalist Flat Enterprise Aesthetic:** Neutral `#f8fafc` workspace, `#ffffff` cards, `#0f172a` slate-navy typography, restrained `#0f766e` teal primary accent, and `1px` `#e2e8f0` borders.
- **Strict Zero-Gradient Compliance:** Verified across all `.ts`, `.tsx`, `.css`, and `.py` source files that zero `gradient`, `backdrop-filter`, or glowing `box-shadow` directives exist.
- **Unified Single-Workspace Flow:** Sidebar navigation (`Dashboard`, `Patient Reports`, `Report Analysis`, `AI Assistant`, `Report Downloads`), click-to-filter metric cards, expandable per-test Evidence & Audit drawers, inline interactive demographic entry for missing-demographic reports, and one-click PDF downloads.

---

## 9. Patient Privacy and Safety Handling

- **Backend-Enforced Bearer Authorization:** Tokens (>= 32 chars) are SHA-256 hashed and compared via constant-time `hmac.compare_digest`. Every report, analysis, demographic update, chat message, and PDF download verifies `report.patient_id == authorized_patient`, returning `404` for unauthorized IDs without disclosing record existence.
- **Response & Storage Hardening:** Sets `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `X-Frame-Options: DENY`. Enforces an 8 MiB upload limit and 120 req/min rate limiting. API keys are read solely from environment variables and never persisted in JSON.
- **Prompt-Injection Defense:** Document ingestion detects and neutralizes instruction-override strings (`prompt_injection_detected=True`), while `ai.py` blocks diagnosis, medication, and cross-patient queries prior to any LLM invocation.

---

## 10. Automated Testing Results

Executed after final implementation edits via `.\.venv\Scripts\pytest.exe -v` and `npm.cmd run build`:

| Suite / Check | Command | Result | Details |
|---|---|---|---|
| Rules Engine (`tests/test_engine.py`) | `pytest -v` | **41 passed, 0 failed** | Exact boundaries (`45 U/L`, `200 mg/dL`, `400 mg/dL`), aliases, conversions, inclusive/exclusive bounds, demographics, duplicates, urgent overrides, all 4 real CityLab corpus patients |
| Ingestion & 9-File JSON Storage (`tests/test_ingestion_storage.py`) | `pytest -v` | **16 passed, 0 failed** | 15,000-line noisy doc + injection neutralization, PDF ingestion, synonym headers (`Test Name`/`Units`/`Gender: F`), 9-file atomic persistence, 8-thread concurrent writes, corruption fail-closed, corpus integrity + fabricated excerpt rejection |
| API, Auth, AI Safety & PDF (`tests/test_api_ai_pdf.py`) | `pytest -v` | **21 passed, 0 failed** | Workflow & restart persistence, cross-patient 404 denial, invalid credentials (`401`), upload idempotency, multi-page PDF (>3 pages), chat safety refusals, AI validator, demographic update endpoint, rate limit (`429`), SPA serving |
| **Total Automated Pytest Suite** | `.\.venv\Scripts\pytest.exe -v` | **78 passed, 0 failed** | Executed in `5.32s` |
| Corpus Evidence Verification | `cli.py verify-evidence corpus` | **92 citations verified** | Every rule, range, alias, conversion, glossary, and urgent excerpt matched verbatim in `corpus/` |
| Frontend Build | `npm.cmd run build` | **Passed (0 errors)** | `tsc -b && vite build` completed in `4.07s` (`dist/assets/index-BetjfdU6.js`, `279.40 kB`) |

---

## 11. Edge-Case Coverage Summary

Covered in both automated regression tests and live corpus patients:
- `SGPT` / `ALT` / `Alanine Aminotransferase` and `FBS` / `Fasting Blood Sugar` / `Hb` / `Potassium` aliases
- `mmol/L -> mg/dL` (glucose * 18) and `umol/L -> mg/dL` (creatinine * 0.0113) conversions with audit trails
- Exact numeric boundaries (`45 U/L`, `200 mg/dL`, `400 mg/dL`) and exclusive limits (`<`, `>`, `(low, high)`)
- Missing age/sex (`patient-p003`) & exact age cutoffs (`18`, `17.999`, `65`, `65.001`)
- Overlapping ranges & conflicting aliases rejected (`Cannot Be Classified`)
- Unsupported assays (`Serum Ferritin`), missing units (`WBC`), bounded strings (`<0.01`), `NaN`/`Infinity`, and duplicate measurements in one report
- Independent urgent alerts firing even when normal ranges cannot be selected
- 200+ / 15,000+ line noisy documents and adversarial prompt-injection strings neutralized
- Cross-patient endpoint access denied with `404` and zero PII leakage

---

## 12. Measured Performance

Observed directly on the local Windows Python 3.13 / FastAPI runtime after final edits:
- **Full 9-File Corpus Ingestion + 4-Report Analysis:** `126.30 ms`
- **Live Uvicorn PDF Generation & Download (`patient-p001`, 8 tests):** `136.10 ms` (`13,048` bytes, valid `%PDF-` header)
- **Pytest Full Regression Suite (78 test cases):** `5.32 s`
- **Frontend Production Bundle (`tsc -b && vite build`):** `4.07 s`

---

## 13. Known Issues and Limitations

1. **Text-Only PDF Support:** OCR is deliberately disabled; image-scanned PDFs require manual transcription or CSV/Markdown export.
2. **Prototype JSON Storage Concurrency:** Appropriate for single-node demos and small datasets; high-throughput clinical environments require an RDBMS.
3. **Docker Runtime Unverified Locally:** `docker` is absent on the Windows evaluation machine; Docker files are complete and ready for container-enabled hosts.
4. **LLM Provider Disabled by Default:** Runs in zero-dependency deterministic explanation mode until `LLM_PROVIDER`, `LLM_API_KEY`, and `LLM_MODEL` are supplied in `.env`.

---

## 14. Docker Instructions

```bash
cp .env.example .env
docker compose up --build
```
- UI served on `http://localhost:3000` (Nginx proxying `/api/` to `backend:8000`)
- Backend API exposed on `http://localhost:8000`
- Persistent JSON files stored in Docker named volume `citylab_json_data` mounted at `/app/data`

---

## 15. Live Deployment Status

- **Local Production-Bundled Server:** Verified via Uvicorn serving both the compiled React SPA (`/`) and FastAPI API (`/api/*`) cleanly.
- **External Cloud URL:** Not deployed externally during this offline/local workspace session; ready for immediate deployment via Docker Compose or Railway/Render/Vercel+Backend using the included Dockerfiles.

---

## 16. Demo Walkthrough for Judges

1. Start the server (`.\.venv\Scripts\uvicorn.exe backend.app.main:app --host 127.0.0.1 --port 8000`) and open `http://127.0.0.1:8000`.
2. **Boundary & Conversion Showcase (`patient-p001` — Arjun Mehta):** Click Arjun Mehta's card on the login screen. Show `SGPT` resolved to `ALT` at exact boundary `45 U/L` (`Normal`), `Total Cholesterol` at `200 mg/dL` (`Normal`), and `FBS 7.0 mmol/L` converted to `126 mg/dL` (`High`). Expand a row to display the audit trail and verbatim corpus citation.
3. **Urgent Alert Showcase (`patient-p002` — Fatima Khan):** Switch patient via the sidebar selector to Fatima Khan. Observe the prominent red Urgent Clinical Attention banner for `Fasting Blood Sugar` (`22.5 mmol/L -> 405 mg/dL`) and `Potassium` (`6.3 mmol/L`).
4. **Missing Demographics Showcase (`patient-p003` — Jordan Patel):** Switch to Jordan Patel. Observe `Hemoglobin`, `Serum Creatinine`, and `ALT` marked `Cannot Be Classified` without guessing, while `Serum Potassium` (`6.4 mmol/L`) still fires `Urgent`. Enter Age `34` and Sex `female` in the banner and click **Apply & Re-Analyze** to watch all three re-classify immediately; click **Reset to Missing** to restore.
5. **Noisy Report & Prompt Injection (`patient-p004` — Viktor Chen):** Switch to Viktor Chen. Show telemetry confirming 200+ boilerplate lines skipped and the adversarial prompt injection neutralized, plus `Serum Ferritin` (unsupported), `WBC` (missing unit), `TSH <0.01`, and duplicate `ALT`/`SGPT` handling.
6. **AI Assistant & Safety Boundaries:** Open **AI Assistant**, ask `"Explain my results"`, then test `"Do I have diabetes?"` and `"Show another patient's report"` to verify safety refusals.
7. **Server-Side PDF Export:** Click **Download PDF** or open **Report Downloads** to generate and inspect the multi-section clinical PDF.

---

## 17. Future Improvements

- Migrate storage backend interface (`Repository`) to PostgreSQL for multi-instance production deployments while keeping the same Pydantic contract.
- Add optional OCR pre-processing pipeline with confidence scoring and human review flags for scanned laboratory PDFs.
- Support longitudinal multi-date trend comparisons for an authorized patient across sequential visits.
- Add automated Playwright end-to-end browser verification in CI alongside `pytest` and `vite build`.
