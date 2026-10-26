"""LabReady College Lab Readiness and Verified Alternative Agent.

Primary Workflow: College Practical Readiness, Conflict Detection, Batch Planning, and Verified Alternatives.
Secondary Workflow: Local Workstation Preparation and Deterministic Environment Verification.
"""
from datetime import datetime
from html import escape
from uuid import uuid4

import streamlit as st

from app import DEMO_REQUEST
from preparation_ui import render_preparation
from schemas import Session, Software
from ui_state import CLARIFICATION, Conversation, error_guidance

st.set_page_config(page_title="LabReady", page_icon="🔬", layout="wide", initial_sidebar_state="collapsed")

STYLE = """
<style>
.stApp {background:#f8fafc; color:#0f172a;}
.block-container {max-width:1260px; padding-top:1.6rem; padding-bottom:2.5rem;}
header[data-testid="stHeader"] {background:transparent; z-index:1;}
h1,h2,h3,h4 {color:#0f172a; letter-spacing:-.03em;}
h1 {font-size:2.35rem !important; margin-bottom:0.1rem !important; margin-top:0.1rem !important;}
h2 {font-size:1.4rem !important; margin-top:0.3rem !important;}
h3 {font-size:1.12rem !important;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:14px;}
[data-testid="stForm"] {background:white; border-radius:16px; padding:1.25rem; border:1px solid #e2e8f0; box-shadow:0 1px 3px rgba(0,0,0,0.04);}
.eyebrow {font-size:.76rem; letter-spacing:.14em; font-weight:700; color:#0f766e; text-transform:uppercase; margin-bottom:.3rem;}
.headline {font-size:1.85rem; font-weight:800; color:#0f172a; line-height:1.22; margin-top:0.2rem; margin-bottom:0.25rem;}
.subtitle {font-size:1.02rem; color:#475569; margin-bottom:1.1rem; line-height:1.45;}
.model {display:inline-block; padding:.32rem .75rem; background:#ecfdf5; color:#065f46;
 border-radius:24px; font-size:.82rem; font-weight:600; margin-top:0.2rem; margin-bottom:0.6rem; border:1px solid #a7f3d0;}
.stepper {display:flex; flex-wrap:wrap; gap:0.4rem; align-items:center; background:white;
 border:1px solid #e2e8f0; border-radius:12px; padding:0.55rem 0.95rem; margin-bottom:1.2rem;
 font-size:0.86rem; color:#475569; box-shadow:0 1px 2px rgba(0,0,0,0.03);}
.step {font-weight:600; padding:0.2rem 0.55rem; border-radius:6px; background:#f1f5f9; color:#475569;}
.step.active {background:#0f766e; color:white;}
.step.done {background:#ccfbf1; color:#0f766e;}
.step-arrow {color:#94a3b8; font-weight:700;}
.demo-preset {background:#ffffff; border:1px solid #cbd5e1; border-radius:10px; padding:0.75rem 0.9rem; margin-bottom:0.5rem; transition:all 0.15s ease;}
.demo-preset:hover {border-color:#0f766e; background:#f0fdfa;}
.lab-card {background:white; border:1px solid #e2e8f0; border-radius:14px; padding:1.2rem 1.3rem; margin-bottom:1rem; box-shadow:0 1px 3px rgba(0,0,0,0.03);}
.lab-head {display:flex; align-items:center; justify-content:space-between; gap:1rem; margin-bottom:.7rem;}
.lab-name {font-size:1.15rem; font-weight:700; color:#0f172a;}
.muted {color:#64748b; font-size:.86rem; margin-bottom:0.4rem;}
.badge {font-size:.73rem; letter-spacing:.04em; font-weight:800; border-radius:20px; padding:.3rem .65rem; text-transform:uppercase;}
.badge.ready {color:#065f46; background:#d1fae5; border:1px solid #a7f3d0;}
.badge.blocked {color:#991b1b; background:#fee2e2; border:1px solid #fecaca;}
.badge.unverified {color:#854d0e; background:#fef9c3; border:1px solid #fef08a;}
.badge.pass {color:#065f46; background:#d1fae5;}
.badge.fail {color:#991b1b; background:#fee2e2;}
.badge.unknown {color:#854d0e; background:#fef9c3;}
.fact {display:grid; grid-template-columns:130px 1fr; gap:.8rem; padding:.35rem 0; font-size:.89rem;}
.fact-label {color:#64748b; font-weight:500;}
.reason {font-size:.87rem; color:#b91c1c; margin-top:.45rem; font-weight:500;}
.checklist-row {display:flex; justify-content:space-between; align-items:center; padding:0.35rem 0; border-bottom:1px solid #f1f5f9; font-size:0.86rem;}
.checklist-status {font-size:0.72rem; font-weight:700; padding:0.15rem 0.45rem; border-radius:4px;}
.empty {padding:2.2rem 1.5rem; border:2px dashed #cbd5e1; background:#ffffff; border-radius:14px; text-align:center;}
.empty h3 {margin-bottom:.4rem; color:#1e293b;}
.empty p {color:#64748b; max-width:460px; margin:auto; font-size:0.92rem; line-height:1.5;}
.prep-callout {background:#eff6ff; border:1px solid #bfdbfe; border-radius:10px; padding:0.75rem 1rem; margin:0.8rem 0; font-size:0.88rem; color:#1e40af;}
@media (max-width:640px) {.block-container {padding-top:1.1rem;} h1 {font-size:1.9rem !important;}
.fact {grid-template-columns:95px 1fr;} .lab-card {padding:1rem;}}
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)


def new_session():
    st.session_state.pop("conversation", None)
    st.session_state.pop("pending", None)
    st.session_state.pop("pending_session", None)
    st.session_state.pop("preparation", None)
    st.session_state.pop("local_fallback", None)
    st.session_state.pop("prep_clarification", None)
    st.session_state.pop("prep_ai_error", None)
    st.session_state.pop("prep_interpreter_trace", None)
    st.session_state["request_text"] = ""
    st.session_state["prep_request_pending"] = ""
    st.session_state.pop("local_python_version", None)
    st.session_state.pop("local_python_version_pending", None)


def load_example():
    st.session_state["request_text"] = DEMO_REQUEST


def set_scenario(scenario_key):
    st.session_state["active_scenario"] = scenario_key
    if scenario_key == "demo_a":
        # Practical Ready: 50 students, Python 3.12, 13:00-15:00
        sess = Session(
            practical_name="Data Structures Lab",
            date="2026-10-27",
            start="13:00",
            end="15:00",
            students=50,
            software=[Software(name="Python", version="3.12")],
            equipment=["projector", "whiteboard"],
            preferred_lab=None,
            allow_batch_split=False,
        )
        st.session_state["pending_session"] = (sess, uuid4().hex)
    elif scenario_key == "demo_b":
        # Blocked with Verified Alternative: 60 students, Python 3.12, 10:00-12:00
        sess = Session(
            practical_name="Data Science Practical",
            date="2026-10-27",
            start="10:00",
            end="12:00",
            students=60,
            software=[Software(name="Python", version="3.12")],
            equipment=["projector", "whiteboard"],
            preferred_lab=None,
            allow_batch_split=False,
        )
        st.session_state["pending_session"] = (sess, uuid4().hex)
    elif scenario_key == "demo_c":
        # No Feasible Alternative: 70 students, ROS 2.0 (unverified), 10:00-12:00
        sess = Session(
            practical_name="Robotics & Autonomous Systems",
            date="2026-10-27",
            start="10:00",
            end="12:00",
            students=70,
            software=[Software(name="ROS", version="2.0")],
            equipment=["robotic_arm"],
            preferred_lab=None,
            allow_batch_split=False,
        )
        st.session_state["pending_session"] = (sess, uuid4().hex)
    elif scenario_key == "demo_d":
        # Batch Splitting Demo: 60 students in Lab D (35 capacity) split into 2 batches
        sess = Session(
            practical_name="Machine Learning Workshop",
            date="2026-10-27",
            start="10:00",
            end="12:00",
            students=60,
            software=[Software(name="Python", version="3.12")],
            equipment=["projector", "whiteboard"],
            preferred_lab="lab-d",
            allow_batch_split=True,
            max_batches=2,
        )
        st.session_state["pending_session"] = (sess, uuid4().hex)


def queue_check():
    conversation = st.session_state["conversation"]
    if not conversation.busy and "pending" not in st.session_state:
        st.session_state["pending"] = (st.session_state.get("request_text", ""), uuid4().hex)


def lab_card(evidence, session, *, alternative=False, candidate=None):
    installed = ", ".join(f"{s.name} {s.version}" for s in evidence.installed_software) or "None listed in inventory"
    required = ", ".join(f"{s.name} {s.version}" for s in session.software)
    equipment = ", ".join(evidence.equipment) or "None listed in inventory"
    needed = ", ".join(session.equipment) or "None requested"
    conflicts = ", ".join(evidence.conflicting_booking_ids) or "No overlapping bookings in the records"
    
    details = [
        ("Computers", f"{evidence.working_computers} working / {session.students} required"),
        ("Room capacity", f"{evidence.capacity} places / {session.students} students"),
        ("Software", f"Installed: {installed}. Required: {required} (exact versions)."),
        ("Equipment", f"Listed: {equipment}. Required: {needed}."),
        ("Bookings", conflicts),
    ]
    rows = "".join(f'<div class="fact"><span class="fact-label">{escape(label)}</span><span>{escape(value)}</span></div>' for label, value in details)
    reasons = "".join(f'<div class="reason">• {escape(reason)}</div>' for reason in evidence.reasons)
    
    if alternative:
        if candidate and getattr(candidate, "is_split", False) and candidate.batches:
            batch_lines = []
            for idx, (b_s, b_e) in enumerate(zip(candidate.batches, candidate.batch_evidences), 1):
                batch_lines.append(f"<div><strong>Batch {idx}:</strong> {b_s.students} students · {b_s.start}–{b_s.end} · {b_e.lab_name} (Verified)</div>")
            reasons += f'<div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:0.6rem; margin-top:0.6rem; font-size:0.87rem; color:#166534;"><strong>Split Batch Schedule Approved:</strong><br/>{"".join(batch_lines)}</div>'
        else:
            reasons += '<div class="muted">Qualifies: enough places and working computers, every requested resource matches, and no booking overlaps.</div>'
    
    time = f'<div class="muted">{escape(session.date)} · {escape(session.start)}–{escape(session.end)} · Asia/Kolkata</div>' if alternative else ""
    
    # Detailed verification checks
    checklist_html = ""
    if getattr(evidence, "checks", None):
        items_html = []
        for chk in evidence.checks:
            badge_class = chk.status.lower()
            items_html.append(
                f'<div class="checklist-row">'
                f'<span><strong>{escape(chk.name)}:</strong> {escape(chk.evidence)}</span>'
                f'<span class="badge {badge_class}">{chk.status}</span>'
                f'</div>'
            )
        checklist_html = f'<div style="margin-top:0.8rem; border-top:1px solid #f1f5f9; padding-top:0.5rem;"><details><summary style="font-size:0.82rem; font-weight:600; color:#0f766e; cursor:pointer;">Verification Checklist ({len(evidence.checks)} checks)</summary><div style="margin-top:0.4rem;">{"".join(items_html)}</div></details></div>'
    
    st.markdown(
        f'<div class="lab-card">'
        f'<div class="lab-head">'
        f'<span class="lab-name">{escape(evidence.lab_name)}</span>'
        f'<span class="badge {evidence.status.lower()}">{evidence.status}</span>'
        f'</div>'
        f'{time}{rows}{reasons}{checklist_html}'
        f'</div>',
        unsafe_allow_html=True
    )


def results(review):
    st.caption(f"Latest request · checked {review.checked_at} Asia/Kolkata")
    labels = {
        "ready": "Ready lab found",
        "blocked": "All checked labs blocked",
        "unverified": "Readiness unverified (audit required)",
        "alternatives": "Ready lab found in alternatives",
        "incomplete": "Incomplete / error",
    }
    st.subheader(labels.get(review.outcome, "Readiness evaluation complete"))
    for error in review.errors:
        st.error(error_guidance(error))
    if review.needs_clarification:
        st.info(CLARIFICATION)
    if not review.results:
        st.caption("Availability is unknown. No successful check for this request; previous results are not shown.")
    
    session = review.session
    if session:
        with st.container(border=True):
            prac_title = session.practical_name or "Scheduled Practical"
            st.markdown(f"**{escape(prac_title)} · Requirements**")
            date_col, time_col, count_col = st.columns([1, 1.4, .8])
            date_col.metric("Date", session.date)
            time_col.metric("Time · Asia/Kolkata", f"{session.start}–{session.end}")
            count_col.metric("Students", session.students)
            
            soft_str = ", ".join(f"{s.name} {s.version}" for s in session.software)
            eq_str = ", ".join(session.equipment) or "None requested"
            split_str = f"Allowed (max {session.max_batches} batches)" if session.allow_batch_split else "Single session required"
            
            st.text(f"Software: {soft_str}")
            st.text(f"Equipment: {eq_str}")
            st.text(f"Preferred lab: {session.preferred_lab or 'Any lab'}")
            st.text(f"Batch splitting: {split_str}")

        if review.errors:
            st.warning("The request did not finish cleanly. Only completed checks from this request appear below.")
        
        # Check if there is a software blocker
        has_software_blocker = False
        if review.readiness:
            for ev in review.readiness.labs:
                for r in ev.reasons:
                    if "installed versions" in r or "Requires" in r:
                        has_software_blocker = True
                        break
        
        if has_software_blocker:
            st.markdown(
                '<div class="prep-callout">'
                '<strong>💡 Software blocker detected:</strong> A software version mismatch was identified in lab records. '
                'If you are testing or preparing a local computer, use the <strong>Prepare this computer</strong> section below to create '
                'an isolated, verified Python environment with approved PyPI packages.'
                '</div>',
                unsafe_allow_html=True
            )

        st.markdown("### Lab readiness")
        if review.readiness:
            for evidence in review.readiness.labs:
                lab_card(evidence, session)
        else:
            st.info("The original time window was not checked in this request. Only alternative results are available.")
        st.caption("Missing resources mean absent or mismatched in the demonstration records. Unreadable or invalid data is unknown, not a confirmed shortage.")
        
        st.markdown("### Validated alternatives")
        alternatives = review.alternatives
        if alternatives:
            if not alternatives.alternatives:
                st.info("No feasible alternative found.")
                st.markdown(
                    "<p style='color:#64748b; font-size:0.9rem;'><strong>What would need to change:</strong><br/>"
                    "• Consider relaxing the preferred lab constraint to allow other rooms.<br/>"
                    "• Enable batch splitting if total student count exceeds single-room working computers.<br/>"
                    "• Check an alternative date or an expanded operating window.</p>",
                    unsafe_allow_html=True
                )
            for candidate in alternatives.alternatives[:3]:
                lab_card(candidate.evidence, candidate.session, alternative=True, candidate=candidate)
            
            # Show audit trail of rejected candidates
            if getattr(alternatives, "rejected", None):
                with st.expander(f"Audit trail: rejected candidate alternatives ({len(alternatives.rejected)} rejected)"):
                    st.caption("Deterministic evaluation rejected these arrangements for failing one or more mandatory constraints:")
                    for rej in alternatives.rejected:
                        st.markdown(f"**{rej.candidate_type} · {rej.lab_name} ({rej.time_slot})**")
                        for reason in rej.reasons:
                            st.markdown(f"<span style='color:#b91c1c; font-size:0.87rem;'>• {escape(reason)}</span>", unsafe_allow_html=True)
                        st.write("")
        elif review.readiness and review.readiness.status == "READY":
            st.caption("A lab already meets the original request. No alternative search was performed.")
        else:
            st.caption("Alternative search was not completed. Availability of alternatives is unknown.")

    with st.expander("How this was checked"):
        st.caption("Actual action proposals and execution records only. Application-triggered actions are labelled separately. No hidden reasoning is displayed.")
        if not review.trace:
            st.write("No activity recorded for this request.")
        for index, event in enumerate(review.trace, 1):
            source = "Application-triggered" if event["source"] == "application" else "Model / validated agent"
            st.markdown(f"**{index}. {source} · {event['event'].replace('_', ' ')}**")
            st.json({k: v for k, v in event.items() if k not in {"source", "event"}}, expanded=False)


def main():
    st.markdown('<div class="eyebrow">LABREADY · COLLEGE LAB READINESS & VERIFIED ALTERNATIVES</div>', unsafe_allow_html=True)
    heading, reset = st.columns([5, 1])
    heading.title("LabReady")
    reset.button("New session", on_click=new_session, use_container_width=True)
    st.markdown('<div class="headline">Prepare your lab. Verify it works.</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Deterministic lab readiness, conflict detection, student-batch planning, and verified alternatives for scheduled practicals.</div>', unsafe_allow_html=True)
    st.info("Demonstration data — not verified college availability.")

    # Visual Workflow Stepper
    st.markdown(
        '<div class="stepper">'
        '<span class="step done">1. Define Practical</span>'
        '<span class="step-arrow">→</span>'
        '<span class="step done">2. Check Readiness</span>'
        '<span class="step-arrow">→</span>'
        '<span class="step active">3. Identify Blockers</span>'
        '<span class="step-arrow">→</span>'
        '<span class="step">4. Find Alternatives</span>'
        '<span class="step-arrow">→</span>'
        '<span class="step">5. Verify & Decide</span>'
        '</div>',
        unsafe_allow_html=True
    )

    # Initialize session state conversation
    try:
        if "conversation" not in st.session_state:
            st.session_state["conversation"] = Conversation()
    except Exception as exc:
        st.error(f"Cannot initialize LabReady: {exc}. Check OLLAMA_MODEL and run check_setup.py.")
        return
    conversation = st.session_state["conversation"]
    waiting = conversation.busy or "pending" in st.session_state or "pending_session" in st.session_state

    # Demonstration Scenario Presets Bar
    st.markdown("#### Instant Demo Scenarios")
    s_col1, s_col2, s_col3, s_col4 = st.columns(4)
    with s_col1:
        st.button("Demo A: Practical Ready", on_click=set_scenario, args=("demo_a",), disabled=waiting, use_container_width=True, help="50 students, Python 3.12 at 13:00 - all checks PASS")
    with s_col2:
        st.button("Demo B: Blocked + Alternative", on_click=set_scenario, args=("demo_b",), disabled=waiting, use_container_width=True, help="60 students, Python 3.12 at 10:00 - booking conflict, verified 12:00 slot found")
    with s_col3:
        st.button("Demo C: No Alternative", on_click=set_scenario, args=("demo_c",), disabled=waiting, use_container_width=True, help="70 students, unverified ROS 2.0 - all options blocked/unverified")
    with s_col4:
        st.button("Demo D: Batch Splitting", on_click=set_scenario, args=("demo_d",), disabled=waiting, use_container_width=True, help="60 students in Lab D (cap 35) split into 2 verified batches")

    st.write("")
    request_panel, result_panel = st.columns([1.1, 1.7], gap="large")

    with request_panel:
        st.subheader("Define your practical")
        st.markdown(f'<div class="model">Local model · {escape(conversation.agent.model)}</div>', unsafe_allow_html=True)
        st.caption("Enter practical specifications via natural language with local Gemma or the structured form below.")
        
        mode_tab1, mode_tab2 = st.tabs(["Natural Language (AI-Assisted)", "Structured Form (Deterministic)"])

        with mode_tab1:
            st.caption("Include a date, time window, student count, and software with exact versions.")
            st.button("Load example", on_click=load_example, disabled=waiting)
            with st.form("session_request"):
                st.text_area("Session request or follow-up", key="request_text", height=160,
                             placeholder="e.g. Check Python 3.12 for 60 students on 2026-10-27, 10:00 to 12:00.")
                st.form_submit_button("Check readiness", type="primary", use_container_width=True,
                                      on_click=queue_check, disabled=waiting)
            st.caption("All session times use Asia/Kolkata. One working computer per student.")
            if conversation.messages:
                with st.expander("Conversation", expanded=bool(conversation.latest and conversation.latest.needs_clarification)):
                    for message in conversation.messages:
                        st.markdown("**You**" if message["role"] == "user" else "**LabReady**")
                        st.text(message["text"])

        with mode_tab2:
            with st.form("structured_practical_form"):
                prac_name = st.text_input("Practical or Subject Name", value="Data Science Practical")
                f_col1, f_col2 = st.columns(2)
                req_date = f_col1.text_input("Required Date (YYYY-MM-DD)", value="2026-10-27")
                req_students = f_col2.number_input("Number of Students", min_value=1, max_value=200, value=60, step=1)
                
                t_col1, t_col2 = st.columns(2)
                req_start = t_col1.text_input("Start Time (HH:MM)", value="10:00")
                req_end = t_col2.text_input("End Time (HH:MM)", value="12:00")

                sw_col1, sw_col2 = st.columns([1.5, 1])
                sw_name = sw_col1.text_input("Required Software", value="Python")
                sw_ver = sw_col2.text_input("Version", value="3.12")

                req_eq = st.multiselect("Required Equipment", options=["projector", "whiteboard", "robotic_arm"], default=["projector", "whiteboard"])
                pref_lab = st.selectbox("Preferred Lab (Optional)", options=["Any lab", "lab-a", "lab-b", "lab-c", "lab-d", "lab-e"], index=0)

                st.markdown("**Batch Planning & Window Constraints**")
                allow_split = st.checkbox("Allow splitting students into batches if room is too small", value=False)
                max_b = st.slider("Max Batches", min_value=2, max_value=4, value=2) if allow_split else 2

                submit_struct = st.form_submit_button("Check readiness (Deterministic)", type="primary", use_container_width=True, disabled=waiting)
                if submit_struct:
                    try:
                        chosen_lab = None if pref_lab == "Any lab" else pref_lab
                        new_sess = Session(
                            practical_name=prac_name.strip() or "Practical",
                            date=req_date.strip(),
                            start=req_start.strip(),
                            end=req_end.strip(),
                            students=int(req_students),
                            software=[Software(name=sw_name.strip(), version=sw_ver.strip())],
                            equipment=req_eq,
                            preferred_lab=chosen_lab,
                            allow_batch_split=allow_split,
                            max_batches=int(max_b),
                        )
                        st.session_state["pending_session"] = (new_sess, uuid4().hex)
                    except Exception as exc:
                        st.error(f"Invalid input: {exc}")

    with result_panel:
        # Process deterministic pending session
        pending_session = st.session_state.pop("pending_session", None)
        if pending_session:
            sess, tok = pending_session
            with st.spinner("Executing deterministic lab checks and alternative verification…"):
                conversation.submit_session(sess, tok)
            st.rerun()

        # Process natural language pending submission
        pending = st.session_state.pop("pending", None)
        if pending:
            with st.spinner(f"Checking with {conversation.agent.model} and the current lab records…"):
                conversation.submit(*pending)
            st.rerun()

        if conversation.latest:
            results(conversation.latest)
        else:
            st.markdown(
                '<div class="empty">'
                '<h3>Know what will work before you book.</h3>'
                '<p>Select an instant demo scenario above or describe a practical to compare laboratory capacity, detect booking conflicts, plan student batches, and verify alternatives.</p>'
                '</div>',
                unsafe_allow_html=True
            )

    st.divider()

    # Secondary Workflow: Local Workstation Preparation & Deterministic Verification
    st.markdown('<div class="eyebrow">LOCAL COMPUTER PREPARATION · SECONDARY CAPABILITY</div>', unsafe_allow_html=True)
    render_preparation()

    st.divider()
    st.caption("Recommendations do not reserve labs. Results reflect records read during that check; recheck before making arrangements.")


if __name__ == "__main__":
    main()
