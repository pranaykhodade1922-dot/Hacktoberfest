# LabReady — College Lab Readiness & Verified Alternative Agent

**Know what will work before you book.**

> *"LabReady doesn't just identify why a practical cannot run. It finds an alternative and verifies that the alternative satisfies the practical's requirements."*

LabReady helps colleges and academic institutions determine whether a scheduled laboratory practical can run successfully. When a practical cannot run due to insufficient student capacity, missing or unverified software, missing equipment, or booking conflicts, LabReady searches institutional inventory, plans student batches when permitted, and deterministically re-verifies proposed alternatives before presenting them as ready.

---

## 1. Product Vision & Architecture

The application is structured into two complementary workflows:

### A. Primary Workflow: College Lab Practical Decision Engine
```text
DEFINE PRACTICAL
  → CHECK READINESS (Capacity, Software, Equipment, Bookings, Time Windows)
  → IDENTIFY BLOCKERS (Specific conflict IDs, computer shortfalls, version mismatches)
  → FIND ALTERNATIVES (Rooms, time slots, student-batch arrangements)
  → VERIFY ALTERNATIVES (Deterministic re-checking of all constraints)
  → PRESENT DECISION & AUDIT EVIDENCE (Side-by-side comparison, rejection audit trail)
```

- **Zero AI Dependency for Decisive Checks**: All capacity evaluations, software version matches, booking overlaps, batch schedules, and verifications are executed with deterministic Python algorithms.
- **AI as Optional Interface Layer**: Gemma (`gemma3:4b` via local Ollama) is used exclusively to interpret natural language requests into strict, validated JSON action contracts. If Ollama is offline or unavailable, the entire application remains 100% operational via the structured form interface.
- **Strict Verification States**:
  - `PASS`: Requirement verified and satisfied.
  - `FAIL`: Requirement verified and not satisfied.
  - `UNKNOWN`: Insufficient evidence or unverified inventory record.
  - `NOT_APPLICABLE`: Check does not apply to this session.
  - **Decision Gate**: An alternative is marked **READY** only when *every* mandatory check is `PASS`. If any check is `UNKNOWN`, the result is marked **UNVERIFIED**. If any check fails, the result is marked **BLOCKED**.

### B. Secondary Workflow: Local Workstation Preparation & Verification
When a software requirement blocks a practical, LabReady allows faculty and lab administrators to safely prepare and verify the assigned local Windows workstation:
- **Environment Isolation**: Creates a dedicated virtual environment (`.labready/practicals/python-data`) without touching global Python or system packages.
- **Dependency Resolution**: Performs read-only PyPI wheel resolution (`dependency_resolution.py`), verifying distribution origins and SHA-256 hashes without installing anything during planning.
- **Explicit Human Approval**: Staff must review the exact allowlisted commands and click **Approve and prepare**. Any change in requirements, findings, or files invalidates the plan hash immediately.
- **Deterministic Verification Probes**: Runs isolated calculations (e.g., NumPy array sum = 6, pandas DataFrame aggregation = 60) to confirm mathematical correctness before declaring the environment ready.

---

## 2. Key Capabilities

| Capability | Implementation Details |
|---|---|
| **Practical Requirement Intake** | Dual-mode: Structured form (subject, date, start/end, students, software, equipment, preferred lab, operating window, batch options) and natural-language extraction via Gemma. |
| **Lab Capacity & Computer Check** | Validates both room seat capacity and verified working computer counts (one working computer per student required). |
| **Software Version Verification** | Distinguishes verified installations from unverified inventory records. Exact version matching required. |
| **Equipment Inventory Audit** | Confirms availability of projectors, whiteboards, robotic arms, and specialized hardware. |
| **Booking Conflict Prevention** | Detects overlapping time intervals and boundary touches; prevents double-booking in scheduling logic. |
| **Student-Batch Planning** | When class size exceeds room capacity, automatically calculates split batches (e.g. 70 students into two 35-student batches in Lab D) and verifies consecutive non-overlapping slots. |
| **Candidate Rejection Audit** | Explains exactly why rejected arrangements failed (e.g. booking conflict, insufficient seats, missing software). |
| **Audit & Protocol Traceability** | Records all action proposals, arguments, and application-triggered events in an audit log. |

---

## 3. Demonstration Scenarios

Four instant demo buttons are built into the UI for hackathon judges and evaluation:

### DEMO A — Practical Ready
- **Session**: Data Structures Practical, 2026-10-27 from 13:00 to 15:00, 50 students, Python 3.12, projector & whiteboard.
- **Result**: `READY` in Lab B. All mandatory checks (Capacity 65 >= 50, Working computers 65 >= 50, Python 3.12 verified, no booking conflict) pass with full evidence.

### DEMO B — Practical Blocked with Verified Alternative
- **Session**: Data Science Practical, 2026-10-27 from 10:00 to 12:00, 60 students, Python 3.12.
- **Result**: Original slot `BLOCKED` due to booking conflict `booking-b-20261027-01` (10:00-12:00) in Lab B, working computers shortfall in Lab A (42 < 60), and version mismatch in Lab C (Python 3.10).
- **Alternative**: Lab B at 12:00–14:00 is found, verified, and presented as `READY`.

### DEMO C — No Feasible Alternative
- **Session**: Robotics & Autonomous Systems, 2026-10-27 from 10:00 to 12:00, 70 students, ROS 2.0 (unverified), robotic arm.
- **Result**: `BLOCKED`. Every candidate violates mandatory capacity constraints or lacks verification evidence. Clear audit trail explains what would need to change.

### DEMO D — Student-Batch Splitting
- **Session**: Machine Learning Workshop, 2026-10-27 from 10:00 to 12:00, 70 students, Python 3.12, batch splitting enabled (max 2 batches).
- **Result**: Single session is blocked across all labs (largest room is 65). The engine calculates two batches of 35 students each in Lab D (capacity 35), verifies consecutive conflict-free slots (10:00-12:00 and 12:00-14:00), and presents a verified batch plan.

---

## 4. Project Structure

```text
workshop-agent/
├── app.py                      # Interactive CLI and --demo mode
├── agent.py                    # Bounded JSON action loop for Ollama / Gemma
├── config.py                   # Host and model configuration
├── data/
│   ├── labs.json               # Demonstration laboratory inventory records
│   └── bookings.json           # Demonstration institutional booking schedules
├── dependency_resolution.py    # Non-installing PyPI pip resolution & hash audit
├── practical_engine.py         # Deterministic readiness, alternatives, batching & verification
├── preparation.py              # Isolated workstation venv manager & calculation probes
├── preparation_agent.py        # Gemma natural language requirements interpreter
├── preparation_ui.py           # 5-stage workstation preparation UI component
├── render.py                   # Structured CLI result formatter
├── requirements.txt            # Python dependencies (Streamlit, Pydantic, Ollama)
├── schemas.py                  # Strict Pydantic input, inventory, check, and result models
├── streamlit_app.py            # Primary full-stack Streamlit web application
├── ui_state.py                 # Concurrency control, Review state, and session adapters
└── tests/
    ├── test_college_engine.py  # Comprehensive readiness, batching, and scenario tests
    ├── test_labready.py        # Core domain logic, boundary, and agent tests
    ├── test_new_capabilities.py # Live inspection, hash audit, and UI integration tests
    ├── test_preparation.py     # Approval gating, plan invalidation, and execution tests
    ├── test_ui.py              # Streamlit state deduplication and error guidance tests
    ├── browser_smoke.py        # Playwright browser end-to-end smoke test
    └── preparation_browser_smoke.py # Workstation preparation browser smoke test
```

---

## 5. Setup and Running Locally

### Prerequisites
- Python 3.12 (Windows x64 recommended)
- Optional: Local [Ollama](https://ollama.ai) with `gemma3:4b` (`ollama pull gemma3:4b`) for natural language input.

### Installation
```powershell
# Clone repository
git clone https://github.com/pranaykhodade1922-dot/Hacktoberfest.git
cd Hacktoberfest

# Activate virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Web Application
```powershell
.\venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address=127.0.0.1 --server.port=8501
```
Open **http://127.0.0.1:8501** in your browser.

---

## 6. Running Automated Tests

All test suites use deterministic fixtures and do not require an active Ollama daemon or internet connection:

```powershell
# Run all 70 automated unit and integration tests
.\venv\Scripts\python.exe -m unittest discover tests

# Run dedicated college practical readiness engine tests
.\venv\Scripts\python.exe -m unittest tests/test_college_engine.py

# Run workstation preparation & security tests
.\venv\Scripts\python.exe -m unittest tests/test_preparation.py

# Run live browser smoke tests (with Streamlit server running)
.\venv\Scripts\python.exe tests/preparation_browser_smoke.py --url http://127.0.0.1:8501
```

---

## 7. Security and Institutional Boundaries

1. **Demonstration Data Notice**: All records in `data/labs.json` and `data/bookings.json` are clearly labeled as **FICTIONAL DEMONSTRATION DATA**. Recommendations do not make live institutional reservations unless an authorized scheduling ERP API is connected.
2. **Subprocess Isolation**: Preparation commands execute strictly via predefined parameter lists (`shell=False`) with process timeouts and dedicated virtual environments.
3. **No Unapproved Installs**: Package resolution checks PyPI distribution hashes prior to any installation. No package is installed without explicit user approval in the UI.
4. **Credential Safety**: No private institutional credentials, API keys, or tokens are stored in source code.
