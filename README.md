# LabReady - local college practical readiness agent

**Prepare your lab. Verify it works.**

“Prepare the assigned computer for a practical, verify that it works, and recommend another lab only when preparation cannot resolve the blockers.”

LabReady inspects the local Windows computer, resolves supported setup issues in an isolated practical environment, and verifies that the environment works with deterministic calculation probes. Fictional college inventory comparison is offered as a fallback only when preparation cannot resolve local blockers.

## Workflow stages

The primary workflow follows five explicit stages:

`Requirements → Inspect → Review plan → Prepare → Verify`

1. **Requirements**:
   - The user describes practical requirements in natural language: e.g. *“Prepare this computer for Python 3.12 with NumPy and pandas.”*
   - Local Gemma (`gemma3:4b` via Ollama) interprets the request into structured JSON requirements.
   - If information is missing (such as omitting the Python version or packages), Gemma asks for clarification rather than guessing.
   - If Ollama is offline, the interface displays actionable guidance to start Ollama without crashing or silently switching models.
   - Validated requirements can also be confirmed or adjusted directly.

2. **Inspect (“This computer — live inspection.”)**:
   - Python performs a read-only live inspection of this machine and the dedicated practical target (`.labready/practicals/python-data`).
   - Clearly displays:
     - Required and detected Python version (including creator interpreter)
     - Required packages and installed versions
     - Missing dependencies
     - Specific readiness blockers
     - Verifiable inspection evidence

3. **Review plan**:
   - Generates a concrete preparation plan:
     - Creates an isolated virtual environment (no system site-packages) using the existing Python 3.12 interpreter.
     - Resolves compatible, published package versions via pip non-installing dependency resolution (`dependency_resolution.py`), verifying PyPI wheel URLs and SHA-256 hashes for Windows x64 / Python 3.12.
     - Explains any unsupported issues requiring manual attention (e.g. requesting a Python version unavailable from the creator).
   - Displays exact allowlisted commands in an expandable section.
   - Requires explicit staff approval (**Approve and prepare**) before any changes are made.
   - Approval is cryptographically bound to the exact plan; changing requirements, files, or inspection findings immediately invalidates approval.

4. **Prepare**:
   - Executes only predefined allowlisted actions in the dedicated environment.
   - Subprocesses run with argument arrays, `shell=False`, and strict timeouts.
   - The application's virtual environment and global Python remain untouched.
   - Displays real-time progress events and captured logs.
   - Prevents duplicate execution on clicks and Streamlit reruns through concurrency guards and machine-level locks.
   - No automatic retry on installation failure.

5. **Verify**:
   - Performs independent verification after preparation:
     - Checks the dedicated interpreter Python version.
     - Imports NumPy and pandas from inside the dedicated environment.
     - Records installed versions.
     - Runs deterministic calculations: NumPy array sum = 6, pandas student total = 60.
     - Marks **READY** only when every required verification check passes.

6. **Fallback recommendations**:
   - Fictional college lab search is offered only when preparation cannot resolve the blockers (status is `PREPARATION FAILED` or `MANUAL ATTENTION REQUIRED`).
   - Clearly labeled as fictional demonstration inventory — inspecting this computer does not inspect or guarantee an entire college lab.

Fixed dedicated target (relative to project root):

```text
.labready/practicals/python-data
```

Allowlisted recipe: Python 3.12 with `numpy==2.2.6` and `pandas==2.2.3` (plus verified wheel dependencies: `python-dateutil`, `pytz`, `six`, `tzdata`).

## If the local URL does not open

The reproduced failure on 2026-10-26 was **no running listener on port 8501**;
the interpreter, dependencies, entry point, and project configuration were valid.
Starting the actual project produced no startup exception and returned HTTP 200
for the health endpoint and root. Prior browser smoke tests start temporary
servers and stop them when testing finishes; they are not persistent app hosting.

From a PowerShell terminal that stays open:

```powershell
Set-Location C:\Users\Pranay\workshop-agent
.\venv\Scripts\python.exe -m streamlit run .\streamlit_app.py --server.address=127.0.0.1 --server.port=8501
```

Open **http://127.0.0.1:8501**. Closing that terminal or stopping its server can
make the URL unavailable. Ollama need not be online for the page or local
inspection to open; inference only happens after a planner submission, never
during module import. A missing/offline model produces an actionable planner
error without silently switching models or blocking local preparation.

Inspect a port conflict without terminating any process:

```powershell
Get-NetTCPConnection -LocalPort 8501 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess
```

If another service occupies 8501, leave it alone and use an available port, e.g.:

```powershell
.\venv\Scripts\python.exe -m streamlit run .\streamlit_app.py --server.address=127.0.0.1 --server.port=8502
```

Then use **http://127.0.0.1:8502**, matching the port printed in the actual logs.
Check both endpoints on the chosen port:

```powershell
(Invoke-WebRequest http://127.0.0.1:8501/_stcore/health -UseBasicParsing).StatusCode
(Invoke-WebRequest http://127.0.0.1:8501/ -UseBasicParsing).StatusCode
```

The background server started during setup writes its captured logs to
`.labready/runtime/streamlit.stdout.log` and `streamlit.stderr.log`. It binds only
to `127.0.0.1`; no public bind or firewall change is needed.

## Local faculty interface

Install dependencies into the existing virtual environment, then launch:

```powershell
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\venv\Scripts\python.exe -m streamlit run .\streamlit_app.py
```

Open `http://127.0.0.1:8501` if the browser does not open automatically.
The project configuration uses a light theme and binds the server to loopback.
Stop the server with `Ctrl+C`. No virtual environment activation is needed.
`OLLAMA_MODEL` is honored; the displayed model is the one used by that browser
session, with no silent fallback to Llama or demo logic.

- **Load example** fills the request without running it. **Check readiness**
  invokes the actual agent through Python, including local Gemma inference.
- Include the date, start/end time, student count, and exact software versions.
  If clarification is needed, enter missing details as a follow-up and submit
  again. **New session** clears the conversation, input, results, and activity.
- Parsed requirements, lab evidence, and up to three alternatives come from
  validated Python results. **How this was checked** shows actual action proposals,
  validation, and tool results. Application-triggered actions have separate labels;
  no hidden model reasoning is displayed.
- Every new explicit submission reads current records through the existing tools.
  Streamlit reruns do not execute checks automatically. Conversation and result
  snapshots live only in that browser's `st.session_state`, never a shared cache.
  Reloading or disconnecting can reset the browser session.
- Results are timestamped snapshots, not live availability. A failed new request
  replaces previous results with an incomplete/error state. Unreadable data means
  unknown availability; a missing resource means absent or mismatched in the
  fictional records. Recommendations never reserve labs.

The CLI-only `--demo` mode remains separate; it is not exposed as an AI fallback
in the interface.

## Run in Windows PowerShell

From this project folder, use the existing environment without activation:

```powershell
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\venv\Scripts\python.exe .\check_setup.py
.\venv\Scripts\python.exe .\app.py
```

Normal mode actually calls local Ollama at `http://localhost:11434` using
`gemma3:4b` by default. Enter `/exit` to quit. Example request:

```text
Check a Python 3.12 practical for 60 students on 2026-10-27 from 10:00 to 12:00.
```

Use explicit `YYYY-MM-DD` dates, `HH:MM` times, student counts in digits, and
software names and exact versions. All times are Asia/Kolkata local, with no
machine timezone conversion. Missing required values trigger clarification;
required values must also appear in the user conversation to prevent model
defaults. Follow-up messages retain conversation history. Equipment is optional
(none requested by default); specify e.g. `projector`. Preferred labs use stable
IDs `lab-a`, `lab-b`, `lab-c` (natural language names can be interpreted by AI).

Debug mode prints actual tool arguments and results:

```powershell
.\venv\Scripts\python.exe .\app.py --debug
```

## Model configuration and action protocol

`gemma3:4b` does **not** support Ollama native tool calling: its published
[chat template](https://ollama.com/library/gemma3:4b/blobs/e0a42594d802) has no
tool-call handling. LabReady instead uses Ollama's
[structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
via the `format` JSON schema parameter, without sending `tools`.

The model proposes one action per turn, for example:

```json
{"action":"check_session_readiness","arguments":{"date":"2026-10-27","start":"10:00","end":"12:00","students":60,"software":[{"name":"Python","version":"3.12"}],"equipment":[]}}
```

Allowed actions are `check_session_readiness`, `find_alternatives`, `clarify`,
and `done`. Python strictly validates the action envelope, allowlisted action
name, argument names, types, and values before execution. Booleans and strings
are rejected for integer counts; JSON strings are rejected for array fields.
Malformed responses execute nothing and can be retried within the bounded loop.
Availability conclusions still come exclusively from Python domain results.
Application feedback uses content messages because Gemma lacks native tool
message support. The same JSON protocol is used for other configured models.

If Gemma is not installed, download it explicitly once (this preserves Llama):

```powershell
ollama pull gemma3:4b
```

Choose a model for the current PowerShell session; no global settings change:

```powershell
$env:OLLAMA_MODEL = "gemma3:4b"
.\venv\Scripts\python.exe .\check_setup.py
.\venv\Scripts\python.exe .\app.py
```

The existing Llama model can still be selected with
`$env:OLLAMA_MODEL = "llama3.1:8b"`. To restore the default, use
`Remove-Item Env:OLLAMA_MODEL -ErrorAction SilentlyContinue`.
The setup check and live integration check both honor `OLLAMA_MODEL`.

Deterministic demo **does not use AI or contact Ollama**:

```powershell
.\venv\Scripts\python.exe .\app.py --demo
```

It uses 2026-10-27, 10:00-12:00, 60 students, Python 3.12. Lab A has only
42 working computers; Lab B is booked; Lab C has Python 3.10. Alternatives in
Lab B begin at 12:00, since a booking ending at 12:00 permits a session starting
then. Lab B is also free 14:00-16:00 in the demonstration records.

## Verification

Offline unit tests, followed by a separate live Ollama integration check:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe .\tests\integration_ollama.py
```

The automated suite also covers the per-session UI adapter, trace events,
clarification follow-ups, booking reloads, duplicate-submission protection, and
Streamlit components via `AppTest`. It uses mocked model responses for these
offline tests; it does not claim they are live model checks.
Preparation tests use temporary roots and a simulated process boundary for
creation, pip success/failure, and verification failures. They cover approval,
tampering/stale plans, unsupported packages/interpreters, isolation, concurrency,
duplicates, and no app/global install targets. A harmless real subprocess test
also verifies output capture and process-tree timeout handling. These are not
an approved real package-installation integration run.

Optional real-browser verification requires installed Chrome and Playwright:

```powershell
.\venv\Scripts\python.exe -m pip install playwright
.\venv\Scripts\python.exe .\tests\browser_smoke.py
```

Read-only preparation UI verification against an already running server:

```powershell
.\venv\Scripts\python.exe .\tests\preparation_browser_smoke.py --url http://127.0.0.1:8501
```

This checks local inspection, displayed actions and target, approval gating,
and requirement invalidation. It deliberately **never clicks approval**. The
real preparation integration is pending explicit staff approval in the UI.

This opt-in test uses actual `gemma3:4b`, a temporary Streamlit server, and an
isolated project/data copy. It checks startup, example loading, results,
clarification and follow-up, changed bookings, mobile overflow, and stale-result
removal after a data failure. It leaves the real booking files unchanged and
prints the temporary location of screenshots and server logs.

The live check reports the selected model's capabilities and probes native tool
support when it is not advertised. Gemma's HTTP 400 "does not support tools"
response is expected. It then tests the actual structured-JSON readiness and
alternative flow; any action, execution, or connection errors fail the check.

Single-request AI mode is also available:

```powershell
.\venv\Scripts\python.exe .\app.py --request "Check a Python 3.12 practical for 60 students on 2026-10-27 from 10:00 to 12:00." --debug
```

## Rules and limitations

- Software versions match exactly: `3.12` does not mean `3.12.0` or `>=3.12`.
  Software names and equipment names match without case sensitivity.
- Bookings use half-open intervals `[start, end)`. Overnight sessions are rejected.
- Readiness checks all labs unless a preferred lab is specified. A preferred lab
  narrows the initial check; alternatives may use any lab.
- Alternatives search the same date at whole-minute start times, preserving
  duration, student count, software, and equipment. Default search hours are
  09:00-17:00; the search tool accepts `opening` and `closing` overrides.
- Ordering is earliest start first, then stable lab ID, capped at three. Original
  lab/time choices are excluded. Nearby one-minute-shifted slots may appear;
  candidates need not be mutually exclusive and are never booked automatically.
- Data files are reloaded for each tool call. A changed booking can invalidate
  an earlier recommendation. Recheck before acting.
- The agent allows at most four model rounds and eight tool calls per request,
  with a 90-second HTTP timeout per model call. Local model output may be invalid
  or incomplete; errors are shown rather than claimed as successful checks.
  If the model stops after a blocked readiness check without searching, an
  application policy invokes the validated alternative tool for that same
  session. Debug output identifies these policy calls separately from AI calls.
  Each model request uses an 8192-token context window and repeats the original
  user messages as explicit context for follow-ups. This is request-local and
  does not change global Ollama settings.
- Only structured successful tool results are rendered as readiness conclusions.
  Action schemas and all arguments are validated strictly; values are never coerced.
  Free-form model prose is suppressed. Clarification prompts are generated by the
  CLI. Literal value grounding is conservative, not a full semantic parser;
  use explicit dates, times, counts, and versions rather than relative wording.
- Conversation history is in memory until exit. There is no persistence or
  history summarization; restart for long or unrelated conversations.

## Files

`app.py` provides the CLI; `agent.py` handles structured JSON actions; `config.py`
reads `OLLAMA_MODEL`; `schemas.py`
validates inputs and results; `tools.py` evaluates readiness and alternatives;
`render.py` displays definitive results. `SKILL.md` supplies agent instructions.
`data/labs.json` and `data/bookings.json` contain labelled fictional records.
`streamlit_app.py` renders the faculty page; `ui_state.py` manages individual
submission snapshots. `.streamlit/config.toml` holds project-local theme and
loopback settings. `Agent.last_trace` exposes observable events for the latest
request; its CLI return value and domain interfaces remain available.
`preparation.py` implements the fixed local recipe, plans, approval and verification;
`process_runner.py` bounds spawned process trees; `preparation_ui.py` renders the
staff-controlled workflow. Neither preparation nor its approval is an agent tool.

## Existing environment setup

Environment setup for Windows PowerShell, using the existing `venv` and local
Ollama installation. LabReady now defaults to `gemma3:4b`; the existing
`llama3.1:8b` installation is preserved.

Open this folder in VS Code. Workspace settings point the Python extension to
`${workspaceFolder}/venv/Scripts/python.exe`. If VS Code already remembers a
different interpreter, run **Python: Select Interpreter** and choose
`.\venv\Scripts\python.exe`.

Run these commands from this folder; virtual environment activation is unnecessary.

Install the recorded Python dependency when needed:

```powershell
.\venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

With the Ollama app running, check the environment and send a short test prompt:

```powershell
.\venv\Scripts\python.exe .\check_setup.py
```

The check verifies the workspace virtual environment, Python version, installed
Ollama package, server at `http://localhost:11434`, configured model availability,
advertised capabilities, and a validated structured JSON response. Success ends
with `SUCCESS: Workshop environment is ready.`
Failures print troubleshooting steps and return a nonzero exit code.

The existing installation and model are reused. No global settings are required.
