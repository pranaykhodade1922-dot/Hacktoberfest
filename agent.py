"""Bounded structured-JSON action loop; all execution is validated Python."""
import json
import re
from pathlib import Path
from typing import Annotated, Literal

import ollama
from pydantic import Field, RootModel, ValidationError

from render import render
from config import HOST, get_model
from schemas import Alternatives, Contract, Readiness, Session
from tools import Repository, check_session_readiness, find_alternatives


class AlternativeArguments(Session):
    opening: str = "09:00"
    closing: str = "17:00"


ARGUMENTS = {"check_session_readiness": Session, "find_alternatives": AlternativeArguments}


class CheckAction(Contract):
    action: Literal["check_session_readiness"]
    arguments: Session


class AlternativeAction(Contract):
    action: Literal["find_alternatives"]
    arguments: AlternativeArguments


class ClarifyAction(Contract):
    action: Literal["clarify"]
    question: str = Field(min_length=1)


class DoneAction(Contract):
    action: Literal["done"]


class Action(RootModel[Annotated[CheckAction | AlternativeAction | ClarifyAction | DoneAction,
                                 Field(discriminator="action")]]):
    pass


def inline_schema(model):
    """Inline references for small local models that struggle with $defs."""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def expand(value):
        if isinstance(value, dict):
            if "$ref" in value:
                return expand(definitions[value["$ref"].split("/")[-1]])
            return {k: expand(v) for k, v in value.items() if k != "discriminator"}
        if isinstance(value, list):
            return [expand(v) for v in value]
        return value

    return expand(schema)


ACTION_SCHEMA = inline_schema(Action)


class Agent:
    def __init__(self, *, debug=False, client=None, repository=None, max_rounds=4, max_calls=8, model=None):
        self.model = model if model is not None else get_model()
        self.client = client if client is not None else ollama.Client(host=HOST, timeout=90.0)
        self.repository = repository or Repository()
        self.debug = debug
        self.max_rounds = max_rounds
        self.max_calls = max_calls
        self.history = [{"role": "system", "content": Path(__file__).with_name("SKILL.md").read_text(encoding="utf-8")}]
        self.history[0]["content"] += "\nRespond only with one JSON action matching the supplied response schema."
        self.last_results = []
        self.last_errors = []

        self.last_trace = []
        self.needs_clarification = False

    def trace(self, event, *, source="model", **details):
        """Record observable protocol activity only, never model reasoning."""
        self.last_trace.append({"event": event, "source": source, **details})

    def dispatch(self, name, arguments, *, require_grounding=False, source="model"):
        try:
            validated, session = self.validate_arguments(name, arguments, require_grounding)
        except (ValueError, TypeError) as exc:
            self.trace("arguments_rejected", source=source, tool=name, error=str(exc))
            raise
        self.trace("arguments_validated", source=source, tool=name, arguments=validated.model_dump())
        self.trace("tool_started", source=source, tool=name)
        try:
            if name == "check_session_readiness":
                result = check_session_readiness(session, self.repository)
            else:
                result = find_alternatives(session, validated.opening, validated.closing, self.repository)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.trace("tool_failed", source=source, tool=name, error=str(exc))
            raise
        self.trace("tool_succeeded", source=source, tool=name, result=result.model_dump())
        return result

    def validate_arguments(self, name, arguments, require_grounding):
        if name not in ARGUMENTS:
            raise ValueError(f"Unknown tool: {name}. Only readiness and alternative search are allowed.")
        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object")
        arguments = dict(arguments)
        validated = ARGUMENTS[name].model_validate(arguments)
        session = Session.model_validate({k: v for k, v in validated.model_dump().items() if k not in {"opening", "closing"}})
        if require_grounding:
            self.validate_grounding(session)
        return validated, session

    def validate_grounding(self, session):
        """Require literal user evidence for mandatory values, including follow-ups."""
        text = "\n".join(m["content"] for m in self.history if m["role"] == "user").casefold()
        values = [("date (YYYY-MM-DD)", session.date), ("start time (HH:MM)", session.start),
                  ("end time (HH:MM)", session.end), ("student count (digits)", str(session.students))]
        for software in session.software:
            values.extend([(f"software name {software.name}", software.name),
                           (f"exact {software.name} version", software.version)])
        missing = [label for label, value in values
                   if not re.search(r"(?<![\w.])" + re.escape(value.casefold()) + r"(?!\w|\.\d)", text)]
        if missing:
            raise ValueError("Clarification required: explicitly provide " + ", ".join(missing) + ". No values were assumed.")

    def run(self, text):
        self.history.append({"role": "system", "content": "New submission: earlier application results are historical snapshots. For a complete check or follow-up, execute fresh tools against current records. Reuse user-provided requirements, never earlier availability conclusions."})
        self.history.append({"role": "user", "content": text})
        self.last_results = []
        self.last_errors = []
        self.last_trace = []
        self.needs_clarification = False
        calls = 0
        for _ in range(self.max_rounds):
            try:
                self.trace("model_requested", model=self.model)
                user_context = [m["content"] for m in self.history if m["role"] == "user"]
                messages = [*self.history, {"role": "system", "content":
                    "Answer the latest user submission using these exact user messages, in order. Earlier user details remain requirements unless the user changes them. Never use defaults from examples. Keep software name and version separate. USER-PROVIDED CONTEXT: " + json.dumps(user_context)}]
                response = self.client.chat(model=self.model, messages=messages, format=ACTION_SCHEMA,
                                            stream=False, options={"temperature": 0, "num_predict": 1200, "num_ctx": 8192})
            except Exception as exc:
                self.trace("model_failed", model=self.model, error=str(exc), error_type=type(exc).__name__)
                if isinstance(exc, ollama.ResponseError) and exc.status_code == 404:
                    action = f"The selected model {self.model} is missing. Run 'ollama list' and, if needed, 'ollama pull {self.model}'."
                elif "timeout" in type(exc).__name__.casefold():
                    action = "The local model timed out. Retry after Ollama finishes loading; close other model workloads if needed."
                else:
                    action = f"Ensure the Ollama app is running at {HOST}, then run check_setup.py."
                self.last_errors.append(f"Ollama request failed ({type(exc).__name__}): {exc}. {action}")
                break
            content = response.message.content or ""
            self.history.append({"role": "assistant", "content": content})
            self.trace("action_proposed", content=content)
            if self.debug:
                print(f"DEBUG proposed JSON action: {content}")
            try:
                action = Action.model_validate_json(content, strict=True).root
            except ValidationError as exc:
                error = f"Action validation failed: {exc}"
                self.last_errors.append(error)
                self.trace("action_rejected", error=str(exc))
                self.history.append({"role": "system", "content": json.dumps({"error": error, "instruction": "Return a valid action. Ask for missing fields; never assume values."})})
                continue
            self.trace("action_validated", action=action.action)
            if isinstance(action, (DoneAction, ClarifyAction)):
                self.needs_clarification = isinstance(action, ClarifyAction) and not self.last_results
                # Model prose never becomes authoritative availability output.
                if calls < self.max_calls:
                    self.ensure_alternatives()
                break
            calls += 1
            if calls > self.max_calls:
                self.last_errors.append("Tool call limit reached; narrow your request and retry.")
                return self.output()
            name, arguments = action.action, action.arguments.model_dump()
            if self.debug:
                print(f"DEBUG validated call {name}: {json.dumps(arguments, ensure_ascii=False)}")
            try:
                result = self.dispatch(name, arguments, require_grounding=True)
                self.last_results.append(result)
                payload = result.model_dump_json()
            except (ValidationError, ValueError, OSError, KeyError, TypeError) as exc:
                payload = json.dumps({"error": str(exc), "instruction": "Ask for missing or invalid fields; do not assume values."})
                self.last_errors.append(f"Tool {name} failed: {exc}")
            if self.debug:
                print(f"DEBUG result {name}: {payload}")
            # Gemma templates support content messages, not role=tool messages.
            self.history.append({"role": "system", "content": f"Application result for {name}: {payload}"})
        else:
            self.last_errors.append("Agent round limit reached. Only completed tool results below are valid.")
        return self.output()

    def ensure_alternatives(self):
        """Complete a blocked check even when the model stops without searching."""
        checks = [r for r in self.last_results if isinstance(r, Readiness)]
        if not checks or checks[-1].status != "BLOCKED":
            return
        session = checks[-1].session
        if any(isinstance(r, Alternatives) and r.original == session for r in self.last_results):
            return
        name, arguments = "find_alternatives", session.model_dump()
        if self.debug:
            print(f"DEBUG application policy call {name}: {json.dumps(arguments)}")
        try:
            result = self.dispatch(name, arguments, require_grounding=True, source="application")
            self.last_results.append(result)
            payload = result.model_dump_json()
        except (ValueError, OSError, KeyError, TypeError) as exc:
            payload = json.dumps({"error": str(exc)})
            self.last_errors.append(f"Automatic alternative search failed: {exc}")
        self.history.append({"role": "system", "content": f"Application policy result for {name}: {payload}"})
        if self.debug:
            print(f"DEBUG application policy result {name}: {payload}")

    def output(self):
        parts = [render(result) for result in self.last_results]
        parts.extend(f"ERROR: {error}" for error in self.last_errors)
        if not self.last_results:
            parts.append("No readiness or alternative check succeeded. Please provide or confirm the date (YYYY-MM-DD), start and end times (HH:MM, Asia/Kolkata), student count, required software AND exact versions, and any equipment or preferred lab. What session should I check?")
        return "\n\n".join(parts)
