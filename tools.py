"""Read-only domain logic. No model-generated feasibility decisions."""
import json
from pathlib import Path

from schemas import (Alternatives, Booking, Candidate, Evidence, Lab, Readiness,
                     Search, Session, minutes)

DATA = Path(__file__).resolve().parent / "data"


class Repository:
    def __init__(self, data_dir=DATA):
        self.data_dir = Path(data_dir)

    def load(self):
        labs = [Lab.model_validate(x) for x in json.loads((self.data_dir / "labs.json").read_text(encoding="utf-8"))["labs"]]
        bookings = [Booking.model_validate(x) for x in json.loads((self.data_dir / "bookings.json").read_text(encoding="utf-8"))["bookings"]]
        if not labs or len({x.id for x in labs}) != len(labs):
            raise ValueError("inventory must contain labs with unique IDs")
        if len({b.id for b in bookings}) != len(bookings):
            raise ValueError("booking IDs must be unique")
        if any(b.lab_id not in {lab.id for lab in labs} for b in bookings):
            raise ValueError("booking references an unknown lab")
        return labs, bookings


from practical_engine import evaluate as pe_evaluate, find_alternatives_with_batches


def evaluate(session: Session, lab: Lab, bookings: list[Booking]) -> Evidence:
    return pe_evaluate(session, lab, bookings)


def check_session_readiness(session: Session | dict, repository=None) -> Readiness:
    session = Session.model_validate(session)
    labs, bookings = (repository or Repository()).load()
    if session.preferred_lab:
        labs = [lab for lab in labs if lab.id == session.preferred_lab]
        if not labs:
            raise ValueError("Unknown preferred_lab; use a stable lab ID such as lab-b")
    evidence = [evaluate(session, lab, bookings) for lab in sorted(labs, key=lambda lab: lab.id)]
    if any(x.status == "READY" for x in evidence):
        status = "READY"
    elif any(x.status == "UNVERIFIED" for x in evidence):
        status = "UNVERIFIED"
    else:
        status = "BLOCKED"
    return Readiness(session=session, status=status, labs=evidence)


def clock(value):
    return f"{value // 60:02d}:{value % 60:02d}"


def find_alternatives(session: Session | dict, opening="09:00", closing="17:00", repository=None) -> Alternatives:
    return find_alternatives_with_batches(session, opening=opening, closing=closing, repository=repository)
