"""Automated tests for the deterministic College Practical Readiness & Verification Engine.

Tests capacity, software, equipment, bookings, batch planning, unverified status,
alternative discovery, rejection audit trails, and offline deterministic operation.
"""
from datetime import datetime
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock

from pydantic import ValidationError

from practical_engine import evaluate, find_alternatives_with_batches, verify_candidate
from schemas import (
    Alternatives,
    Booking,
    Candidate,
    Evidence,
    Lab,
    Readiness,
    Session,
    Software,
    VerificationCheck,
)
from tools import DATA, Repository, check_session_readiness, find_alternatives
from ui_state import Conversation


class CollegeEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        for name in ("labs.json", "bookings.json"):
            shutil.copyfile(DATA / name, self.path / name)
        self.repo = Repository(self.path)

    def make_session(self, **kwargs):
        defaults = {
            "practical_name": "Test Practical",
            "date": "2026-10-27",
            "start": "10:00",
            "end": "12:00",
            "students": 60,
            "software": [{"name": "Python", "version": "3.12"}],
            "equipment": ["projector", "whiteboard"],
            "preferred_lab": None,
            "allow_batch_split": False,
            "max_batches": 2,
            "allowed_window_start": "09:00",
            "allowed_window_end": "17:00",
        }
        defaults.update(kwargs)
        return Session.model_validate(defaults)

    def test_sufficient_and_insufficient_capacity(self):
        labs, bookings = self.repo.load()
        lab_a = next(lab for lab in labs if lab.id == "lab-a")  # cap 60, working 42
        lab_b = next(lab for lab in labs if lab.id == "lab-b")  # cap 65, working 65

        # Insufficient working computers (42 < 50) even though room capacity 60 >= 50
        sess_50 = self.make_session(students=50)
        ev_a = evaluate(sess_50, lab_a, [])
        self.assertEqual(ev_a.status, "BLOCKED")
        self.assertTrue(any(c.name == "Working Computers" and c.status == "FAIL" for c in ev_a.checks))
        self.assertTrue(any(c.name == "Room Capacity" and c.status == "PASS" for c in ev_a.checks))

        # Room capacity insufficient (65 < 70)
        sess_70 = self.make_session(students=70)
        ev_b = evaluate(sess_70, lab_b, [])
        self.assertEqual(ev_b.status, "BLOCKED")
        self.assertTrue(any(c.name == "Room Capacity" and c.status == "FAIL" for c in ev_b.checks))

        # Sufficient capacity in lab B for 50 students
        ev_b_50 = evaluate(sess_50, lab_b, [])
        self.assertTrue(all(c.status == "PASS" for c in ev_b_50.checks if c.category == "capacity"))

    def test_software_present_missing_and_version(self):
        labs, bookings = self.repo.load()
        lab_b = next(lab for lab in labs if lab.id == "lab-b")  # Python 3.12
        lab_c = next(lab for lab in labs if lab.id == "lab-c")  # Python 3.10

        # Exact match
        sess = self.make_session(software=[{"name": "Python", "version": "3.12"}])
        ev_b = evaluate(sess, lab_b, [])
        self.assertTrue(any(c.category == "software" and c.status == "PASS" for c in ev_b.checks))

        # Version mismatch
        ev_c = evaluate(sess, lab_c, [])
        self.assertEqual(ev_c.status, "BLOCKED")
        sw_check = next(c for c in ev_c.checks if c.category == "software")
        self.assertEqual(sw_check.status, "FAIL")
        self.assertIn("3.10", sw_check.evidence)

        # Software completely missing
        sess_missing = self.make_session(software=[{"name": "Haskell", "version": "9.4"}])
        ev_b_missing = evaluate(sess_missing, lab_b, [])
        self.assertEqual(ev_b_missing.status, "BLOCKED")
        sw_miss = next(c for c in ev_b_missing.checks if c.category == "software")
        self.assertEqual(sw_miss.status, "FAIL")
        self.assertIn("none", sw_miss.evidence)

    def test_equipment_present_and_missing(self):
        labs, _ = self.repo.load()
        lab_b = next(lab for lab in labs if lab.id == "lab-b")

        # Present equipment
        sess = self.make_session(equipment=["projector"])
        ev = evaluate(sess, lab_b, [])
        self.assertTrue(any(c.category == "equipment" and c.status == "PASS" for c in ev.checks))

        # Missing equipment
        sess_missing = self.make_session(equipment=["3d_printer"])
        ev_missing = evaluate(sess_missing, lab_b, [])
        self.assertEqual(ev_missing.status, "BLOCKED")
        self.assertTrue(any(c.category == "equipment" and c.status == "FAIL" for c in ev_missing.checks))

    def test_unverified_inventory_labels_unverified(self):
        labs, bookings = self.repo.load()
        lab_e = next(lab for lab in labs if lab.id == "lab-e")  # unverified ROS 2.0, cap 30

        # Practical requiring 20 students, ROS 2.0 (in unverified_software)
        sess = self.make_session(
            students=20,
            software=[{"name": "ROS", "version": "2.0"}],
            equipment=["projector"],
            preferred_lab="lab-e"
        )
        ev = evaluate(sess, lab_e, [])
        self.assertEqual(ev.status, "UNVERIFIED")
        self.assertTrue(any(c.category == "software" and c.status == "UNKNOWN" for c in ev.checks))

        # Readiness engine must label overall session UNVERIFIED when an unknown exists without hard fails
        readiness = check_session_readiness(sess, self.repo)
        self.assertEqual(readiness.status, "UNVERIFIED")

    def test_mandatory_failure_prevents_ready_status(self):
        labs, _ = self.repo.load()
        lab_e = next(lab for lab in labs if lab.id == "lab-e")  # cap 30, unverified ROS

        # If student count exceeds capacity (40 > 30), it must be BLOCKED, not UNVERIFIED or READY
        sess = self.make_session(
            students=40,
            software=[{"name": "ROS", "version": "2.0"}],
            preferred_lab="lab-e"
        )
        ev = evaluate(sess, lab_e, [])
        self.assertEqual(ev.status, "BLOCKED")
        self.assertTrue(any(c.status == "FAIL" for c in ev.checks))

    def test_exact_booking_boundaries_and_overlaps(self):
        # Booking in lab-b on 2026-10-27 is 10:00 to 12:00
        labs, bookings = self.repo.load()
        lab_b = next(lab for lab in labs if lab.id == "lab-b")

        # Adjacent before: 09:00 to 10:00 -> NO conflict (PASS)
        ev_before = evaluate(self.make_session(start="09:00", end="10:00", students=50), lab_b, bookings)
        self.assertEqual(ev_before.status, "READY")

        # Adjacent after: 12:00 to 14:00 -> NO conflict (PASS)
        ev_after = evaluate(self.make_session(start="12:00", end="14:00", students=50), lab_b, bookings)
        self.assertEqual(ev_after.status, "READY")

        # Overlapping start: 09:30 to 10:30 -> CONFLICT (BLOCKED)
        ev_overlap1 = evaluate(self.make_session(start="09:30", end="10:30", students=50), lab_b, bookings)
        self.assertEqual(ev_overlap1.status, "BLOCKED")
        self.assertIn("booking-b-20261027-01", ev_overlap1.conflicting_booking_ids)

        # Overlapping end: 11:30 to 12:30 -> CONFLICT (BLOCKED)
        ev_overlap2 = evaluate(self.make_session(start="11:30", end="12:30", students=50), lab_b, bookings)
        self.assertEqual(ev_overlap2.status, "BLOCKED")

        # Engulfing: 09:00 to 13:00 -> CONFLICT (BLOCKED)
        ev_engulf = evaluate(self.make_session(start="09:00", end="13:00", students=50), lab_b, bookings)
        self.assertEqual(ev_engulf.status, "BLOCKED")

    def test_student_batch_splitting(self):
        # 70 students exceeds the largest room (Lab B cap 65)
        # Without splitting, no single room can accommodate 70 students
        sess_no_split = self.make_session(
            students=70,
            allow_batch_split=False,
            software=[{"name": "Python", "version": "3.12"}]
        )
        res_no_split = find_alternatives(sess_no_split, repository=self.repo)
        self.assertEqual(res_no_split.alternatives, [])

        # With splitting permitted (max 2 batches), each batch is 35 students
        # Lab D has capacity 35, working computers 35, Python 3.12
        sess_split = self.make_session(
            students=70,
            allow_batch_split=True,
            max_batches=2,
            software=[{"name": "Python", "version": "3.12"}]
        )
        res_split = find_alternatives(sess_split, repository=self.repo)
        self.assertTrue(len(res_split.alternatives) > 0)
        cand = res_split.alternatives[0]
        self.assertTrue(cand.is_split)
        self.assertEqual(len(cand.batches), 2)
        self.assertEqual(cand.batches[0].students, 35)
        self.assertEqual(cand.batches[1].students, 35)
        self.assertEqual(cand.verification_status, "READY")
        # Ensure batch 2 does not overlap batch 1
        b1, b2 = cand.batches[0], cand.batches[1]
        self.assertTrue(b1.end <= b2.start or b2.end <= b1.start)

    def test_infeasible_scheduling_and_rejection_audit(self):
        # Impossible practical: 180 students (exceeds all rooms even with 2 batches)
        sess = self.make_session(students=180, allow_batch_split=False)
        res = find_alternatives(sess, repository=self.repo)
        self.assertEqual(res.alternatives, [])
        self.assertEqual(res.message, "No feasible alternative found.")
        self.assertTrue(len(res.rejected) > 0)
        # Check that rejection explanations cite capacity
        self.assertTrue(any("Room capacity" in r or "working computers" in r for rej in res.rejected for r in rej.reasons))

    def test_revalidation_of_alternatives(self):
        sess = self.make_session(students=60)
        res = find_alternatives(sess, repository=self.repo)
        cand = res.alternatives[0]  # Lab B at 12:00
        self.assertEqual(cand.verification_status, "READY")

        # Simulate newly added booking in lab-b at 12:00
        data = json.loads((self.path / "bookings.json").read_text())
        data["bookings"].append({
            "id": "external-emergency-booking",
            "lab_id": "lab-b",
            "date": "2026-10-27",
            "start": "12:00",
            "end": "14:00"
        })
        (self.path / "bookings.json").write_text(json.dumps(data))

        # Re-verification must deterministically flag the conflict
        reverified = verify_candidate(cand, self.repo)
        self.assertEqual(reverified.verification_status, "BLOCKED")
        self.assertEqual(reverified.evidence.status, "BLOCKED")

    def test_deterministic_workflow_without_ai(self):
        # Conversation submit_session must work without contacting Ollama
        conv = Conversation()
        sess = self.make_session(
            practical_name="Autonomous Systems",
            students=50,
            start="13:00",
            end="15:00"
        )
        success = conv.submit_session(sess, "test-deterministic-token")
        self.assertTrue(success)
        self.assertIsNotNone(conv.latest)
        self.assertEqual(conv.latest.outcome, "ready")
        self.assertTrue(any(r.status == "READY" for r in conv.latest.readiness.labs))

    def test_invalid_input_handling(self):
        # Missing required fields
        with self.assertRaises(ValidationError):
            Session.model_validate({"students": 50, "date": "2026-10-27"})
        # Invalid date
        with self.assertRaises(ValidationError):
            self.make_session(date="2026-02-31")
        # Invalid time sequence (end before start)
        with self.assertRaises(ValidationError):
            self.make_session(start="14:00", end="12:00")
        # Allowed window end before start
        with self.assertRaises(ValidationError):
            self.make_session(allowed_window_start="17:00", allowed_window_end="09:00")
        # Zero or negative students
        with self.assertRaises(ValidationError):
            self.make_session(students=0)
        with self.assertRaises(ValidationError):
            self.make_session(students=-5)

    def test_three_required_demo_scenarios(self):
        # Scenario A: Practical Ready
        # 50 students, Python 3.12, 2026-10-27 from 13:00 to 15:00
        sess_a = self.make_session(
            practical_name="Data Structures Practical",
            date="2026-10-27",
            start="13:00",
            end="15:00",
            students=50,
            software=[{"name": "Python", "version": "3.12"}],
            equipment=["projector", "whiteboard"],
            preferred_lab=None,
        )
        readiness_a = check_session_readiness(sess_a, self.repo)
        self.assertEqual(readiness_a.status, "READY")
        ready_lab = next(lab for lab in readiness_a.labs if lab.status == "READY")
        self.assertEqual(ready_lab.lab_id, "lab-b")
        # Verify evidence is present for each mandatory check
        self.assertTrue(any(c.name == "Room Capacity" and c.status == "PASS" for c in ready_lab.checks))
        self.assertTrue(any(c.name == "Working Computers" and c.status == "PASS" for c in ready_lab.checks))
        self.assertTrue(any(c.category == "software" and c.status == "PASS" for c in ready_lab.checks))
        self.assertTrue(any(c.name == "Schedule Availability" and c.status == "PASS" for c in ready_lab.checks))

        # Scenario B: Practical Blocked with a Verified Alternative
        # 60 students, Python 3.12, 2026-10-27 from 10:00 to 12:00 (booking conflict in lab-b)
        sess_b = self.make_session(
            practical_name="Data Science Practical",
            date="2026-10-27",
            start="10:00",
            end="12:00",
            students=60,
            software=[{"name": "Python", "version": "3.12"}],
            equipment=["projector", "whiteboard"],
            preferred_lab=None,
        )
        readiness_b = check_session_readiness(sess_b, self.repo)
        self.assertEqual(readiness_b.status, "BLOCKED")
        alts_b = find_alternatives(sess_b, repository=self.repo)
        self.assertTrue(len(alts_b.alternatives) > 0)
        top_alt = alts_b.alternatives[0]
        self.assertEqual(top_alt.verification_status, "READY")
        self.assertEqual(top_alt.session.start, "12:00")
        self.assertEqual(top_alt.session.preferred_lab, "lab-b")

        # Scenario C: No Feasible Alternative
        # 70 students, unverified ROS 2.0
        sess_c = self.make_session(
            practical_name="Robotics Practical",
            date="2026-10-27",
            start="10:00",
            end="12:00",
            students=70,
            software=[{"name": "ROS", "version": "2.0"}],
            equipment=["robotic_arm"],
            preferred_lab=None,
        )
        readiness_c = check_session_readiness(sess_c, self.repo)
        self.assertEqual(readiness_c.status, "BLOCKED")
        alts_c = find_alternatives(sess_c, repository=self.repo)
        self.assertEqual(alts_c.alternatives, [])
        self.assertEqual(alts_c.message, "No feasible alternative found.")
        self.assertTrue(len(alts_c.rejected) > 0)


if __name__ == "__main__":
    unittest.main()
