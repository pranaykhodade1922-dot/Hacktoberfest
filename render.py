"""Definitive CLI output comes exclusively from validated domain results."""
from schemas import Alternatives, Readiness

NOTICE = "FICTIONAL DEMONSTRATION DATA - not verified college availability."


def render(result):
    lines = [NOTICE]
    session = result.session if isinstance(result, Readiness) else result.original
    lines.append(f"{session.date} {session.start}-{session.end} Asia/Kolkata | {session.students} students")
    lines.append("Software: " + ", ".join(f"{s.name} {s.version}" for s in session.software))
    lines.append("Equipment: " + (", ".join(session.equipment) or "none requested"))
    if isinstance(result, Readiness):
        lines.append(f"Session: {result.status}")
        for lab in result.labs:
            lines.append(f"{lab.lab_name} ({lab.lab_id}): {lab.status}")
            lines.extend(f"  - {reason}" for reason in lab.reasons)
            if lab.status == "READY":
                lines.append(f"  Capacity {lab.capacity}; working computers {lab.working_computers}; all requirements met.")
    elif isinstance(result, Alternatives):
        lines.append(result.message)
        for candidate in result.alternatives:
            s, evidence = candidate.session, candidate.evidence
            lines.append(f"  {evidence.lab_name} ({evidence.lab_id}): {s.date} {s.start}-{s.end} Asia/Kolkata - {evidence.status}")
            if getattr(candidate, "is_split", False) and candidate.batches:
                lines.append(f"    Split into {len(candidate.batches)} batches:")
                for b_idx, (b_s, b_e) in enumerate(zip(candidate.batches, candidate.batch_evidences), 1):
                    lines.append(f"      Batch {b_idx}: {b_s.students} students, {b_s.start}-{b_s.end} in {b_e.lab_name}")
            else:
                lines.append(f"    Capacity {evidence.capacity}; working computers {evidence.working_computers}; all requirements met.")
        if getattr(result, "rejected", None):
            lines.append("Rejected candidates audit:")
            for rej in result.rejected[:5]:
                lines.append(f"  - {rej.candidate_type} ({rej.lab_name} {rej.time_slot}): {'; '.join(rej.reasons)}")
    lines.append("Recommendations do not reserve a lab. Recheck before use; bookings can change.")
    return "\n".join(lines)
