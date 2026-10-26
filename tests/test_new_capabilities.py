"""Unit tests for LabReady preparation interpreter, dependency resolution, and UI stages."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from ollama import ChatResponse, ResponseError
from streamlit.testing.v1 import AppTest

from dependency_resolution import Resolution, resolve
from preparation import PINS, PreparationController, PreparationService, Requirements
from preparation_agent import PreparationInterpreter
from schemas import Contract

ROOT = Path(__file__).resolve().parents[1]


def make_chat_response(content):
    return ChatResponse(message={"role": "assistant", "content": content})


class InterpreterTests(unittest.TestCase):
    def test_valid_interpretation_extracts_requirements(self):
        client = Mock()
        payload = json.dumps({"action": "inspect_and_plan", "requirements": {"python_version": "3.12", "packages": ["numpy", "pandas"]}})
        client.chat.return_value = make_chat_response(payload)
        interpreter = PreparationInterpreter(client=client)
        req = interpreter.interpret("Prepare this computer for Python 3.12 with NumPy and pandas.")
        self.assertIsNotNone(req)
        self.assertEqual(req.python_version, "3.12")
        self.assertEqual(req.packages, ("numpy", "pandas"))
        self.assertIsNone(interpreter.question)
        self.assertEqual(len(interpreter.last_errors), 0)

    def test_clarification_asked_when_user_omits_information(self):
        client = Mock()
        payload = json.dumps({"action": "clarify", "question": "What Python version is needed?"})
        client.chat.return_value = make_chat_response(payload)
        interpreter = PreparationInterpreter(client=client)
        req = interpreter.interpret("Prepare this computer with NumPy and pandas.")
        self.assertIsNone(req)
        self.assertIn("Python version", interpreter.question)

    def test_model_guesses_rejected_if_not_in_user_text(self):
        client = Mock()
        # Model returns python 3.12 even though user only wrote python with pandas
        payload = json.dumps({"action": "inspect_and_plan", "requirements": {"python_version": "3.12", "packages": ["numpy", "pandas"]}})
        client.chat.return_value = make_chat_response(payload)
        interpreter = PreparationInterpreter(client=client)
        req = interpreter.interpret("Prepare python with pandas.")
        # Rejection triggers retry or clarification
        self.assertIsNone(req)
        self.assertIsNotNone(interpreter.question)

    def test_actionable_error_when_ollama_offline(self):
        client = Mock()
        client.chat.side_effect = ConnectionError("Could not connect to Ollama")
        interpreter = PreparationInterpreter(client=client)
        req = interpreter.interpret("Prepare this computer for Python 3.12 with NumPy and pandas.")
        self.assertIsNone(req)
        self.assertTrue(any("Start Ollama" in err for err in interpreter.last_errors))


class DependencyResolutionTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock()
        self.service.app_python = Path(tempfile.gettempdir()) / "python.exe"

    def test_valid_resolution_report(self):
        report = {
            "install": [
                {
                    "metadata": {"name": "numpy", "version": "2.2.6"},
                    "download_info": {
                        "url": "https://files.pythonhosted.org/packages/numpy-2.2.6-cp312-cp312-win_amd64.whl",
                        "archive_info": {"hashes": {"sha256": "a" * 64}}
                    }
                },
                {
                    "metadata": {"name": "pandas", "version": "2.2.3"},
                    "download_info": {
                        "url": "https://files.pythonhosted.org/packages/pandas-2.2.3-cp312-cp312-win_amd64.whl",
                        "archive_info": {"hashes": {"sha256": "b" * 64}}
                    }
                }
            ]
        }
        self.service.run.return_value = subprocess.CompletedProcess([], 0, json.dumps(report), "")
        res = resolve(self.service)
        self.assertEqual(res.packages["numpy"], "2.2.6")
        self.assertEqual(res.packages["pandas"], "2.2.3")
        self.assertEqual(len(res.artifacts), 2)

    def test_unapproved_distribution_rejected(self):
        report = {
            "install": [
                {
                    "metadata": {"name": "malicious-pkg", "version": "1.0.0"},
                    "download_info": {
                        "url": "https://files.pythonhosted.org/packages/malicious.whl",
                        "archive_info": {"hashes": {"sha256": "a" * 64}}
                    }
                }
            ]
        }
        self.service.run.return_value = subprocess.CompletedProcess([], 0, json.dumps(report), "")
        with self.assertRaises(ValueError) as ctx:
            resolve(self.service)
        self.assertIn("unapproved or duplicate distribution", str(ctx.exception))

    def test_unapproved_source_or_missing_hash_rejected(self):
        report = {
            "install": [
                {
                    "metadata": {"name": "numpy", "version": "2.2.6"},
                    "download_info": {
                        "url": "http://insecure-site.org/numpy.whl",
                        "archive_info": {"hashes": {"sha256": "a" * 64}}
                    }
                }
            ]
        }
        self.service.run.return_value = subprocess.CompletedProcess([], 0, json.dumps(report), "")
        with self.assertRaises(ValueError) as ctx:
            resolve(self.service)
        self.assertIn("unapproved artifact source", str(ctx.exception))


class LiveInspectionDisplayTests(unittest.TestCase):
    def test_inspection_fields_and_blockers_in_ui(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def runner(argv, **kwargs):
                return subprocess.CompletedProcess(argv, 0, json.dumps({"version": "3.12.10", "minor": "3.12"}), "")
            service = PreparationService(root, runner=runner, app_python=Path(folder) / "python.exe",
                                         resolver=lambda s: Resolution(packages=dict(PINS), artifacts=[]))
            controller = PreparationController(service)
            app = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=15)
            app.session_state["preparation"] = controller
            app.run()
            # Click inspect
            next(b for b in app.button if b.label == "Inspect and propose preparation").click().run()
            self.assertFalse(app.exception)
            # Verify headline and stepper
            self.assertTrue(any("Prepare your lab. Verify it works." in m.value for m in app.markdown))
            self.assertTrue(any("This computer — live inspection." in m.value for m in app.markdown))
            self.assertTrue(any("Dedicated practical environment does not exist" in m.value for m in app.markdown))


if __name__ == "__main__":
    unittest.main()
