# Tech Fusion '26 — Implementation Report
## CityLab Diagnostics Medical Lab Report Explainer (Problem Statement B)

---

## 1. Executive Summary

We built and hardened a minimal-enterprise **Medical Lab Report Explainer** workspace inside `C:\Users\saqlain\Desktop\hack`. The system separates **deterministic medical classification** (Python `Decimal` rules engine) from **natural-language explanation** (deterministic intent router + optional schema-validated LLM phrasing), ensuring that no language model can compute, alter, or invent numeric results, reference ranges, statuses, diagnoses, or treatment advice.

All state, credentials/sessions, and normalized medical rules are stored in a **canonical atomic JSON snapshot (`data/database.json`)** with `filelock` concurrency control, duplicate-key rejection, fail-closed corruption handling, and non-destructive migration from the legacy 9-file layout, alongside private uploaded source documents confined under `data/uploads/<patient_id>/`. After the final code edits, **94 automated pytest tests passed (0 failed, 1 Starlette deprecation warning)**, the TypeScript/Vite frontend compiled cleanly (`0` errors, zero `frontend/src` `gradient`/`backdrop-filter`/`box-shadow`), and live HTTP checks against `http://127.0.0.1:8001` verified personal profile creation, login, upload, review correction, source download, server-restart persistence, 5-endpoint cross-profile `404` isolation, and all sample demo workflows.

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
- Structured `.pdf`, `.png`, `.jpg`, `.jpeg`, `.txt`, `.md`, `.csv`, and `.json` report ingestion with boilerplate noise stripping, injection detection, duplicate JSON key rejection, optional local Tesseract OCR fallback for images/scans, authenticated owner binding regardless of printed document Patient IDs, printed-name mismatch detection, and exact line/page/OCR coordinates.
- Simple personal profiles & single-display access codes (`POST /api/auth/register` generating 150-bit CSPRNG `CLD-...` codes with SHA-256 hashed credentials and 24-hour session tokens in `data/database.json`), `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, and strict separation from synthetic sample personas.
- Inline extraction review (`PATCH /api/reports/{report_id}/review`) tracking `user_corrected`, original extracted values, mismatch confirmation, audit entries (`User-corrected measurement`), PDF `[User corrected]` markers, and stale-chat context invalidation.
- Private upload storage (`data/uploads/<patient_id>/<report_id>.<ext>`) with rollback on DB failure and owner-only streaming (`GET /api/reports/{report_id}/source` with `Content-Security-Policy: default-src 'none'; sandbox` and SPA blocking of `/uploads/` & `/data/`).
- Clickable upper-left **CityLab** logo (`aria-label="CityLab home"`) returning signed-in users to `Dashboard` without losing session/reports and resetting welcome state when signed out.
- **94 passed, 0 failed** automated `pytest` assertions + two-phase live HTTP acceptance & restart-persistence checks on `http://127.0.0.1:8001`.
- Dockerfiles, Nginx config, `.dockerignore`, `.env.example`, and `docker-compose.yml`.

### Incomplete / Not Executed Due to Host Environment
- **Local Image/Scanned-PDF OCR Runtime:** `tesseract` CLI is not installed on this Windows machine (`ocr_available: false`), so live non-mocked OCR on `.png`/`.jpg` or scanned PDFs could not run against a physical Tesseract binary; all OCR paths, uncertainty flags, and missing-Tesseract `422` errors were verified via `OCR_RUNNER` mocks and unit/API tests, while digital text PDFs, CSV, TXT, Markdown, and JSON work natively.
- **Live Docker Compose Runtime Execution:** Docker Desktop / `docker` CLI is not installed on this Windows host, so `docker compose up --build` was not executed locally.
- **Live External LLM API Calls:** No `LLM_API_KEY` is configured in the environment (`LLM_PROVIDER=disabled`, `ai_configured=false`); live external Groq or OpenRouter model responses are therefore **not verified**. AI validation, rejection of fabricated numbers/prescriptions, schema validation, and timeout/`429`/malformed-JSON fallbacks were tested with mocked payloads in `pytest`.
- **Live Chrome DevTools DOM Rendering Walkthrough:** Chrome remote debugging (`DevToolsActivePort`) was unavailable on this Windows host, so interactive click-through DOM visual checks in Chrome were not executed; verified TypeScript compilation, Vite bundle output, served bundle strings, `:focus-visible` CSS rules, zero `gradient`/`backdrop-filter`/`box-shadow` in source files, and live HTTP workflows instead.

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
- **Entry Flow, Home Logo & Review UX:** Landing screen separates personal workspaces (**Create your profile** and **Sign in with access code**) from **Try a sample report** (4 one-click `"Synthetic demo"` cards with `"View report"`). Clicking the upper-left **CityLab** logo (`aria-label="CityLab home"`) returns to `Dashboard` without logging out or clearing saved reports. Personal workspaces hide `"Switch sample patient"`, show an empty state with `"Upload your first report"`, open **Review the extracted results** (`PATCH /api/reports/{id}/review`) on upload with `Uncertain` and `User corrected` indicators plus authenticated **View original report** access, and keep noisy ingestion telemetry collapsed inside **Document processing notes**.

---

## 9. Patient Privacy and Safety Handling

- **Backend-Enforced Bearer Authorization:** Tokens (>= 32 chars) are SHA-256 hashed and compared via constant-time `hmac.compare_digest`. Every report, analysis, demographic update, chat message, and PDF download verifies `report.patient_id == authorized_patient`, returning `404` for unauthorized IDs without disclosing record existence.
- **Response & Storage Hardening:** Sets `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `X-Frame-Options: DENY`. Enforces an 8 MiB upload limit and 120 req/min rate limiting. API keys are read solely from environment variables and never persisted in JSON.
- **Prompt-Injection Defense:** Document ingestion detects and neutralizes instruction-override strings (`prompt_injection_detected=True`), while `ai.py` blocks diagnosis, medication, and cross-patient queries prior to any LLM invocation.

---

## 10. Automated Testing & Live HTTP Verification Results

Executed after final code edits via `.\.venv\Scripts\pytest.exe -v`, `npm.cmd run build`, CLI evidence verification, and live `http://127.0.0.1:8001` HTTP acceptance checks:

- **Full Automated Pytest Suite:** `.\.venv\Scripts\pytest.exe -v` -> **95 passed, 0 failed** (1 Starlette `httpx` deprecation warning, `12.07 s`), adding `test_public_demo_mode_flag` in [`tests/test_personal_profiles_and_uploads.py`](tests/test_personal_profiles_and_uploads.py) alongside `test_engine.py`, `test_ingestion_storage.py`, and `test_api_ai_pdf.py`.
- **Frontend Production Build:** `cd frontend && npm.cmd run build` -> **Passed (0 errors, `4.24 s`)**, emitting `dist/index.html` (`0.44 kB`), `dist/assets/index-rkUJx14J.css` (`21.80 kB`), `dist/assets/index-qxG5JcqT.js` (`305.83 kB`, `0` hardcoded `localhost:8000`/`8001` backend URLs), with zero `gradient`, `backdrop-filter`, or `box-shadow` in `frontend/src/`.
- **Live Server & Restart Persistence (`http://127.0.0.1:8001`):** Verified `/api/health` (`status: "ok"`, `public_demo: false`, `ocr_available: false`), `/` + served React bundle strings (`CityLab home`, `Create your profile`, `Sign in with access code`, `Review the extracted results`, `Save and analyze`, `View original report`), live profile registration -> TXT & text-PDF upload -> inline `PATCH /review` measurement correction -> `/source` download -> `/chat` -> ReportLab PDF (`User corrected`) -> logout token revocation (`401`) -> post-restart re-login with the saved access code confirming persistence of reports and corrections -> cross-profile `404` isolation -> existing sample persona flows (`Arjun Mehta` chat/PDF) -> clean snapshot restore (`data/database.json` preserved).

## 11. Known Limitations

1. **Image & Scanned-PDF OCR Host Dependency:** `backend/Dockerfile` bundles `tesseract-ocr`, while the standalone Windows host lacks a local `tesseract` binary (`ocr_available: false`); digital text PDFs, CSV, TXT, Markdown, and JSON extract directly without Tesseract.
2. **Prototype JSON Storage Concurrency:** Filesystem-locked `data/database.json` and `data/uploads/` are suited for single-node demonstrations rather than high-throughput clinical systems.
3. **LLM Provider Disabled & Docker Desktop Host Prerequisite:** Runs deterministically with `LLM_PROVIDER=disabled`; Cloudflare `cloudflared` (`2026.11.0`) is installed per-user (`%LOCALAPPDATA%\Programs\cloudflared\cloudflared.exe`), while Docker Desktop (`Docker.DockerDesktop`, Proprietary license) and WSL 2 (`HypervisorPresent: False`) require Administrator elevation, license acceptance, and a Windows reboot on this host before container execution can run live.

---

## 12. Isolated Docker & Temporary Cloudflare Tunnel Setup

- **Scripts:** [`scripts/start-docker-demo.ps1`](scripts/start-docker-demo.ps1), [`scripts/start-public-demo.ps1`](scripts/start-public-demo.ps1), [`scripts/stop-public-demo.ps1`](scripts/stop-public-demo.ps1)
- **Container Topology (`docker-compose.yml`):**
  - `citylab-backend` (`backend/Dockerfile`, non-root `appuser`, `tesseract-ocr` bundled) exposes port `8000` only on the internal Compose network (`expose: ["8000"]`, never published to host port `8000`), sets `PUBLIC_DEMO_MODE=true`, and persists isolated JSON/uploads inside named volume `citylab_public_demo_data` (`/app/data`).
  - `citylab-frontend` (`frontend/Dockerfile` + Nginx proxy) binds strictly to `127.0.0.1:8080:80` and proxies `/api/` to `http://backend:8000/api/`.
  - Cloudflare Quick Tunnel forwards `https://<random>.trycloudflare.com` -> `http://127.0.0.1:8080` while keeping the host PC awake (ephemeral URL rotates when stopped).

```powershell
# After Docker Desktop (WSL 2 enabled) is installed and running:
.\scripts\start-public-demo.ps1

# Stop tunnel and containers cleanly while keeping citylab_public_demo_data:
.\scripts\stop-public-demo.ps1
```

---

## 13. Local Runtime Status

- **Live Local Server:** Running via `.\.venv\Scripts\python.exe run_server.py` at `http://127.0.0.1:8001`, serving both the compiled React SPA (`/`) and FastAPI API (`/api/*`) cleanly without interfering with port `8000`.
- **External Cloud URL:** Not deployed externally; runs cleanly locally at `http://127.0.0.1:8001`.

---

## 14. Walkthrough for Evaluators

1. Start the server (`.\.venv\Scripts\python.exe run_server.py`) and open `http://127.0.0.1:8001`.
2. **Personal Profile, Upload, Review & Re-entry:** Under **Create your profile**, enter a name and click **Create profile**. Copy the single-display `CLD-...` access code on **Your profile is ready**, click **Continue to my workspace**, upload a PDF or text/CSV lab report, review/correct extracted values in **Review the extracted results**, click **Save and analyze**, test **View original report** and **CityLab** home logo navigation, then **Sign Out** and return using **Sign in with access code**.
3. **Boundary & Conversion Showcase (`patient-p001` — Arjun Mehta):** Under **Try a sample report**, click **View report** on Arjun Mehta (`Synthetic demo`). Inspect `SGPT` (`ALT`) at `45 U/L` (`Normal`), `Total Cholesterol` at `200 mg/dL` (`Normal`), and `FBS 7.0 mmol/L` converted to `126 mg/dL` (`High`). In **Report assistant**, ask `"Explain ALT"`, `"Is it high?"`, `"What is its reference range?"`, `"Which results are normal?"`, and `"What should I ask my doctor?"`, then open **View sources**.
4. **Urgent Alert Showcase (`patient-p002` — Fatima Khan):** Click **Switch sample patient** and choose **Fatima Khan** (verifying previous chat history clears). Observe the urgent alert banner for `Fasting Blood Sugar` (`22.5 mmol/L -> 405 mg/dL`) and `Potassium` (`6.3 mmol/L`).
5. **Missing Demographics Showcase (`patient-p003` — Jordan Patel):** Switch to Jordan Patel. Observe `Hemoglobin`, `Serum Creatinine`, and `ALT` marked `Cannot Be Classified` without guessing, while `Serum Potassium` (`6.4 mmol/L`) still fires `Urgent`. Enter Age `34` and Sex `female`, click **Apply & Re-Analyze** to watch all three re-classify immediately, and click **Reset to Original** to restore.
6. **Noisy Report & Prompt Injection (`patient-p004` — Viktor Chen):** Switch to Viktor Chen. Inspect `Serum Ferritin`, `WBC` (missing unit), `TSH <0.01`, duplicate `ALT`/`SGPT`, and expand **Document processing notes** to see `218` skipped boilerplate lines and prompt-injection neutralization telemetry.
7. **Server-Side PDF Export:** Click **Download PDF** to download and verify the generated multi-section clinical PDF (including `"User corrected"` markers when edited, `"SYNTHETIC DEMONSTRATION"` disclosure when synthetic, and user-supplied vs original source demographic labels).

---

## 15. Future Improvements

- Migrate storage backend interface (`Repository`) to PostgreSQL for multi-instance production deployments while keeping the same Pydantic contract.
- Bundle Tesseract OCR runtime/language packs inside deployment images and add image deskewing for multi-column scanned laboratory layouts.
- Support longitudinal multi-date trend comparisons for an authorized patient across sequential visits.
- Add automated Playwright end-to-end browser verification in CI alongside `pytest` and `vite build`.
