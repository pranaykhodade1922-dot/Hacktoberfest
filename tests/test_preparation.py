"""Preparation tests use temporary roots and a simulated subprocess boundary.

No practical packages are installed in these tests, or in the app/global Python.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from preparation import (ApprovalError, BASE_PROBE, PINS, PROBE, PreparationController,
                         PreparationService, Requirements, machine_lock)
from process_runner import run_bounded

ROOT = Path(__file__).resolve().parents[1]


class FakeComputer:
    def __init__(self, root):
        self.target = Path(root) / ".labready/practicals/python-data"
        self.calls = []
        self.packages = {}
        self.creator = "3.12"
        self.version = "3.12"
        self.behavior = "success"
        self.calculation = True

    def create(self):
        (self.target / "Scripts").mkdir(parents=True, exist_ok=True)
        (self.target / "Scripts/python.exe").write_bytes(b"fake dedicated interpreter")
        (self.target / "pyvenv.cfg").write_text("include-system-site-packages = false\n")

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[-1] == BASE_PROBE:
            return subprocess.CompletedProcess(argv, 0, json.dumps({"version": self.creator + ".10", "minor": self.creator}), "")
        if "venv" in argv:
            self.create()
            return subprocess.CompletedProcess(argv, 0, "Created dedicated environment", "")
        if "--dry-run" in argv:
            report = {
                "install": [
                    {
                        "metadata": {"name": name, "version": pin},
                        "download_info": {
                            "url": f"https://files.pythonhosted.org/packages/{name}-{pin}-cp312-cp312-win_amd64.whl",
                            "archive_info": {"hashes": {"sha256": "0" * 64}}
                        }
                    }
                    for name, pin in PINS.items()
                ]
            }
            return subprocess.CompletedProcess(argv, 0, json.dumps(report), "")
        if "install" in argv:
            if self.behavior == "timeout":
                raise subprocess.TimeoutExpired(argv, 240, output="Downloading package", stderr="network timed out")
            if self.behavior == "failure":
                return subprocess.CompletedProcess(argv, 1, "", "No internet connection")
            self.packages = dict(PINS)
            return subprocess.CompletedProcess(argv, 0, "Successfully installed allowlisted packages", "")
        if argv[-1] == PROBE:
            packages = {name: {"version": version, "module_version": version,
                               "path": str(self.target / "Lib/site-packages" / name / "__init__.py")}
                        for name, version in self.packages.items()}
            data = {"version": self.version + ".10", "minor": self.version,
                    "prefix": str(self.target), "base_prefix": str(self.target.parent / "base-python"),
                    "pip": True, "packages": packages,
                    "calculation": {"passed": self.calculation and len(packages) == 2,
                                    "numpy_sum": 6 if self.calculation else 7, "pandas_sum": 60}}
            return subprocess.CompletedProcess(argv, 0, "LABREADY_PROBE=" + json.dumps(data), "")
        raise AssertionError("Unexpected command")


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="labready-prep-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.computer = FakeComputer(self.root)
        self.app_python = self.root / "venv/Scripts/python.exe"
        self.app_python.parent.mkdir(parents=True)
        self.app_python.write_bytes(b"app environment must not change")
        self.global_python = self.root / "global-python.exe"
        self.global_python.write_bytes(b"global Python must not change")
        self.service = PreparationService(self.root, runner=self.computer, app_python=self.app_python)
        self.requirements = Requirements()

    def owned_environment(self):
        self.computer.create()
        (self.computer.target / ".labready-owner.json").write_text(json.dumps(self.service.owner()))

    def prepare(self):
        plan = self.service.propose(self.requirements)
        approval = self.service.approve(plan)
        return self.service.execute(plan, approval)

    def test_missing_environment_is_not_prepared_and_plan_creates_it(self):
        plan = self.service.propose(self.requirements)
        self.assertEqual(plan.inspection.status, "NOT PREPARED")
        self.assertTrue(plan.inspection.environment_missing)
        self.assertIn("venv", plan.commands[0])
        self.assertFalse(self.service.target.exists())
        self.assertFalse(plan.inspection.fallback_allowed)

    def test_missing_packages_are_inspected_in_dedicated_environment(self):
        self.owned_environment()
        inspection = self.service.inspect(self.requirements)
        self.assertEqual(inspection.status, "NOT PREPARED")
        self.assertEqual(inspection.missing_packages, ["numpy", "pandas"])
        self.assertEqual(self.computer.calls[-1][0][0], str(self.service.python))

    def test_execution_requires_staff_approval(self):
        plan = self.service.propose(self.requirements)
        with self.assertRaises(ApprovalError):
            self.service.execute(plan, "invented")
        self.assertFalse(self.service.target.exists())

    def test_altered_plan_and_requirements_invalidate_approval(self):
        plan = self.service.propose(self.requirements)
        approval = self.service.approve(plan)
        changed = plan.model_copy(deep=True)
        changed.commands[0][-1] = str(self.root / "venv")
        with self.assertRaises(ApprovalError):
            self.service.execute(changed, approval)
        controller = PreparationController(self.service)
        controller.plan = plan
        with self.assertRaises(ApprovalError):
            controller.prepare(Requirements(python_version="3.11"), plan.id)
        self.assertIsNone(controller.plan)
        self.assertFalse(self.service.target.exists())

    def test_unapproved_packages_and_parameters_rejected(self):
        for fields in ({"packages": ("requests",)}, {"packages": ("numpy",)}, {"command": "anything"}, {"target": "C:/other"}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                Requirements(**fields)

    def test_required_python_unavailable_is_manual_not_package_fix(self):
        plan = self.service.propose(Requirements(python_version="3.11"))
        self.assertEqual(plan.inspection.status, "MANUAL ATTENTION REQUIRED")
        self.assertFalse(plan.commands)
        self.assertTrue(plan.inspection.fallback_allowed)
        self.computer.creator = "3.10"
        self.assertEqual(self.service.inspect(self.requirements).status, "MANUAL ATTENTION REQUIRED")

    def test_success_requires_independent_verification(self):
        result = self.prepare()
        self.assertEqual(result.status, "READY")
        self.assertEqual(result.inspection.details["calculation"]["numpy_sum"], 6)
        self.assertEqual(result.inspection.details["packages"]["pandas"]["version"], PINS["pandas"])
        kinds = [event["event"] for event in result.events]
        self.assertLess(kinds.index("command_finished"), kinds.index("verification_started"))
        self.assertFalse(result.fallback_allowed)

    def test_installation_failure_and_timeout_are_not_retried(self):
        for behavior in ("failure", "timeout"):
            with self.subTest(behavior=behavior):
                # A fresh isolated fixture for each failure; no real environment altered.
                with tempfile.TemporaryDirectory(prefix="labready-prep-failure-") as folder:
                    computer = FakeComputer(folder)
                    computer.behavior = behavior
                    service = PreparationService(folder, runner=computer, app_python=self.app_python)
                    plan = service.propose(self.requirements)
                    approval = service.approve(plan)
                    result = service.execute(plan, approval)
                    self.assertEqual(result.status, "PREPARATION FAILED")
                    self.assertTrue(result.fallback_allowed)
                    service.execute(plan, approval)
                    self.assertEqual(sum("install" in args and "--dry-run" not in args for args, _ in computer.calls), 1)
                    if behavior == "timeout":
                        self.assertTrue(any(e["event"] == "command_timed_out" for e in result.events))

    def test_verification_failure_after_installation_is_not_ready(self):
        self.computer.calculation = False
        result = self.prepare()
        self.assertEqual(result.status, "PREPARATION FAILED")
        self.assertIn("independent verification", result.evidence[0])

    def test_repeated_execution_and_double_click_are_idempotent(self):
        controller = PreparationController(self.service)
        plan = controller.inspect(self.requirements)
        first = controller.prepare(self.requirements, plan.id)
        calls = len(self.computer.calls)
        second = controller.prepare(self.requirements, plan.id)
        self.assertEqual(first.status, second.status)
        self.assertEqual(len(self.computer.calls), calls)
        controller.inspect(self.requirements)
        self.assertIsNone(controller.result)
        self.assertEqual(controller.plan.inspection.status, "READY")
        self.assertFalse(controller.plan.commands)

    def test_filesystem_change_invalidates_approved_plan_before_mutations(self):
        plan = self.service.propose(self.requirements)
        approval = self.service.approve(plan)
        self.owned_environment()
        result = self.service.execute(plan, approval)
        self.assertEqual(result.status, "MANUAL ATTENTION REQUIRED")
        self.assertFalse(any("install" in argv and "--dry-run" not in argv for argv, _ in self.computer.calls))
        self.assertFalse(result.fallback_allowed)

    def test_other_sessions_cannot_execute_through_the_same_lock(self):
        plan = self.service.propose(self.requirements)
        approval = self.service.approve(plan)
        with machine_lock(self.root / ".labready/runtime/python-data.lock"):
            result = self.service.execute(plan, approval)
        self.assertNotEqual(result.status, "READY")
        self.assertFalse(any("install" in argv and "--dry-run" not in argv for argv, _ in self.computer.calls))

    def test_no_global_or_app_environment_mutations_or_shell_commands(self):
        before_app, before_global = self.app_python.read_bytes(), self.global_python.read_bytes()
        self.prepare()
        self.assertEqual(self.app_python.read_bytes(), before_app)
        self.assertEqual(self.global_python.read_bytes(), before_global)
        for argv, kwargs in self.computer.calls:
            self.assertIs(kwargs["shell"], False)
            self.assertGreater(kwargs["timeout"], 0)
            self.assertTrue(Path(argv[0]).is_absolute())
            self.assertEqual(kwargs["env"]["PIP_CONFIG_FILE"], os.devnull)
            if "install" in argv and "--dry-run" not in argv:
                self.assertEqual(argv[0], str(self.service.python))
                self.assertIn("--require-virtualenv", argv)
                self.assertIn("--retries", argv)
                self.assertNotIn("--user", argv)

    def test_existing_unowned_environment_requires_manual_attention(self):
        self.computer.create()
        plan = self.service.propose(self.requirements)
        self.assertEqual(plan.inspection.status, "MANUAL ATTENTION REQUIRED")
        self.assertFalse(plan.commands)

    def test_existing_environment_cannot_include_global_site_packages(self):
        self.owned_environment()
        (self.computer.target / "pyvenv.cfg").write_text("# include-system-site-packages = false\ninclude-system-site-packages = true\n")
        self.assertEqual(self.service.inspect(self.requirements).status, "MANUAL ATTENTION REQUIRED")

    def test_ui_plan_precedes_approval_and_requirement_change_clears_result(self):
        controller = PreparationController(self.service)
        app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=15)
        app.session_state["preparation"] = controller
        app.run()
        next(b for b in app.button if b.label == "Inspect and propose preparation").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any(b.label == "Approve and prepare" for b in app.button))
        self.assertFalse(self.service.target.exists())
        next(b for b in app.button if b.label == "Approve and prepare").click().run()
        self.assertEqual(controller.result.status, "READY")
        app.text_input(key="local_python_version").input("3.11").run()
        self.assertIsNone(controller.plan)
        self.assertIsNone(controller.result)
        self.assertFalse(any(b.label == "Approve and prepare" for b in app.button))


class ProcessBoundaryTests(unittest.TestCase):
    def test_actual_read_only_command_and_timeout_capture(self):
        import sys
        with tempfile.TemporaryDirectory(prefix="labready-process-test-") as folder:
            kwargs = dict(shell=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=folder, env=dict(os.environ), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            completed = run_bounded([sys.executable, "-I", "-B", "-c", "print('bounded read-only probe')"], timeout=10, **kwargs)
            self.assertEqual(completed.returncode, 0)
            self.assertIn("bounded read-only probe", completed.stdout)
            with self.assertRaises(subprocess.TimeoutExpired):
                run_bounded([sys.executable, "-I", "-B", "-c", "import time; time.sleep(20)"], timeout=.4, **kwargs)


if __name__ == "__main__":
    unittest.main()
