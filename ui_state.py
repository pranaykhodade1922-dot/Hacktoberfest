"""Per-browser-session adapter. No Streamlit globals and no availability cache."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from agent import Agent
from schemas import Alternatives, Readiness, Session

CLARIFICATION = (
    "What date (YYYY-MM-DD), start and end times (HH:MM), student count, and "
    "software with exact versions should I use? Include any required equipment "
    "or preferred lab. You can supply just the missing details below."
)


def error_guidance(error):
    if "Action validation failed" in error:
        return "The model returned an invalid JSON action. That proposal was not executed. Retry with an explicit date, time window, student count, and exact software versions. Validation details are in the activity log."
    if "validation error" in error.casefold() and "Tool " in error:
        return "The request or inventory failed validation. Check the supplied values and local data files; the activity log identifies the invalid fields. Availability has not been assumed."
    if "Tool " in error and "Expecting" in error:
        return "The local inventory or bookings contain invalid JSON. Repair data/labs.json or data/bookings.json, then check again. Availability is unknown; the activity log contains the error details."
    return error


@dataclass
class Review:
    request: str
    checked_at: str
    results: list = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    needs_clarification: bool = False

    @property
    def session(self):
        if not self.results:
            return None
        last = self.results[-1]
        return last.session if isinstance(last, Readiness) else last.original

    @property
    def readiness(self):
        return next((r for r in reversed(self.results)
                     if isinstance(r, Readiness) and r.session == self.session), None)

    @property
    def alternatives(self):
        return next((r for r in reversed(self.results)
                     if isinstance(r, Alternatives) and r.original == self.session), None)

    @property
    def outcome(self):
        if self.errors or self.needs_clarification or not self.results:
            return "incomplete"
        if self.readiness:
            if self.readiness.status == "READY":
                return "ready"
            if self.readiness.status == "UNVERIFIED":
                return "unverified"
            return "blocked"
        if self.alternatives and self.alternatives.alternatives:
            return "alternatives"
        return "incomplete"


class Conversation:
    def __init__(self, agent=None):
        self.agent = agent if agent is not None else Agent()
        self.latest = None
        self.messages = []
        self.busy = False
        self.last_token = None

    def submit_session(self, session: Session, token: str):
        """Execute deterministic readiness and alternative checks without invoking LLM."""
        if self.busy or token == self.last_token:
            return False
        self.last_token = token
        self.busy = True
        self.latest = Review(
            request=f"{session.practical_name or 'Practical'}: {session.date} {session.start}-{session.end}, {session.students} students",
            checked_at=datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
        )
        try:
            from tools import check_session_readiness, find_alternatives
            readiness = check_session_readiness(session, self.agent.repository)
            self.latest.results.append(readiness)
            self.latest.trace.append({
                "event": "deterministic_readiness_checked",
                "source": "application",
                "status": readiness.status
            })
            if readiness.status != "READY":
                alts = find_alternatives(session, repository=self.agent.repository)
                self.latest.results.append(alts)
                self.latest.trace.append({
                    "event": "deterministic_alternatives_checked",
                    "source": "application",
                    "count": len(alts.alternatives)
                })
        except Exception as exc:
            self.latest.errors = [str(exc)]
        finally:
            self.busy = False
        return True

    def submit(self, text, token):
        """A unique explicit submission runs once; rerenders never execute tools."""
        if self.busy or token == self.last_token:
            return False
        self.last_token = token
        self.busy = True
        # Clear first, including on an unexpected exception or invalid input.
        self.latest = Review(request=text.strip(), checked_at=datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S"))
        try:
            if not text.strip():
                self.latest.errors = ["Describe a practical session before checking readiness."]
                return True
            self.messages.append({"role": "user", "text": text.strip()})
            self.agent.last_results = []
            self.agent.last_errors = []
            self.agent.last_trace = []
            self.agent.run(text.strip())  # Structured results, never the returned CLI prose.
            self.latest.results = deepcopy(self.agent.last_results)
            self.latest.errors = list(self.agent.last_errors)
            self.latest.trace = deepcopy(self.agent.last_trace)
            self.latest.needs_clarification = (
                any("Clarification required" in error for error in self.latest.errors)
                or (not self.latest.errors and (self.agent.needs_clarification or not self.latest.results))
            )
            summary = {"ready": "Ready lab found.", "blocked": "All checked labs are blocked; review alternatives.",
                       "unverified": "Readiness unverified; manual inventory audit needed.",
                       "alternatives": "Validated alternatives found.", "incomplete": "This check is incomplete."}[self.latest.outcome]
            self.messages.append({"role": "assistant", "text": CLARIFICATION if self.latest.needs_clarification else summary})
        except Exception as exc:
            self.latest.errors = [f"The check could not finish ({type(exc).__name__}): {exc}. Retry or start a new session; run check_setup.py if it persists."]
            self.latest.trace = deepcopy(getattr(self.agent, "last_trace", []))
        finally:
            self.busy = False
        return True
