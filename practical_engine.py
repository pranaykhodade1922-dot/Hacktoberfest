"""Deterministic readiness, alternative-finding, batch-planning, and verification engine.

Zero AI dependency: all decisions are grounded in validated institutional records.
"""
from datetime import datetime
import json
from pathlib import Path
from typing import Literal

from schemas import (
    Alternatives,
    Booking,
    Candidate,
    Evidence,
    Lab,
    Readiness,
    RejectedCandidate,
    Search,
    Session,
    Software,
    VerificationCheck,
    minutes,
)

DATA = Path(__file__).resolve().parent / "data"


def clock(total_minutes: int) -> str:
    """Format total minutes since midnight into HH:MM."""
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def evaluate_checks(session: Session, lab: Lab, bookings: list[Booking]) -> tuple[list[VerificationCheck], list[str], list[str]]:
    """Perform deterministic, granular verification checks for a lab against requirements.

    Returns:
        (checks, reasons, conflicting_booking_ids)
    """
    checks: list[VerificationCheck] = []
    reasons: list[str] = []

    # 1. Capacity: Room Capacity
    if lab.capacity >= session.students:
        checks.append(VerificationCheck(
            category="capacity",
            name="Room Capacity",
            status="PASS",
            evidence=f"Room capacity {lab.capacity} >= {session.students} students",
            details=f"{lab.capacity} total seats available in {lab.name}"
        ))
    else:
        msg = f"Room capacity {lab.capacity} < {session.students} students."
        reasons.append(msg)
        checks.append(VerificationCheck(
            category="capacity",
            name="Room Capacity",
            status="FAIL",
            evidence=msg,
            details=f"Shortfall of {session.students - lab.capacity} student spaces"
        ))

    # 2. Capacity: Working Computers (one per student)
    if lab.working_computers >= session.students:
        checks.append(VerificationCheck(
            category="capacity",
            name="Working Computers",
            status="PASS",
            evidence=f"Working computers {lab.working_computers} >= {session.students} required (one per student)",
            details=f"{lab.working_computers} verified operational workstations"
        ))
    else:
        msg = f"Working computers {lab.working_computers} < {session.students} required (one per student)."
        reasons.append(msg)
        checks.append(VerificationCheck(
            category="capacity",
            name="Working Computers",
            status="FAIL",
            evidence=msg,
            details=f"{lab.working_computers} working vs {session.students} needed"
        ))

    # 3. Software Readiness
    for required in session.software:
        matching_installed = [
            s for s in lab.software
            if s.name.casefold() == required.name.casefold()
        ]
        installed_versions = [s.version for s in matching_installed]
        
        # Check if explicitly unverified in lab inventory
        unverified_names = [u.casefold() for u in lab.unverified_software]
        is_unverified = required.name.casefold() in unverified_names or any(
            not s.verified for s in matching_installed if s.version == required.version
        )

        if required.version in installed_versions:
            if is_unverified:
                msg = f"Software {required.name} {required.version} is installed but unverified in records."
                reasons.append(msg)
                checks.append(VerificationCheck(
                    category="software",
                    name=f"Software: {required.name}",
                    status="UNKNOWN",
                    evidence=msg,
                    details="Inventory record lacks verification signature or physical audit"
                ))
            else:
                checks.append(VerificationCheck(
                    category="software",
                    name=f"Software: {required.name}",
                    status="PASS",
                    evidence=f"{required.name} {required.version} verified and installed",
                    details=f"Exact match on version {required.version}"
                ))
        else:
            ver_text = ", ".join(installed_versions) or "none"
            msg = f"Requires {required.name} {required.version}; installed versions: {ver_text} (exact match required)."
            reasons.append(msg)
            checks.append(VerificationCheck(
                category="software",
                name=f"Software: {required.name}",
                status="FAIL",
                evidence=msg,
                details=f"Target: {required.version}, Found: {ver_text}"
            ))

    # 4. Equipment Readiness
    unverified_eq = [u.casefold() for u in lab.unverified_equipment]
    lab_equipment_map = {x.casefold(): x for x in lab.equipment}
    for item in session.equipment:
        item_cf = item.casefold()
        if item_cf in lab_equipment_map:
            if item_cf in unverified_eq:
                msg = f"Equipment '{item}' listed in inventory but unverified."
                reasons.append(msg)
                checks.append(VerificationCheck(
                    category="equipment",
                    name=f"Equipment: {item}",
                    status="UNKNOWN",
                    evidence=msg,
                    details="Operational status not confirmed by facility staff"
                ))
            else:
                checks.append(VerificationCheck(
                    category="equipment",
                    name=f"Equipment: {item}",
                    status="PASS",
                    evidence=f"Equipment '{item}' verified and available",
                    details=f"Listed in {lab.name} equipment registry"
                ))
        else:
            msg = f"Missing equipment: {item}."
            reasons.append(msg)
            checks.append(VerificationCheck(
                category="equipment",
                name=f"Equipment: {item}",
                status="FAIL",
                evidence=msg,
                details=f"Not registered in {lab.name}"
            ))

    # 5. Booking Conflicts
    s_start = minutes(session.start)
    s_end = minutes(session.end)
    conflicts = [
        b for b in bookings
        if b.lab_id == lab.id
        and b.date == session.date
        and s_start < minutes(b.end)
        and minutes(b.start) < s_end
    ]
    conflicting_ids = [b.id for b in conflicts]
    if conflicts:
        for b in conflicts:
            reasons.append(f"Booking {b.id} overlaps {b.start}-{b.end}.")
        checks.append(VerificationCheck(
            category="booking",
            name="Schedule Availability",
            status="FAIL",
            evidence=f"Conflicting booking(s): {', '.join(conflicting_ids)}",
            details=f"Overlaps requested practical interval {session.start}-{session.end}"
        ))
    else:
        checks.append(VerificationCheck(
            category="booking",
            name="Schedule Availability",
            status="PASS",
            evidence="No overlapping bookings in the records",
            details="Laboratory is free during the requested time window"
        ))

    # 6. Time Window Consistency
    window_start = minutes(getattr(session, "allowed_window_start", "09:00"))
    window_end = minutes(getattr(session, "allowed_window_end", "17:00"))
    if s_start >= window_start and s_end <= window_end:
        checks.append(VerificationCheck(
            category="time_window",
            name="Permitted Time Window",
            status="PASS",
            evidence=f"Practical slot {session.start}-{session.end} fits within permitted window ({clock(window_start)}-{clock(window_end)})",
            details="Operational hours constraint satisfied"
        ))
    else:
        msg = f"Slot {session.start}-{session.end} falls outside permitted operational window {clock(window_start)}-{clock(window_end)}."
        reasons.append(msg)
        checks.append(VerificationCheck(
            category="time_window",
            name="Permitted Time Window",
            status="FAIL",
            evidence=msg,
            details="Session must be scheduled during facility operating hours"
        ))

    return checks, reasons, conflicting_ids


def evaluate(session: Session, lab: Lab, bookings: list[Booking]) -> Evidence:
    """Evaluate a laboratory against a session's requirements deterministically."""
    checks, reasons, conflicting_ids = evaluate_checks(session, lab, bookings)
    
    # Determine overall status according to strict verification rule:
    # Any FAIL -> BLOCKED
    # Any UNKNOWN -> UNVERIFIED
    # All PASS (or NOT_APPLICABLE) -> READY
    has_fail = any(c.status == "FAIL" for c in checks)
    has_unknown = any(c.status == "UNKNOWN" for c in checks)
    
    if has_fail:
        status: Literal["READY", "BLOCKED", "UNVERIFIED"] = "BLOCKED"
    elif has_unknown:
        status = "UNVERIFIED"
    else:
        status = "READY"

    return Evidence(
        lab_id=lab.id,
        lab_name=lab.name,
        status=status,
        reasons=reasons,
        capacity=lab.capacity,
        working_computers=lab.working_computers,
        installed_software=lab.software,
        equipment=lab.equipment,
        conflicting_booking_ids=conflicting_ids,
        checks=checks,
    )


def verify_candidate(candidate: Candidate, repository) -> Candidate:
    """Re-verify every aspect of a proposed candidate deterministically before presentation."""
    labs, bookings = repository.load()
    lab_map = {lab.id: lab for lab in labs}

    if candidate.is_split and candidate.batches:
        verified_batches = []
        verified_evidences = []
        all_passed = True
        has_unknown = False

        for batch_session in candidate.batches:
            lab = lab_map.get(batch_session.preferred_lab)
            if not lab:
                all_passed = False
                break
            ev = evaluate(batch_session, lab, bookings)
            verified_evidences.append(ev)
            if ev.status == "BLOCKED":
                all_passed = False
            elif ev.status == "UNVERIFIED":
                has_unknown = True

        status = "READY" if all_passed and not has_unknown else ("UNVERIFIED" if has_unknown else "BLOCKED")
        return Candidate(
            session=candidate.session,
            evidence=candidate.evidence,
            batches=candidate.batches,
            batch_evidences=verified_evidences,
            is_split=True,
            verification_status=status
        )
    else:
        lab = lab_map.get(candidate.session.preferred_lab)
        if not lab:
            candidate.evidence.status = "BLOCKED"
            candidate.verification_status = "BLOCKED"
            return candidate
        fresh_evidence = evaluate(candidate.session, lab, bookings)
        return Candidate(
            session=candidate.session,
            evidence=fresh_evidence,
            is_split=False,
            verification_status=fresh_evidence.status
        )


def find_alternatives_with_batches(
    session: Session | dict,
    opening: str = "09:00",
    closing: str = "17:00",
    repository=None,
    max_candidates: int = 3,
) -> Alternatives:
    """Search for feasible alternative labs, time slots, and student-batch splits.

    Re-verifies all candidates and explains rejected options.
    """
    from tools import Repository
    repo = repository or Repository()
    search = Search.model_validate({"session": session, "opening": opening, "closing": closing})
    session = search.session
    labs, bookings = repo.load()

    if session.preferred_lab and session.preferred_lab not in {lab.id for lab in labs}:
        raise ValueError("Unknown preferred_lab; use a stable lab ID such as lab-b")

    duration = minutes(session.end) - minutes(session.start)
    found: list[Candidate] = []
    rejected: list[RejectedCandidate] = []

    # 1. Standard single-session search across labs and time slots
    for start in range(minutes(opening), minutes(closing) - duration + 1):
        for lab in sorted(labs, key=lambda lab: lab.id):
            if start == minutes(session.start) and (not session.preferred_lab or lab.id == session.preferred_lab):
                continue  # Original requested slot reported in readiness
            candidate_session = Session.model_validate({
                **session.model_dump(),
                "start": clock(start),
                "end": clock(start + duration),
                "preferred_lab": lab.id,
            })
            evidence = evaluate(candidate_session, lab, bookings)
            if evidence.status == "READY":
                cand = Candidate(
                    session=candidate_session,
                    evidence=evidence,
                    is_split=False,
                    verification_status="READY",
                )
                verified = verify_candidate(cand, repo)
                if verified.verification_status == "READY":
                    found.append(verified)
                    if len(found) >= max_candidates:
                        return Alternatives(
                            original=session,
                            alternatives=found,
                            message="Validated alternatives; no reservation made.",
                            rejected=rejected[:10],
                        )
            else:
                if len(rejected) < 15:
                    rejected.append(RejectedCandidate(
                        candidate_type="Single session (room/time)",
                        lab_id=lab.id,
                        lab_name=lab.name,
                        time_slot=f"{clock(start)}-{clock(start + duration)}",
                        reasons=evidence.reasons,
                    ))

    # 2. Student-Batch Planning (if permitted and single-session options exhausted or needed)
    if session.allow_batch_split and session.students > 1:
        max_batches = getattr(session, "max_batches", 2)
        for num_batches in range(2, min(max_batches + 1, session.students + 1)):
            batch_size = (session.students + num_batches - 1) // num_batches
            for lab in sorted(labs, key=lambda lab: lab.id):
                # Lab must be able to hold the split batch size
                if lab.capacity < batch_size or lab.working_computers < batch_size:
                    rejected.append(RejectedCandidate(
                        candidate_type=f"Batch split ({num_batches} batches of {batch_size})",
                        lab_id=lab.id,
                        lab_name=lab.name,
                        time_slot="All slots",
                        reasons=[f"Lab capacity or working computers ({lab.working_computers}) cannot hold even split batch of {batch_size}"],
                    ))
                    continue

                # Try to schedule consecutive or available slots within opening..closing
                scheduled_batches: list[Session] = []
                batch_evidences: list[Evidence] = []
                current_start = minutes(opening)
                simulated_bookings = list(bookings)

                for b_idx in range(num_batches):
                    # Compute students for this batch
                    remaining_students = session.students - (b_idx * batch_size)
                    this_batch_size = min(batch_size, remaining_students)
                    if this_batch_size <= 0:
                        break

                    slot_found = False
                    for b_start in range(current_start, minutes(closing) - duration + 1):
                        b_session = Session.model_validate({
                            **session.model_dump(),
                            "start": clock(b_start),
                            "end": clock(b_start + duration),
                            "students": this_batch_size,
                            "preferred_lab": lab.id,
                            "allow_batch_split": False,
                        })
                        ev = evaluate(b_session, lab, simulated_bookings)
                        if ev.status == "READY":
                            scheduled_batches.append(b_session)
                            batch_evidences.append(ev)
                            # Book this slot in simulation so subsequent batches don't overlap
                            simulated_bookings.append(Booking(
                                id=f"sim-batch-{b_idx+1}",
                                lab_id=lab.id,
                                date=session.date,
                                start=clock(b_start),
                                end=clock(b_start + duration),
                            ))
                            current_start = b_start + duration  # consecutive or after
                            slot_found = True
                            break
                    if not slot_found:
                        break

                if len(scheduled_batches) == num_batches:
                    # All batches successfully scheduled!
                    batch_cand = Candidate(
                        session=scheduled_batches[0],
                        evidence=batch_evidences[0],
                        batches=scheduled_batches,
                        batch_evidences=batch_evidences,
                        is_split=True,
                        verification_status="READY",
                    )
                    verified_batch = verify_candidate(batch_cand, repo)
                    if verified_batch.verification_status == "READY":
                        found.append(verified_batch)
                        if len(found) >= max_candidates:
                            return Alternatives(
                                original=session,
                                alternatives=found,
                                message="Validated alternatives; no reservation made.",
                                rejected=rejected[:10],
                            )
                else:
                    rejected.append(RejectedCandidate(
                        candidate_type=f"Batch split ({num_batches} batches)",
                        lab_id=lab.id,
                        lab_name=lab.name,
                        time_slot=f"{num_batches}x {duration}min slots",
                        reasons=[f"Could only find {len(scheduled_batches)} of {num_batches} conflict-free slots in {lab.name} within {opening}-{closing}"],
                    ))

    msg = "Validated alternatives; no reservation made." if found else "No feasible alternative found."
    return Alternatives(
        original=session,
        alternatives=found,
        message=msg,
        rejected=rejected,
    )
