# Tech Fusion '26 — Implementation Report
## CityLab Diagnostics Medical Lab Report Explainer (Problem Statement B)

---

## 1. Executive Summary

We built and hardened a minimal-enterprise **Medical Lab Report Explainer** workspace inside `C:\Users\saqlain\Desktop\hack`. The system separates **deterministic medical classification** (Python `Decimal` rules engine) from **natural-language explanation** (deterministic intent router + optional schema-validated LLM phrasing), ensuring that no language model can compute, alter, or invent numeric results, reference ranges, statuses, diagnoses, or treatment advice.

All state and normalized medical rules are stored in a **canonical atomic JSON snapshot (`data/database.json`)** with `filelock` concurrency control, duplicate-key rejection, fail-closed corruption handling, and non-destructive migration from the legacy 9-file layout. After the final code edits, **89 automated pytest tests passed (0 failed, 1 Starlette deprecation warning)**, **92 literal evidence citations** matched `corpus/` files verbatim, the TypeScript/Vite frontend compiled cleanly (`0` errors, zero CSS `gradient`/`backdrop-filter`/`box-shadow`), and live HTTP checks against `http://127.0.0.1:8001` verified health, served UI bundle content, all 4 sample persona assistant/demographics workflows, PDF downloads, and 5-endpoint cross-patient `404` isolation.

---

## 2. Corpus Provenance & Fixtures Used

Because `C:\Users\saqlain\Desktop\hack` started empty with no organizer-supplied files inside it, [`corpus/`](corpus/) holds a **self-authored synthetic demonstration corpus** (`knowledge_provenance: "synthetic"`). Matching excerpts against these files verifies **software fidelity to the loaded fixtures** — it does **not** represent clinical validation or external medical authority. Furthermore, `engine.py` refuses to classify uploaded non-synthetic patient reports (`synthetic=False`) against `synthetic` rules (`Cannot Be Classified`), and marks both UI views and PDFs with synthetic demonstration disclosures.

| File | Purpose | Key Contents (Synthetic Fixtures) |
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
- Structured markdown/CSV/TXT/JSON/text-PDF report ingestion with boilerplate noise stripping, injection detection, duplicate JSON key rejection, and exact line/page coordinates.
- Corpus parser (`backend/app/corpus_parser.py`) with synthetic provenance tracking (`knowledge_provenance: "synthetic"`) and literal excerpt verification (`verify_corpus_evidence`).
- Canonical atomic JSON snapshot repository (`backend/app/storage.py` writing `data/database.json`) with `FileLock`, duplicate-key rejection, fail-closed corruption guards, and one-time non-destructive migration preserving the legacy 9 `*.json` files.
- Deterministic `Decimal` medical rules engine (`backend/app/engine.py`) with synthetic-vs-real report isolation.
- Deterministic intent router, phrase-matched test resolution, validated report-scoped follow-up state (`active_measurement_ids` + `context_revision`), strict `StructuredAIResponse` (`extra='forbid'`), hardened numeric/status/diagnosis/treatment `validate_ai_text`, and provider-independent `LLMAdapter` (`backend/app/ai.py`).
- FastAPI backend (`backend/app/main.py`) with Bearer token patient isolation, rate limiting (120 req/min/host), demo allowlist (`DEMO_MODE`), upload `synthetic=False` enforcement, interactive session demographic updates/resets with original source preservation (`/demographics`), and SPA serving via `run_server.py` on `http://127.0.0.1:8001`.
- Server-side ReportLab PDF generator (`backend/app/pdf.py`) including `"SYNTHETIC DEMONSTRATION"` banner/notice when synthetic and explicit `Original Source Age`/`Sex` vs `(user-supplied)` demographic distinction.
- Enterprise minimal zero-gradient React + TypeScript + Tailwind frontend (`frontend/src/main.tsx`), compiled into `frontend/dist/`.
- **89 passed, 0 failed** automated `pytest` assertions + live HTTP acceptance checks across all 4 sample personas, PDFs, demographic updates, and cross-patient `404` isolation on `http://127.0.0.1:8001`.
- Dockerfiles, Nginx config, `.dockerignore`, `.env.example`, and `docker-compose.yml`.

### Incomplete / Not Executed Due to Host Environment
- **Live Docker Compose Runtime Execution:** Docker Desktop / `docker` CLI is not installed on this Windows host, so `docker compose up --build` was not executed locally.
- **Live External LLM API Calls:** No `LLM_API_KEY` is configured in the environment (`LLM_PROVIDER=disabled`, `ai_configured=false`); live external Groq or OpenRouter model responses are therefore **not verified**. AI validation, rejection of fabricated numbers/prescriptions, schema validation, and timeout/`429`/malformed-JSON fallbacks were tested with mocked payloads in `pytest`.
- **Live Chrome DevTools DOM Rendering Walkthrough:** The Chrome DevTools remote debugging socket (`DevToolsActivePort`) was not active on this Windows host during verification, so interactive mouse-click DOM layout, computed style checks in Chrome, and `375px` mobile viewport rendering were not directly inspected in a live Chrome window. Responsive styling (`styles.css` with `:focus-visible` and mobile media queries), built TypeScript/Vite compilation, zero gradients/shadows, and served HTML/JS/CSS asset contents were verified instead alongside live HTTP acceptance calls.

---

## 4. System Architecture

```text
+----------------------------------------------------------------------+
|                React + TypeScript + Tailwind UI (Flat)               |
|  Sample Cards | Collapsed Private Code | Report | Assistant | PDF    |
+----------------------------------+-----------------------------------+
                                   | HTTP / Bearer Token (/api/*)
+----------------------------------v-----------------------------------+
|               FastAPI Application (http://127.0.0.1:8001)            |
|  BodyLimit (8 MiB) | Security Headers | Rate Limiter | Auth Guard    |
+-------+-------------------------+--------------------------+---------+
        |                         |                          |
+-------v--------+      +---------v---------+      +---------v---------+
| Corpus &       |      | Deterministic     |      | Assistant Router  |
| Report Parser  |      | Rules Engine      |      | & AI Validator    |
| (ingestion.py) |      | (engine.py)       |      | (ai.py)           |
+-------+--------+      +---------+---------+      +---------+---------+
        |                         |                          |
+-------v-------------------------v--------------------------v---------+
|     Canonical Atomic JSON Snapshot: data/database.json (storage.py)  |
|       (One-time non-destructive migration from legacy 9 *.json)      |
+----------------------------------------------------------------------+
                                   |
                        +----------v----------+
                        | ReportLab PDF Gen   |
                        | (pdf.py)            |
                        +---------------------+
```

---

## 5. AI Model, Assistant Routing & Safety Strategy

- **Deterministic Intent Routing (`_route_intent`):** Incoming questions are first screened for cross-patient / prompt-injection patterns (`CROSS_PATIENT_RE`, `INJECTION_OR_BYPASS_RE`) and diagnosis or treatment requests (`DIAGNOSIS_RE`, `TREATMENT_RE`). Greetings, category queries (`list_normal`, `list_high`, `list_low`, `list_abnormal`, `list_urgent`, `list_unclassified`), `doctor_questions`, and `report_summary` are routed without colliding with specific test matches.
- **Contiguous Word-Boundary Phrase Matching (`match_tests_in_question`):** Replaces noisy word-overlap scoring (which previously confused words like `"high"`/`"it"` with `"HDL"`). Only full contiguous alias/name phrases excluding generic words match tests cleanly, while longest-span matching prevents sub-phrase collisions.
- **Validated Follow-Up Context (`active_measurement_ids` + `context_revision`):** Multi-turn follow-ups (`"Is it high?"`, `"What is its reference range?"`) keep focus on the active test only when client-supplied `active_measurement_ids` all belong to the authorized report (otherwise `422`) and `context_revision` matches `compute_analysis_revision(report, analysis)` (stale demographic context clears prior topic and returns `intent='clarification'`).
- **Strict Structured AI Output + Text Validator (`StructuredAIResponse` & `validate_ai_text`):** When an external `groq` or `:free` `openrouter` provider is configured, `LLMAdapter.select_structured` enforces `StructuredAIResponse` (`extra='forbid'`), allowing the model only to select valid report `measurement_ids` and whitelisted `explanation_keys` while the backend renders every number, unit conversion, readable reference range, classification, and source disclosure. `validate_ai_text` rejects invented values, numbers copied onto the wrong test, fabricated reference intervals, wrong statuses, omitted urgent warnings, diagnoses, and treatment prescriptions. Whenever `LLM_PROVIDER=disabled` or an upstream API fails, the system stays safely in deterministic mode and discloses in the UI that AI assistance is unavailable.

---

## 6. Deterministic Rules-Engine Design

Implemented in [`backend/app/engine.py`](backend/app/engine.py):
1. **Exact Decimal Arithmetic:** Parses measurement values, conversion multipliers/offsets, age boundaries, and reference limits via `decimal.Decimal`, eliminating binary floating-point rounding drift.
2. **Documented Alias Resolution:** Builds a casefolded whitespace-normalized index from the `test_aliases` collection in `database.json`. Unknown tests return `Cannot Be Classified` (`"not covered in the CityLab reference sheets"`). Ambiguous multi-match aliases also return `Cannot Be Classified`.
3. **Test-Specific Unit Conversion:** Converts units only when a single `(test_id, from_unit, to_unit)` entry exists in `test_aliases` (e.g., `FBS: mmol/L -> mg/dL * 18`; `Creatinine: umol/L -> mg/dL * 0.0113`), logging the exact formula into `result.audit`.
4. **Demographic Matching Without Guessing:** `demographic_match()` returns `False` when any known attribute disqualifies a rule, `None` when a required demographic (`age` or `sex`) is missing/unknown, and `True` only when satisfied.
5. **Independent Urgent Thresholds:** `urgent_thresholds` rules evaluate independently of reference range availability. Even if a patient lacks demographics (`patient-p003`) or has duplicate entries, triggered urgent rules force `status = "Urgent"` and surface the critical warning.
6. **Boundary & Synthetic Isolation Rules:** Supports both inclusive (`[`, `]`) and exclusive (`(`, `)`) bounds for values and ages, and refuses to classify uploaded non-synthetic reports (`synthetic=False`) against `knowledge_provenance='synthetic'` rules.

---

## 7. JSON Database Structure and Persistence

Implemented in [`backend/app/storage.py`](backend/app/storage.py) using a single canonical atomic snapshot at `DATA_DIR/database.json` (while preserving non-destructive one-time migration from legacy 9-file installations: `patients.json`, `reports.json`, `reference_ranges.json`, `test_aliases.json`, `urgent_thresholds.json`, `medical_glossary.json`, `safety_rules.json`, `analysis_results.json`, `report_metadata.json`).

Every mutation acquires `FileLock('.storage.lock', timeout=10)`, reads `database.json` with a duplicate-key JSON rejection hook (`_reject_duplicate_keys`), validates cross-collection foreign keys across the unified `Database` Pydantic model, computes deterministic `knowledge_version` SHA-256 hashes, and writes a single temporary file in `DATA_DIR` via `tempfile.mkstemp` + `os.fsync` + `os.replace`. Nine separate files are **not** written in a multi-file transaction; `database.json` is the single authoritative snapshot. Corrupted, empty, duplicate-key, or schema-mismatched JSON fails closed (`StorageError`) without falling back silently or overwriting disk files.

---

## 8. Frontend Design and UI Decisions

Implemented in [`frontend/src/main.tsx`](frontend/src/main.tsx) and [`frontend/src/styles.css`](frontend/src/styles.css):
- **Minimalist Flat Enterprise Aesthetic:** Neutral `#f8fafc` workspace, `#ffffff` cards, `#0f172a` slate-navy typography, restrained `#0f766e` teal primary accent, and `1px` `#e2e8f0` borders.
- **Strict Zero-Gradient Compliance:** Verified across all `frontend/src` and `backend/app` files (`0` matches for `gradient`, `backdrop-filter`, `box-shadow`), and verified in the compiled served CSS that `0` `linear-gradient`, `radial-gradient`, or `conic-gradient` functions exist.
- **First-Time Entry & Assistant UX:** Landing screen shows **Choose a sample report** (4 one-click `"Synthetic demo"` cards with `"View report"`) above a collapsed **Have a private access code?** disclosure without exposing raw demo token strings or `"32+ character"` jargon. Inside the workspace, **Switch sample patient** cancels in-flight requests (`AbortController`) and clears prior chat/selection state; the **Report assistant** surfaces `"View sources"` and `"Report information"` disclosures cleanly without internal machinery names, clearly states when AI assistance is unavailable, and places noisy ingestion telemetry inside a secondary collapsible **Document processing notes** section.

---

## 9. Patient Privacy and Safety Handling

- **Backend-Enforced Bearer Authorization:** Tokens (>= 32 chars) are SHA-256 hashed and compared via constant-time `hmac.compare_digest`. Every report, analysis, demographic update, chat message, and PDF download verifies `report.patient_id == authorized_patient`, returning `404` for unauthorized IDs without disclosing record existence.
- **Response & Storage Hardening:** Sets `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `X-Frame-Options: DENY`. Enforces an 8 MiB upload limit and 120 req/min rate limiting. API keys are read solely from environment variables and never persisted in JSON.
- **Prompt-Injection Defense:** Document ingestion detects and neutralizes instruction-override strings (`prompt_injection_detected=True`), while `ai.py` blocks diagnosis, medication, and cross-patient queries prior to any LLM invocation.

---

## 10. Automated Testing & Live HTTP Verification Results

Executed after final code edits via `.\.venv\Scripts\pytest.exe -v`, `npm.cmd run build`, CLI evidence verification, and live `http://127.0.0.1:8001` HTTP acceptance checks:

| Suite / Check | Command / Target | Result | Verified Scope |
|---|---|---|---|
| **Full Automated Pytest Suite** | `.\.venv\Scripts\pytest.exe -v` | **89 passed, 0 failed** (1 Starlette `httpx` warning, `10.99s`) | Rules engine (`tests/test_engine.py`), canonical atomic snapshot & legacy migration & ingestion (`tests/test_ingestion_storage.py`), API/Auth/Assistant/AI-validation/PDF (`tests/test_api_ai_pdf.py`) |
| Corpus Ingestion & Evidence Verification | `cli.py --data-dir data ingest-corpus corpus` & `verify-evidence corpus` | **92 citations verified** | `vdf3e2fb7d0820a62`: 17 tests, 26 ranges, 12 urgent rules, 4 patients, 8 reports; created `data/database.json` while keeping `corpus/` & legacy `data/*.json` unchanged |
| Frontend Build | `cd frontend; npm.cmd run build` | **Passed (0 errors, `7.66s`)** | `tsc -b && vite build` emitted `dist/index.html` (`0.44 kB`), `dist/assets/index-dw2jjv0z.css` (`20.49 kB`), `dist/assets/index-imkg2hPj.js` (`286.53 kB`) |
| Live Server Health & Assets | `GET http://127.0.0.1:8001/api/health`, `/`, `/assets/index-*.js`, `/assets/index-*.css` | **HTTP 200 OK** | Confirmed `knowledge_provenance: "synthetic"`, `snapshot_file: "database.json"`, `ai_configured: false`, `:focus-visible`, zero CSS gradients, and updated UI labels |
| Live 4-Persona API & PDF Acceptance | Live `http://127.0.0.1:8001` Python HTTP checks | **Passed** | Arjun multi-turn `ALT -> Is it high? -> reference range -> normal -> high -> urgent -> doctor questions`; Fatima urgent + `11,300`-byte PDF; Jordan `34/female` override + `10,188`-byte PDF (`Original Source Age` & `user-supplied`) + reset; Viktor noise/injection telemetry; 5x cross-patient `404` checks |

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

## 12. Observed Artifact Sizes & Execution Timings

Measured directly on the local Windows Python 3.13 / Vite runtime after final edits:
- **Full Pytest Suite (89 test cases):** `10.99 s` (`89 passed, 0 failed`)
- **Frontend Production Build (`tsc -b && vite build`):** `7.66 s` (`286,511` bytes served JS, `20,489` bytes served CSS)
- **Canonical Snapshot Size (`data/database.json`):** `212,733` bytes
- **Live Server PDF Downloads (`http://127.0.0.1:8001`):** Fatima Khan report `11,300` bytes; Jordan Patel demographic-override report `10,188` bytes (valid `%PDF-` headers)

---

## 13. Known Issues and Limitations

1. **Text-Only PDF Support:** OCR is deliberately disabled; image-scanned PDFs require manual transcription or CSV/Markdown export.
2. **Prototype JSON Storage Concurrency:** Appropriate for single-node demos and small datasets; high-throughput clinical environments require an RDBMS.
3. **Docker Runtime Unverified Locally:** `docker` is absent on the Windows evaluation machine; Docker files are provided for container-enabled hosts.
4. **LLM Provider Disabled & Live Calls Unverified:** Runs in deterministic mode (`LLM_PROVIDER=disabled`, `ai_configured=false`); no live Groq/OpenRouter API key was configured during verification.
5. **Live Chrome DevTools Inspection Not Run:** Chrome remote debugging (`DevToolsActivePort`) was unavailable on the host, leaving visual browser layout checks unexecuted in Chrome.

---

## 14. Docker Instructions

```bash
cp .env.example .env
docker compose up --build
```
- UI served on `http://localhost:3000` (Nginx proxying `/api/` to `backend:8000` inside Compose)
- Backend API exposed on `http://localhost:8000` inside Compose
- Persistent JSON snapshot stored in Docker named volume `citylab_json_data` mounted at `/app/data`

---

## 15. Local Runtime Status

- **Live Local Server:** Running via `.\.venv\Scripts\python.exe run_server.py` at `http://127.0.0.1:8001`, serving both the compiled React SPA (`/`) and FastAPI API (`/api/*`) cleanly without interfering with port `8000`.
- **External Cloud URL:** Not deployed externally; runs cleanly locally at `http://127.0.0.1:8001`.

---

## 16. Demo Walkthrough for Evaluators

1. Start the server (`.\.venv\Scripts\python.exe run_server.py`) and open `http://127.0.0.1:8001`.
2. **Boundary & Conversion Showcase (`patient-p001` — Arjun Mehta):** Under **Choose a sample report**, click **View report** on Arjun Mehta (`Synthetic demo`). Inspect `SGPT` (`ALT`) at `45 U/L` (`Normal`), `Total Cholesterol` at `200 mg/dL` (`Normal`), and `FBS 7.0 mmol/L` converted to `126 mg/dL` (`High`). In **Report assistant**, ask `"Explain ALT"`, `"Is it high?"`, `"What is its reference range?"`, `"Which results are normal?"`, and `"What should I ask my doctor?"`, then open **View sources**.
3. **Urgent Alert Showcase (`patient-p002` — Fatima Khan):** Click **Switch sample patient** and choose **Fatima Khan** (verifying previous chat history clears). Observe the urgent alert banner for `Fasting Blood Sugar` (`22.5 mmol/L -> 405 mg/dL`) and `Potassium` (`6.3 mmol/L`).
4. **Missing Demographics Showcase (`patient-p003` — Jordan Patel):** Switch to Jordan Patel. Observe `Hemoglobin`, `Serum Creatinine`, and `ALT` marked `Cannot Be Classified` without guessing, while `Serum Potassium` (`6.4 mmol/L`) still fires `Urgent`. Enter Age `34` and Sex `female`, click **Apply & Re-Analyze** to watch all three re-classify immediately, and click **Reset to Original** to restore.
5. **Noisy Report & Prompt Injection (`patient-p004` — Viktor Chen):** Switch to Viktor Chen. Inspect `Serum Ferritin`, `WBC` (missing unit), `TSH <0.01`, duplicate `ALT`/`SGPT`, and expand **Document processing notes** to see `218` skipped boilerplate lines and prompt-injection neutralization telemetry.
6. **Server-Side PDF Export:** Click **Download PDF** to download and verify the generated multi-section clinical PDF (including the `"SYNTHETIC DEMONSTRATION"` disclosure and user-supplied vs original source demographic labels).

---

## 17. Future Improvements

- Migrate storage backend interface (`Repository`) to PostgreSQL for multi-instance production deployments while keeping the same Pydantic contract.
- Add optional OCR pre-processing pipeline with confidence scoring and human review flags for scanned laboratory PDFs.
- Support longitudinal multi-date trend comparisons for an authorized patient across sequential visits.
- Add automated Playwright end-to-end browser verification in CI alongside `pytest` and `vite build`.
