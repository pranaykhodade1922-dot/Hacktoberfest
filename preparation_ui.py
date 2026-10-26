"""Staff-only approval controls for this computer, separate from fictional labs."""
from html import escape
import subprocess

import streamlit as st

from preparation import ApprovalError, PINS, PreparationController, Requirements
from preparation_agent import PreparationInterpreter, EXAMPLE as PREP_EXAMPLE
from schemas import Session, Software
from tools import check_session_readiness, find_alternatives


def changed():
    controller = st.session_state.get("preparation")
    if controller:
        controller.invalidate()
    st.session_state.pop("local_fallback", None)
    st.session_state.pop("prep_clarification", None)
    st.session_state.pop("prep_ai_error", None)


def load_prep_example():
    st.session_state["prep_request_pending"] = PREP_EXAMPLE


def render_stepper(stage: str):
    stages = [
        ("requirements", "1. Requirements"),
        ("inspect", "2. Inspect"),
        ("review", "3. Review plan"),
        ("prepare", "4. Prepare"),
        ("verify", "5. Verify"),
    ]
    keys = [s[0] for s in stages]
    cur_idx = keys.index(stage) if stage in keys else 0
    pills = []
    for idx, (key, label) in enumerate(stages):
        if idx < cur_idx:
            cls = "step done"
        elif idx == cur_idx:
            cls = "step active"
        else:
            cls = "step"
        pills.append(f'<span class="{cls}">{escape(label)}</span>')
    st.markdown(f'<div class="stepper">{" <span class=\"step-arrow\">→</span> ".join(pills)}</div>', unsafe_allow_html=True)


def show_inspection(inspection, requirements=None, controller=None):
    st.markdown("#### Inspection findings")
    st.markdown('<div class="live-badge">This computer — live inspection.</div>', unsafe_allow_html=True)
    st.markdown(f"**{inspection.status}**")

    req_py = requirements.python_version if requirements else "3.12"
    det_py = "Not detected"
    if inspection.details.get("version"):
        det_py = f"Python {inspection.details['version']} (dedicated environment)"
    elif inspection.details.get("creator"):
        det_py = f"Python {inspection.details['creator'].get('version', '3.12')}"
        if controller:
            det_py += f" (creator at {controller.service.app_python})"

    pkg_rows = []
    packages_probe = inspection.details.get("packages", {})
    for name, pin in PINS.items():
        if inspection.environment_missing:
            inst = "None (environment missing)"
        else:
            p_data = packages_probe.get(name, {})
            if "version" in p_data:
                inst = str(p_data["version"])
            elif "error" in p_data:
                inst = f"Missing ({p_data['error']})"
            else:
                inst = "Not installed"
        pkg_rows.append(f"{name}: required {pin}, installed {inst}")

    missing_str = ", ".join(inspection.missing_packages) if inspection.missing_packages else "None"

    blockers = []
    if inspection.environment_missing:
        blockers.append("Dedicated practical environment does not exist (.labready/practicals/python-data).")
    if inspection.missing_packages:
        blockers.append(f"Missing required packages: {', '.join(inspection.missing_packages)}.")
    if inspection.status == "MANUAL ATTENTION REQUIRED":
        blockers.append("Unsupported configuration or creator mismatch requires manual attention.")
    if not blockers and inspection.status != "READY":
        blockers.append("Environment not verified ready.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f'<div class="inspection-card">'
            f'<div class="card-label">Python Version</div>'
            f'<div class="card-value">Required: {escape(req_py)}<br>'
            f'<span style="font-size:0.85rem; font-weight:normal; color:#475569;">Detected: {escape(det_py)}</span></div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with c2:
        st.markdown(
            f'<div class="inspection-card">'
            f'<div class="card-label">Missing Dependencies</div>'
            f'<div class="card-value">{escape(missing_str)}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown(
        f'<div class="inspection-card" style="margin-top:0.6rem;">'
        f'<div class="card-label">Required Packages & Installed Versions</div>'
        f'<div class="card-value" style="font-size:0.87rem; font-weight:normal;">' +
        "<br>".join(f"• {escape(row)}" for row in pkg_rows) +
        f'</div></div>',
        unsafe_allow_html=True
    )

    if blockers:
        st.markdown(
            f'<div class="inspection-card" style="margin-top:0.6rem; border-left:3px solid #e11d48;">'
            f'<div class="card-label" style="color:#e11d48;">Specific Readiness Blockers</div>'
            f'<div class="card-value" style="font-size:0.87rem; font-weight:normal;">' +
            "<br>".join(f"• {escape(b)}" for b in blockers) +
            f'</div></div>',
            unsafe_allow_html=True
        )

    st.caption("Actual inspection of this Windows computer's dedicated practical environment only.")
    for ev in inspection.evidence:
        st.write(ev)

    if inspection.details:
        with st.expander("Local verification evidence"):
            st.json(inspection.details)


def fallback(requirements, eligible):
    if not eligible:
        st.caption("Fictional fallback options stay unavailable until preparation fails or inspection confirms an unsupported blocker.")
        return
    st.markdown("#### Fictional fallback options")
    st.warning("These are demonstration lab records, not verified computer inspections or reservations. This one computer's result says nothing about an entire lab.")
    st.info("Local preparation cannot resolve the blockers on this computer. You may search fictional demonstration lab records for an alternative room.")
    st.caption("Fallbacks must satisfy Python, numpy and pandas requirements. The current fictional records list Python only, so they may yield no feasible alternative.")
    with st.form("local_fallback_form"):
        date = st.text_input("Fallback session date", placeholder="YYYY-MM-DD")
        left, right = st.columns(2)
        start = left.text_input("Fallback start time", placeholder="HH:MM")
        end = right.text_input("Fallback end time", placeholder="HH:MM")
        students = st.text_input("Fallback student count", placeholder="Positive integer")
        submitted = st.form_submit_button("Check fictional fallback options")
    if submitted:
        st.session_state.pop("local_fallback", None)
        try:
            if not students.isdecimal():
                raise ValueError("Enter a positive student count in digits")
            session = Session(date=date, start=start, end=end, students=int(students),
                              software=[Software(name="Python", version=requirements.python_version),
                                        *[Software(name=name, version=pin) for name, pin in PINS.items()]])
            readiness = check_session_readiness(session)
            alternatives = find_alternatives(session)
            st.session_state["local_fallback"] = (readiness, alternatives)
        except (ValueError, OSError, KeyError) as exc:
            st.error(f"Fallback check failed: {exc}. Enter the full session requirements; availability is unknown until evaluation succeeds.")
    data = st.session_state.get("local_fallback")
    if data:
        readiness, alternatives = data
        st.caption(f"{readiness.session.date} {readiness.session.start}–{readiness.session.end} Asia/Kolkata")
        for evidence in readiness.labs:
            st.write(f"{evidence.lab_name}: {evidence.status}")
            for reason in evidence.reasons:
                st.caption(reason)
        if not alternatives.alternatives:
            st.info("No feasible alternative found.")
        for candidate in alternatives.alternatives:
            st.write(f"{candidate.evidence.lab_name}: {candidate.session.date} {candidate.session.start}–{candidate.session.end} Asia/Kolkata — READY")
        with st.expander("Fictional fallback evaluator output"):
            st.json({"readiness": readiness.model_dump(), "alternatives": alternatives.model_dump()})


def render_preparation():
    st.subheader("Prepare this computer")
    st.caption("Scope: this Windows computer only. Remote lab-computer management requires future authorized connectivity.")
    if "preparation" not in st.session_state:
        st.session_state["preparation"] = PreparationController()
    controller = st.session_state["preparation"]

    current_stage = "requirements"
    if controller.result:
        current_stage = "verify"
    elif controller.busy:
        current_stage = "prepare"
    elif controller.plan and controller.plan.actions:
        current_stage = "review"
    elif controller.plan:
        current_stage = "inspect"

    render_stepper(current_stage)

    with st.container(border=True):
        st.markdown("**1. Practical requirements**")
        st.caption("Describe the practical requirements in natural language or enter exact requirements below.")

        if "prep_request_pending" in st.session_state:
            st.session_state["prep_request_input"] = st.session_state.pop("prep_request_pending")
        elif "prep_request_input" not in st.session_state:
            st.session_state["prep_request_input"] = PREP_EXAMPLE

        prompt_text = st.text_input(
            "Natural language practical request",
            key="prep_request_input",
            help="Example: Prepare this computer for Python 3.12 with NumPy and pandas."
        )
        col_ex, col_ai = st.columns([1, 2])
        col_ex.button("Load practical example", on_click=load_prep_example, disabled=controller.busy)

        if col_ai.button("Interpret with Gemma (AI)", disabled=controller.busy):
            with st.spinner("Gemma is interpreting your practical request..."):
                try:
                    interpreter = PreparationInterpreter()
                    req = interpreter.interpret(prompt_text)
                    st.session_state["prep_interpreter_trace"] = interpreter.last_trace
                    if req:
                        st.session_state["local_python_version_pending"] = req.python_version
                        st.session_state["prep_clarification"] = None
                        st.session_state["prep_ai_error"] = None
                        st.success(f"Gemma validated requirements: Python {req.python_version} with NumPy and pandas.")
                        controller.inspect(req)
                        st.rerun()
                    elif interpreter.question:
                        st.session_state["prep_clarification"] = interpreter.question
                        st.session_state["prep_ai_error"] = None
                    elif interpreter.last_errors:
                        st.session_state["prep_ai_error"] = interpreter.last_errors[0]
                        st.session_state["prep_clarification"] = None
                except Exception as exc:
                    st.session_state["prep_ai_error"] = f"Cannot use local model at http://localhost:11434 ({type(exc).__name__}): {exc}. Check setup and start Ollama."

        if st.session_state.get("prep_clarification"):
            st.info(f"Clarification required: {st.session_state['prep_clarification']}")
        if st.session_state.get("prep_ai_error"):
            st.error(st.session_state["prep_ai_error"])

        st.markdown("**Validated local requirements**")
        if "local_python_version_pending" in st.session_state:
            st.session_state["local_python_version"] = st.session_state.pop("local_python_version_pending")
        elif "local_python_version" not in st.session_state:
            st.session_state["local_python_version"] = "3.12"

        python_version = st.text_input(
            "Required local Python version",
            key="local_python_version",
            on_change=changed,
            disabled=controller.busy,
            help="Major.minor. This MVP can create environments only with the existing Python 3.12 interpreter."
        )
        st.write("Required packages: " + ", ".join(f"{name}=={pin}" for name, pin in PINS.items()))
        st.caption("Fixed, tested allowlist. Gemma cannot choose packages, commands, paths, URLs, or grant approval.")
        st.text("Exact target: " + str(controller.service.target))
        st.caption("The app's venv and global Python are never practical installation targets.")

        try:
            requirements = Requirements(python_version=python_version.strip())
        except ValueError as exc:
            controller.invalidate()
            st.error(f"Invalid local requirements: {exc}")
            return

        if st.button("Inspect and propose preparation", disabled=controller.busy):
            st.session_state.pop("local_fallback", None)
            with st.spinner("Inspecting actual local interpreter and package evidence…"):
                controller.inspect(requirements)

    plan = controller.plan
    if plan is None:
        st.info("Not inspected yet. Inspection is read-only; nothing will be installed without explicit approval.")
        return

    if plan.requirements != requirements:
        controller.invalidate()
        st.warning("Requirements changed. Inspect again to create a new plan.")
        return

    if controller.result and controller.result.inspection is None:
        st.warning("The latest preparation did not establish the current environment state. Its earlier inspection is historical; inspect again before a new attempt.")
    else:
        show_inspection(controller.result.inspection if controller.result else plan.inspection, requirements, controller)

    if plan.actions:
        st.markdown("#### Proposed actions — approval required")
        st.text("Exact target: " + plan.inspection.target)
        st.caption("Plan ID: " + plan.id)
        if plan.resolution:
            st.caption("Compatible, published package versions verified through dependency resolution (PyPI wheels and SHA-256 hashes validated).")
        for index, action in enumerate(plan.actions, 1):
            st.write(f"{index}. {action}")
        with st.expander("Exact fixed commands for this plan"):
            for command in plan.commands:
                st.code(subprocess.list2cmdline(command), language="text")
        st.caption("Approval applies only to this plan and these requirements. Changed requirements, files, or inspection findings invalidate it. Package downloads require internet. Failed installs are not retried automatically.")
        if st.button("Approve and prepare", type="primary", disabled=controller.busy or controller.result is not None,
                     key="approve_local_preparation"):
            st.session_state.pop("local_fallback", None)
            with st.status("Checking staff approval and the current inspection", expanded=True) as progress:
                def report(event):
                    if event["event"] == "preparing":
                        progress.update(label="PREPARING — executing the approved local plan", state="running")
                    elif event["event"] == "command_started":
                        cmd_desc = "venv creation" if "venv" in event.get("argv", []) else "package installation"
                        progress.write(f"Executing: {cmd_desc}")
                    elif event["event"] == "verification_started":
                        progress.write("Verifying environment and calculations...")
                    else:
                        progress.write(event["event"].replace("_", " "))
                try:
                    result = controller.prepare(requirements, plan.id, report)
                    progress.update(label=result.status, state="complete" if result.status == "READY" else "error")
                except (ApprovalError, ValueError, OSError) as exc:
                    progress.update(label="Approval invalidated — inspect again", state="error")
                    st.error(str(exc))

    if controller.result:
        result = controller.result
        st.markdown("#### Preparation result")
        if result.status == "READY":
            st.success("**READY** — Environment verified successfully.")
            if result.inspection and result.inspection.details:
                calc = result.inspection.details.get("calculation", {})
                pkgs = result.inspection.details.get("packages", {})
                st.markdown(
                    f"• **Interpreter**: Python {result.inspection.details.get('version')}<br>"
                    f"• **NumPy**: version {pkgs.get('numpy', {}).get('version')} (verified sum = {calc.get('numpy_sum', 6)})<br>"
                    f"• **pandas**: version {pkgs.get('pandas', {}).get('version')} (verified student total = {calc.get('pandas_sum', 60)})<br>"
                    f"• **Definitive readiness**: Verified calculations passed. Global and app Python untouched.",
                    unsafe_allow_html=True
                )
        else:
            st.error(f"**{result.status}**")
            for evidence in result.evidence:
                st.write(evidence)
            st.caption("To retry deliberately, inspect again and approve the newly displayed plan. No automatic retry or deletion is performed.")
        with st.expander("Actual preparation execution log"):
            st.json(result.model_dump())

    if st.session_state.get("prep_interpreter_trace"):
        with st.expander("Gemma interpretation action trace"):
            st.caption("Structured JSON action proposal, validation, and schema enforcement events.")
            st.json(st.session_state["prep_interpreter_trace"])

    eligible = controller.result.fallback_allowed if controller.result else plan.inspection.fallback_allowed
    fallback(requirements, eligible)
