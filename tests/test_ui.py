import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock

from ollama import ChatResponse, ResponseError
from streamlit.testing.v1 import AppTest

from agent import Agent
from app import DEMO_REQUEST, demo_session
from tools import DATA, Repository
from ui_state import Conversation, error_guidance

ROOT = Path(__file__).resolve().parents[1]


def response(action="done", **fields):
    return ChatResponse(message={"role": "assistant", "content": json.dumps({"action": action, **fields})})


def checking_client():
    client = Mock()
    client.chat.side_effect = [response("check_session_readiness", arguments=demo_session().model_dump()), response()]
    return client


class StateTests(unittest.TestCase):
    def test_submission_deduplicates_reruns(self):
        client = checking_client()
        state = Conversation(Agent(client=client))
        self.assertTrue(state.submit(DEMO_REQUEST, "one"))
        self.assertFalse(state.submit(DEMO_REQUEST, "one"))
        self.assertEqual(client.chat.call_count, 2)
        self.assertEqual(state.latest.outcome, "blocked")
        self.assertEqual(len(state.latest.alternatives.alternatives), 3)

    def test_trace_records_validation_execution_and_policy_source(self):
        state = Conversation(Agent(client=checking_client()))
        state.submit(DEMO_REQUEST, "one")
        events = state.latest.trace
        self.assertTrue(any(e["event"] == "action_proposed" for e in events))
        self.assertTrue(any(e["event"] == "arguments_validated" for e in events))
        self.assertTrue(any(e["event"] == "tool_succeeded" and e["source"] == "application" for e in events))
        self.assertTrue(all("thinking" not in e for e in events))

    def test_rejected_action_has_no_execution_event(self):
        client = Mock()
        client.chat.side_effect = [response("shell", arguments={}), response()]
        state = Conversation(Agent(client=client))
        state.submit("run something", "one")
        self.assertTrue(any(e["event"] == "action_rejected" for e in state.latest.trace))
        self.assertFalse(any(e["event"] == "tool_started" for e in state.latest.trace))

    def test_clarification_followup_retains_history(self):
        client = Mock()
        client.chat.side_effect = [response("clarify", question="What date and time?"),
                                   response("check_session_readiness", arguments=demo_session().model_dump()), response()]
        state = Conversation(Agent(client=client))
        state.submit("Check Python 3.12 for 60 students", "one")
        self.assertTrue(state.latest.needs_clarification)
        state.submit("2026-10-27 from 10:00 to 12:00.", "two")
        self.assertEqual(state.latest.outcome, "blocked")
        self.assertEqual(len([m for m in state.agent.history if m["role"] == "user"]), 2)

    def test_failed_new_request_removes_previous_results(self):
        client = checking_client()
        state = Conversation(Agent(client=client))
        state.submit(DEMO_REQUEST, "one")
        previous = state.latest
        client.chat.side_effect = ConnectionError("Ollama is offline")
        state.submit(DEMO_REQUEST, "two")
        self.assertTrue(previous.results)
        self.assertEqual(state.latest.results, [])
        self.assertIsNone(state.latest.readiness)
        self.assertEqual(state.latest.outcome, "incomplete")
        self.assertIn("Ollama", state.latest.errors[0])

    def test_missing_model_is_actionable(self):
        client = Mock()
        client.chat.side_effect = ResponseError("model not found", 404)
        state = Conversation(Agent(client=client))
        state.submit(DEMO_REQUEST, "one")
        self.assertIn("ollama pull", state.latest.errors[0])
        self.assertFalse(state.latest.needs_clarification)

    def test_inventory_failure_does_not_ask_for_session_details_again(self):
        with tempfile.TemporaryDirectory() as folder:
            shutil.copyfile(DATA / "labs.json", Path(folder) / "labs.json")
            (Path(folder) / "bookings.json").write_text('{"bookings":')
            client = Mock()
            client.chat.side_effect = [response("check_session_readiness", arguments=demo_session().model_dump()),
                                       response("clarify", question="What date?")]
            state = Conversation(Agent(client=client, repository=Repository(folder)))
            state.submit(DEMO_REQUEST, "one")
            self.assertFalse(state.latest.needs_clarification)
            self.assertFalse(state.latest.results)
            self.assertIn("Repair data/labs.json", error_guidance(state.latest.errors[0]))

    def test_unexpected_failure_and_blank_submission_clear_results(self):
        state = Conversation(Agent(client=checking_client()))
        state.submit(DEMO_REQUEST, "one")
        state.agent.run = Mock(side_effect=RuntimeError("unexpected"))
        state.submit(DEMO_REQUEST, "two")
        self.assertFalse(state.latest.results)
        self.assertFalse(state.latest.trace)
        self.assertFalse(state.busy)
        state.submit(" ", "three")
        self.assertIn("Describe", state.latest.errors[0])

    def test_changed_booking_is_reloaded_on_new_submission(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("labs.json", "bookings.json"):
                shutil.copyfile(DATA / name, Path(folder) / name)
            client = Mock()
            client.chat.side_effect = [response("check_session_readiness", arguments=demo_session().model_dump()), response(),
                                       response("check_session_readiness", arguments=demo_session().model_dump()), response()]
            state = Conversation(Agent(client=client, repository=Repository(folder)))
            state.submit(DEMO_REQUEST, "one")
            self.assertTrue(state.latest.alternatives.alternatives)
            path = Path(folder) / "bookings.json"
            data = json.loads(path.read_text())
            data["bookings"].append({"id": "fixture-change", "lab_id": "lab-b", "date": "2026-10-27", "start": "12:00", "end": "17:00"})
            path.write_text(json.dumps(data))
            state.submit(DEMO_REQUEST, "two")
            self.assertEqual(state.latest.alternatives.message, "No feasible alternative found.")
            self.assertEqual(state.latest.alternatives.alternatives, [])


class StreamlitTests(unittest.TestCase):
    def app(self, state=None):
        app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=15)
        if state is not None:
            app.session_state["conversation"] = state
        return app.run()

    def button(self, app, label):
        return next(b for b in app.button if b.label == label)

    def test_example_loads_without_execution_and_reset_clears(self):
        client = Mock()
        state = Conversation(Agent(client=client))
        app = self.app(state)
        self.assertFalse(app.exception)
        self.button(app, "Load example").click().run()
        self.assertEqual(app.text_area[0].value, DEMO_REQUEST)
        client.chat.assert_not_called()
        self.button(app, "New session").click().run()
        self.assertEqual(app.text_area[0].value, "")
        self.assertIsNone(app.session_state["conversation"].latest)

    def test_results_render_once_and_failure_replaces_success(self):
        client = checking_client()
        app = self.app(Conversation(Agent(client=client)))
        app.text_area[0].input(DEMO_REQUEST)
        self.button(app, "Check readiness").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(h.value == "All checked labs blocked" for h in app.subheader))
        self.assertTrue(any("Lab A" in m.value and "42 working" in m.value for m in app.markdown))
        app.run()  # Rerun must not invoke the model again.
        self.assertEqual(client.chat.call_count, 2)
        client.chat.side_effect = TimeoutError("deadline exceeded")
        self.button(app, "Check readiness").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(h.value == "Incomplete / error" for h in app.subheader))
        self.assertFalse(any("lab-card" in m.value and "Lab A" in m.value for m in app.markdown))
        self.assertTrue(any("timed out" in error.value for error in app.error))


if __name__ == "__main__":
    unittest.main()
