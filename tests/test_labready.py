import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from ollama import ChatResponse
from pydantic import ValidationError

from agent import Action, Agent
from config import get_model
from app import demo_session
from render import render
from schemas import Session
from tools import DATA, Repository, check_session_readiness, find_alternatives


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        for name in ("labs.json", "bookings.json"):
            shutil.copyfile(DATA / name, self.path / name)
        self.repo = Repository(self.path)
        self.session = demo_session()

    def change(self, **fields):
        return Session.model_validate({**self.session.model_dump(), **fields})

    def check(self, **fields):
        return check_session_readiness(self.change(**fields), self.repo)

    def test_demo_blockers(self):
        result = self.check()
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("Working computers 42", result.labs[0].reasons[0])
        self.assertEqual(result.labs[1].conflicting_booking_ids, ["booking-b-20261027-01"])
        self.assertIn("3.10", result.labs[2].reasons[0])

    def test_room_capacity(self):
        result = self.check(students=66, preferred_lab="lab-b")
        self.assertTrue(any("Room capacity" in r for r in result.labs[0].reasons))

    def test_missing_software_and_version(self):
        for software in ([{"name": "R", "version": "4.4"}], [{"name": "Python", "version": "3.12.0"}]):
            with self.subTest(software=software):
                result = self.check(software=software)
                self.assertTrue(all(any("installed versions" in r for r in lab.reasons) for lab in result.labs))

    def test_missing_equipment(self):
        result = self.check(equipment=["oscilloscope"])
        self.assertTrue(all("Missing equipment: oscilloscope." in lab.reasons for lab in result.labs))

    def test_overlap_and_adjacent_bookings(self):
        for start, end, status in [("09:30", "10:30", "BLOCKED"), ("10:30", "11:00", "BLOCKED"),
                                   ("09:00", "10:00", "READY"), ("12:00", "14:00", "READY")]:
            with self.subTest(start=start):
                self.assertEqual(self.check(start=start, end=end, preferred_lab="lab-b").status, status)

    def test_alternatives_preserve_requirements(self):
        result = find_alternatives(self.session, repository=self.repo)
        self.assertEqual(len(result.alternatives), 3)
        self.assertEqual(result.alternatives[0].session.start, "12:00")
        for candidate in result.alternatives:
            self.assertEqual(candidate.session.preferred_lab, "lab-b")
            self.assertEqual(candidate.session.students, 60)
            self.assertEqual(candidate.session.software, self.session.software)
            self.assertEqual(check_session_readiness(candidate.session, self.repo).status, "READY")

    def test_no_feasible_alternative(self):
        result = find_alternatives(self.change(students=100), repository=self.repo)
        self.assertEqual(result.alternatives, [])
        self.assertEqual(result.message, "No feasible alternative found.")

    def test_opening_hours_and_duration(self):
        result = find_alternatives(self.session, opening="14:00", closing="16:00", repository=self.repo)
        self.assertEqual(len(result.alternatives), 1)
        self.assertEqual(result.alternatives[0].session.start, "14:00")
        self.assertEqual(result.alternatives[0].session.end, "16:00")
        self.assertFalse(find_alternatives(self.session, opening="14:00", closing="15:00", repository=self.repo).alternatives)
        with self.assertRaises(ValidationError):
            find_alternatives(self.session, opening="17:00", closing="09:00", repository=self.repo)

    def test_changed_booking_invalidates_candidate(self):
        candidate = find_alternatives(self.session, repository=self.repo).alternatives[0]
        data = json.loads((self.path / "bookings.json").read_text())
        data["bookings"].append({"id": "new-booking", "lab_id": "lab-b", "date": "2026-10-27", "start": "12:00", "end": "17:00"})
        (self.path / "bookings.json").write_text(json.dumps(data))
        self.assertEqual(check_session_readiness(candidate.session, self.repo).status, "BLOCKED")
        self.assertFalse(find_alternatives(self.session, repository=self.repo).alternatives)

    def test_invalid_inputs(self):
        invalid = [{"students": True}, {"students": 0}, {"students": -1}, {"students": "60"},
                   {"date": "2026-02-30"}, {"date": "27/10/2026"}, {"start": "25:00"},
                   {"end": "10:00"}, {"end": "09:00"}, {"software": []},
                   {"software": [{"name": "Python"}]}, {"equipment": [True]}, {"unexpected": 1}]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                self.change(**fields)
        for field in ("date", "students", "software", "start", "end"):
            data = self.session.model_dump()
            del data[field]
            with self.subTest(missing=field), self.assertRaises(ValidationError):
                Session.model_validate(data)

    def test_unknown_lab_rejected(self):
        with self.assertRaises(ValueError):
            self.check(preferred_lab="invented")


def reply(*calls, content=""):
    if calls:
        name, args = calls[0]
        content = json.dumps({"action": name, "arguments": args})
    return ChatResponse(message={"role": "assistant", "content": content or '{"action":"done"}'})


class AgentTests(unittest.TestCase):
    def test_actual_tool_dispatch_and_history(self):
        client = Mock()
        client.chat.side_effect = [reply(("check_session_readiness", demo_session().model_dump())),
                                   reply(), reply()]
        agent = Agent(client=client)
        output = agent.run("Check Python 3.12 for 60 students on 2026-10-27 from 10:00 to 12:00.")
        self.assertIn("Lab A (lab-a): BLOCKED", output)
        self.assertIn("Validated alternatives", output)
        self.assertNotIn("Invented", output)
        self.assertTrue(any("Application result" in m["content"] for m in agent.history))
        self.assertNotIn("tools", client.chat.call_args.kwargs)
        self.assertIn("format", client.chat.call_args.kwargs)
        agent.run("What about later?")
        self.assertEqual(sum(m["role"] == "user" for m in agent.history), 2)

    def test_invalid_tool_and_arguments(self):
        agent = Agent(client=Mock())
        for name, arguments in [("shell", {"command": "dir"}),
                                ("check_session_readiness", {"session": demo_session().model_dump(), "extra": True}),
                                ("check_session_readiness", {"session": {"students": True}})]:
            with self.subTest(name=name), self.assertRaises((ValueError, ValidationError)):
                agent.dispatch(name, arguments)

    def test_json_encoded_arrays_rejected(self):
        agent = Agent(client=Mock())
        args = demo_session().model_dump()
        args["software"] = json.dumps(args["software"])
        args["equipment"] = "[]"
        with self.assertRaises(ValidationError):
            agent.dispatch("check_session_readiness", args)

    def test_missing_information_clarification(self):
        client = Mock()
        client.chat.return_value = reply(content='{"action":"clarify","question":"What date?"}')
        agent = Agent(client=client)
        output = agent.run("Check a Python practical")
        self.assertIn("Please provide or confirm", output)
        self.assertFalse(agent.last_results)

    def test_failed_tool_not_success(self):
        client = Mock()
        client.chat.side_effect = [reply(("check_session_readiness", {"session": {"students": True}})), reply()]
        agent = Agent(client=client)
        output = agent.run("Bad request")
        self.assertIn("failed", output)
        self.assertNotIn("Session: READY", output)

    def test_model_cannot_fill_missing_required_values(self):
        client = Mock()
        client.chat.side_effect = [reply(("check_session_readiness", demo_session().model_dump())), reply()]
        agent = Agent(client=client)
        output = agent.run("Check a Python practical")
        self.assertIn("Clarification required", output)
        self.assertFalse(agent.last_results)

    def test_bounded_loop(self):
        client = Mock()
        client.chat.return_value = reply(("unknown", {}))
        agent = Agent(client=client, max_rounds=2)
        self.assertIn("round limit", agent.run("repeat"))
        self.assertEqual(client.chat.call_count, 2)

    def test_connection_error(self):
        client = Mock()
        client.chat.side_effect = TimeoutError("deadline exceeded")
        agent = Agent(client=client)
        self.assertIn("TimeoutError", agent.run("check"))
        self.assertFalse(agent.last_results)

    def test_action_envelope_rejects_unsafe_or_invalid_proposals(self):
        for proposal in ["not JSON", '{"action":"shell","arguments":{}}',
                         '{"action":"done","extra":"payload"}',
                         json.dumps({"action": "check_session_readiness", "arguments": {**demo_session().model_dump(), "students": True}}),
                         json.dumps({"action": "check_session_readiness", "arguments": {**demo_session().model_dump(), "students": "60"}})]:
            with self.subTest(proposal=proposal), self.assertRaises(ValidationError):
                Action.model_validate_json(proposal, strict=True)

    def test_malformed_action_never_executes(self):
        client = Mock()
        client.chat.side_effect = [reply(content='{"action":"shell","arguments":{}}'), reply()]
        agent = Agent(client=client)
        with patch.object(agent, "dispatch") as dispatch:
            output = agent.run("run a shell")
        dispatch.assert_not_called()
        self.assertIn("Action validation failed", output)

    def test_model_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(get_model(), "gemma3:4b")
        with patch.dict("os.environ", {"OLLAMA_MODEL": "llama3.1:8b"}):
            self.assertEqual(Agent(client=Mock()).model, "llama3.1:8b")
        with patch.dict("os.environ", {"OLLAMA_MODEL": " "}), self.assertRaises(ValueError):
            get_model()


if __name__ == "__main__":
    unittest.main()
