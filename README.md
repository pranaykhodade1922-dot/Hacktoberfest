# LabReady — College Lab Readiness & Verified Alternative Agent

**Know what will work before you book.**

> *"LabReady doesn't just identify why a practical cannot run. It finds an alternative and verifies that the alternative satisfies the practical's requirements."*

LabReady is an open-source decision and preparation assistant designed for colleges and universities. Academic practicals frequently fail or get rescheduled on the day of execution due to unexpected room constraints: insufficient working computers, software version mismatches, missing laboratory equipment, or unrecorded scheduling conflicts.

LabReady solves this problem by validating practical requirements against institutional lab registries, diagnosing specific blockers, planning student-batch divisions when permitted, and deterministically verifying alternative rooms and time slots before recommending them. For software blockers on the instructor's local machine, LabReady provides an isolated, human-gated virtual environment preparation workflow with mathematical calculation verification.

---

## 1. Project Overview

In academic computer science and engineering institutions, scheduling a laboratory practical involves coordinating several interdependent requirements:
- **Physical room capacity** and **verified working workstations** (one operational workstation per student).
- **Exact software packages and language versions** (e.g. Python 3.12 vs 3.10; unverified vs verified installations).
- **Specialized equipment** (projectors, whiteboards, robotic arms).
- **Institutional calendar bookings** and operational facility windows (09:00–17:00).

When any of these constraints fail, instructors and department staff are left scrambling to find a feasible substitute. LabReady replaces manual guesswork with an automated, auditable decision workflow that either confirms readiness or finds and independently re-verifies viable alternatives.

---

## 2. Key Features

- **Dual Intake Modes**: Describe practical specifications in conversational English or submit structured parameters (subject, date, student count, software, equipment, preferred lab, operating window, batch splitting).
- **Deterministic Multi-Dimensional Verification**: Evaluates 6 distinct categories for every laboratory:
  1. Room Seat Capacity (`capacity >= students`).
  2. Working Computers (`working_computers >= students`).
  3. Exact Software & Version Verification (`Software: name + version`, audited vs unverified status).
  4. Specialized Equipment Availability (`projector`, `whiteboard`, `robotic_arm`).
  5. Schedule Availability (`Booking overlaps` and time-boundary touches).
  6. Permitted Time Window (`09:00–17:00` facility operational hours).
- **Grounded Blocker Explanations**: Cites specific reasons for non-readiness (e.g., shortfall count, mismatched installed versions, overlapping booking IDs).
- **Independent Alternative Re-verification**: Discovered alternative slots and rooms are never assumed ready. Every proposed candidate is re-verified through the same strict deterministic check engine before presentation.
- **Student-Batch Planning**: When a class size exceeds single-room capacity (and batch splitting is permitted), LabReady automatically splits students into balanced batches (e.g., 70 students split into two 35-student batches in Lab D) and verifies consecutive non-overlapping slots.
- **Rejection Audit Trail**: Retains and displays explanations for rejected candidate arrangements so staff understand why other slots were not recommended.
- **Secondary Local Workstation Preparation**: Safe, isolated preparation of the local Windows computer (`.labready/practicals/python-data`) with read-only dependency resolution, explicit human approval gating, and calculation verification probes (NumPy sum, pandas DataFrame aggregation).

---

## 3. Architecture

LabReady uses a layered architecture that strictly separates user interaction from authoritative availability logic:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE (Streamlit)                       │
│     Natural Language Tab (Gemma AI)  │  Structured Form (Deterministic) │
│     Instant Demo Scenarios (A, B, C, D) │  Workstation Preparation UI   │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
    ┌──────────────────────────┐           ┌───────────────────────────┐
    │  AI INTERPRETER (Ollama) │           │   DETERMINISTIC ENGINE    │
    │  Model: gemma3:4b        │           │   (practical_engine.py)   │
    │  Strict Pydantic JSON    │           │                           │
    │  Extraction only         │──────────▶│   • evaluate()            │
    │  No decision authority   │           │   • find_alternatives()   │
    │  Grounding validation    │           │   • verify_candidate()    │
    └──────────────────────────┘           └─────────────┬─────────────┘
                                                         │
                                           ┌─────────────┴─────────────┐
                                           ▼                           ▼
                                  ┌─────────────────┐         ┌─────────────────┐
                                  │ data/labs.json  │         │data/bookings.json│
                                  └─────────────────┘         └─────────────────┘
```

### Deterministic Decision Gates
All availability determinations follow strict verification rules:
- **`PASS`**: Requirement verified and satisfied against records.
- **`FAIL`**: Requirement checked and failed (e.g. insufficient computers, overlapping booking).
- **`UNKNOWN`**: Inventory record lacks audit verification signature.
- **`NOT_APPLICABLE`**: Check not required for this practical.

**Readiness Status**:
- `READY`: All mandatory checks evaluate to `PASS`.
- `UNVERIFIED`: No checks failed, but one or more records are `UNKNOWN` (requires physical audit).
- `BLOCKED`: Any mandatory check evaluates to `FAIL`.

---

## 4. Technology Stack

- **Core Logic & Engine**: Python 3.12 (standard library `datetime`, `subprocess`, `hashlib`, `pathlib`, `json`).
- **Data Modeling & Contract Enforcement**: `pydantic==2.14.1` (strict models, forbidden extra properties, custom field validators).
- **Web Application & UI**: `streamlit==1.66.1` (reactive state management, multi-tab forms, custom badges, metric cards).
- **Local Model Client**: `ollama==0.6.3` (communicates with local Ollama daemon for `gemma3:4b`).
- **Testing & Quality Assurance**: Standard library `unittest`, `streamlit.testing.v1.AppTest`, and Playwright for live browser smoke testing.

---

## 5. Installation

### Prerequisites
- **Operating System**: Windows 10/11 (x64) or Linux/macOS.
- **Python**: Python 3.12 installed and added to `PATH`.
- **Optional (for AI mode)**: [Ollama](https://ollama.ai) installed and running locally with the `gemma3:4b` model pulled (`ollama pull gemma3:4b`). *Note: Natural-language parsing requires Ollama, but the deterministic structured form and instant demo scenarios function 100% offline without Ollama.*

### Windows PowerShell Setup
```powershell
# 1. Clone repository
git clone https://github.com/pranaykhodade1922-dot/Hacktoberfest.git
cd Hacktoberfest

# 2. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Optional: Verify setup and Ollama connectivity
python check_setup.py

# 5. Launch the Streamlit application
python -m streamlit run streamlit_app.py --server.address=127.0.0.1 --server.port=8501
```

Open **http://127.0.0.1:8501** in your web browser.

---

## 6. Configuration

Configuration options are managed through environment variables:

| Variable | Default Value | Description |
|---|---|---|
| `OLLAMA_MODEL` | `gemma3:4b` | Local model name pulled in Ollama. Used exclusively for natural-language requirement interpretation. |

A template file [`.env.example`](file:///.env.example) is provided in the repository root. No external API keys, tokens, or paid cloud credentials are required.

---

## 7. Running Tests

All unit tests run completely offline without contacting external networks or requiring a running Ollama server:

```powershell
# Run the complete test suite (71 automated unit and integration tests)
venv\Scripts\python -m unittest discover tests

# Run college practical readiness engine tests specifically
venv\Scripts\python -m unittest tests/test_college_engine.py

# Run workstation preparation & security tests
venv\Scripts\python -m unittest tests/test_preparation.py
```

### Browser Smoke Tests (Playwright)
With the Streamlit server running on `http://127.0.0.1:8501`:
```powershell
# 1. Run local workstation preparation smoke test
venv\Scripts\python tests/preparation_browser_smoke.py --url http://127.0.0.1:8501

# 2. Run full college readiness end-to-end browser smoke test
venv\Scripts\python tests/browser_smoke.py
```

---

## 8. Demonstration Scenarios

Four instant scenarios are built into the UI bar for judges and evaluators:

### Demo A — Practical Ready
- **Practical**: Data Structures Lab (50 students, Python 3.12, projector, whiteboard).
- **Time**: 2026-10-27 from 13:00 to 15:00.
- **Outcome**: `READY` in Lab B. All 7 verification checks pass (`PASS`). Lab B has 65 seats, 65 working computers, Python 3.12 installed, projector/whiteboard available, and no booking overlaps.

### Demo B — Practical Blocked with Verified Alternative
- **Practical**: Data Science Practical (60 students, Python 3.12, projector, whiteboard).
- **Time**: 2026-10-27 from 10:00 to 12:00.
- **Outcome**: Original slot `BLOCKED` across all labs:
  - Lab A: Blocked (42 working computers < 60 needed).
  - Lab B: Blocked by booking conflict (`booking-b-20261027-01` overlaps 10:00–12:00).
  - Lab C: Blocked by version mismatch (requires Python 3.12; installed 3.10).
  - Lab D: Blocked by room capacity (35 < 60).
  - Lab E: Blocked by capacity (30 < 60) and missing software.
- **Verified Alternative**: Proposes Lab B at **12:00–14:00**. The engine independently re-verifies capacity, software, equipment, and absence of bookings, marking the alternative `READY`.

### Demo C — No Feasible Alternative
- **Practical**: Robotics & Autonomous Systems (70 students, ROS 2.0, robotic arm).
- **Time**: 2026-10-27 from 10:00 to 12:00.
- **Outcome**: `BLOCKED` with no suitable alternative. The engine generates a rejection audit log explaining why each room was rejected (e.g., student count exceeds largest room capacity of 65 seats, robotic arm absent in other labs).

### Demo D — Student-Batch Splitting
- **Practical**: Machine Learning Workshop (60 students, Python 3.12, allow batch split enabled).
- **Preferred Lab**: Lab D (capacity: 35 seats).
- **Outcome**: A single session of 60 students cannot fit in Lab D. The batch planner splits the 60 students into two verified batches of 30 students each in Lab D across consecutive conflict-free windows (10:00–12:00 and 12:00–14:00), presenting a verified split schedule.

---

## 9. AI and Validation: Transparent Separation

| Responsibility | Handled By | Method / Verification |
|---|---|---|
| Natural-language parsing | Gemma (`gemma3:4b` via Ollama) | Strict Pydantic JSON schema output; regex-based user-context grounding verification. |
| Missing field detection | Gemma + Grounding Validator | Triggers clarification questions if mandatory values (date, times, student count, software version) are missing. |
| Lab readiness evaluation | Deterministic Python Engine | Exact mathematical checks against `labs.json` and `bookings.json`. |
| Conflict detection | Deterministic Python Engine | Interval overlap comparison (`start < existing_end` and `existing_start < end`). |
| Alternative slot search | Deterministic Python Engine | Exhaustive search across operational windows with candidate re-verification. |
| Workstation preparation | Human Staff Approval Gate | Read-only dependency resolution, SHA-256 hash validation, isolated virtual environment, mathematical calculation checks. |

> **Notice**: Language models can hallucinate or omit requirements. In LabReady, the AI has zero decision-making authority over lab readiness or candidate feasibility. An AI-proposed action is executed only after passing schema validation and grounding checks against user text.

---

## 10. Data Limitations

All laboratory inventories (`data/labs.json`) and schedule records (`data/bookings.json`) provided in this repository are **fictional demonstration data** created for testing and evaluation purposes.
- Recommendations produced by LabReady do not place live bookings in college scheduling ERPs (such as Ellucian Banner, PeopleSoft, or Timetabler).
- Real-world deployment requires connecting an authenticated institutional database adapter.

---

## 11. Limitations and Future Work

### Current Limitations
1. **Local Workstation Scope**: The preparation workflow executes on the current Windows machine only; remote workstation cluster orchestration is not currently implemented.
2. **Fixed PyPI Allowlist**: Local environment package resolution supports tested distributions of `numpy==2.2.6` and `pandas==2.2.3` for Python 3.12.
3. **Local Ollama Daemon**: Natural-language interpretation requires an active local Ollama instance (the structured form works fully offline).

### Future Roadmap
- **Institutional SIS/ERP Connectors**: Direct integration with university room reservation APIs via OAuth2.
- **Distributed Machine Agent**: Lightweight SSH/WinRM daemon to inspect and prepare entire laboratory workstation clusters simultaneously.
- **Expanded Software Catalog**: Support for dynamic PyPI package allowlisting, containerized environments (Docker/Podman), and non-Python software runtimes (Java, C++, ROS).
