"""Gemma interprets requirements; Python alone plans and executes preparation."""
import json
import re
from typing import Annotated, Literal

from pydantic import Field, RootModel, ValidationError, field_validator

from agent import Agent, inline_schema
from preparation import Requirements
from schemas import Contract

EXAMPLE = "Prepare this computer for Python 3.12 with NumPy and pandas."


class ParsedRequirements(Contract):
    python_version: str = Field(pattern=r"^3\.\d+$")
    packages: list[Literal["numpy", "pandas"]] = Field(min_length=2, max_length=2)

    @field_validator("packages")
    @classmethod
    def both_packages(cls, value):
        if set(value) != {"numpy", "pandas"}:
            raise ValueError("This workflow requires numpy and pandas, without duplicates")
        return value


class InspectAction(Contract):
    action: Literal["inspect_and_plan"]
    requirements: ParsedRequirements


class ClarifyAction(Contract):
    action: Literal["clarify"]
    question: str = Field(min_length=1)


class PreparationAction(RootModel[Annotated[InspectAction | ClarifyAction, Field(discriminator="action")]]):
    pass


SCHEMA = inline_schema(PreparationAction)
INSTRUCTIONS = """Interpret a request to prepare THIS computer. Return exactly one JSON action.
Allowed: {"action":"inspect_and_plan","requirements":{"python_version":"MAJOR.MINOR","packages":["numpy","pandas"]}}
or {"action":"clarify","question":"Ask for missing information"}.
Require an explicitly supplied Python version and BOTH package names. NumPy is
case-insensitive. Reuse earlier user details for follow-ups; latest corrections
win. Never guess a Python version or omit additional requested software silently.
If information is missing or other software is requested, ask a clarification.
Only this Python data recipe is supported. Never propose commands, package
versions, paths, installation URLs, approval, execution, lab readiness or alternatives.
Python performs inspection and pip dependency resolution. Staff alone approves.
"""


class PreparationInterpreter(Agent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.history = [{"role": "system", "content": INSTRUCTIONS}]
        self.question = None

    def interpret(self, text):
        self.history.append({"role": "user", "content": text})
        self.last_trace = []
        self.last_errors = []
        self.question = None
        if not text.strip():
            self.question = "Describe the Python version and the packages your practical requires."
            return None
        for _ in range(2):
            try:
                self.trace("model_requested", model=self.model)
                messages = [*self.history, {"role": "system", "content": "User-provided requirements in order: " + json.dumps([m["content"] for m in self.history if m["role"] == "user"])}]
                response = self.client.chat(model=self.model, messages=messages, format=SCHEMA, stream=False,
                                            options={"temperature": 0, "num_predict": 400, "num_ctx": 8192})
                content = response.message.content or ""
                self.history.append({"role": "assistant", "content": content})
                self.trace("action_proposed", content=content)
                action = PreparationAction.model_validate_json(content, strict=True).root
                self.trace("action_validated", action=action.action)
                if isinstance(action, ClarifyAction):
                    self.question = action.question
                    return None
                user_text = "\n".join(m["content"] for m in self.history if m["role"] == "user").casefold()
                required = [action.requirements.python_version, "python", "numpy", "pandas"]
                missing = [value for value in required if not re.search(r"(?<![\w.])" + re.escape(value) + r"(?!\w|\.\d)", user_text)]
                if missing:
                    raise ValueError("Clarification required; user has not explicitly supplied: " + ", ".join(missing))
                requirements = Requirements(python_version=action.requirements.python_version, packages=("numpy", "pandas"))
                self.trace("requirements_validated", requirements=requirements.model_dump())
                return requirements
            except (ValidationError, ValueError) as exc:
                self.trace("action_rejected", error=str(exc))
                self.last_errors.append(str(exc))
                self.history.append({"role": "system", "content": "Validation failed: " + str(exc) + ". Return a valid action, or ask for missing information; never guess."})
            except Exception as exc:
                self.trace("model_failed", error=str(exc), error_type=type(exc).__name__)
                self.last_errors.append(f"Cannot use {self.model} at http://localhost:11434 ({type(exc).__name__}): {exc}. Start Ollama, confirm the selected model with 'ollama list', and run check_setup.py. No local changes occurred.")
                return None
        self.question = "Please state the required Python version and confirm NumPy and pandas. No preparation plan was accepted."
        return None
