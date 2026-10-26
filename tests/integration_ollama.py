"""Opt-in live integration check, separate from deterministic unit tests."""
import sys
from pathlib import Path
import ollama

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import Agent
from app import DEMO_REQUEST
from schemas import Alternatives, Readiness


def main():
    agent = Agent(debug=True)
    print(f"Live model: {agent.model}; protocol: validated structured JSON actions")
    try:
        capabilities = agent.client.show(agent.model).capabilities or []
        print(f"Advertised native tools: {'yes' if 'tools' in capabilities else 'no'}; capabilities: {capabilities}")
        if "tools" not in capabilities:
            try:
                agent.client.chat(model=agent.model, messages=[{"role": "user", "content": "Call probe."}],
                                  tools=[{"type": "function", "function": {"name": "probe", "description": "Harmless protocol probe; nothing is executed.",
                                          "parameters": {"type": "object", "properties": {}}}}],
                                  stream=False, options={"num_predict": 1})
            except ollama.ResponseError as exc:
                if exc.status_code != 400 or "does not support tools" not in str(exc):
                    raise
                print(f"CONFIRMED: Native tool request rejected: {exc}")
            else:
                print("NOTE: Server accepted native tool definitions despite missing advertised capability; JSON protocol remains in use.")
    except Exception as exc:
        print(f"FAIL: Cannot inspect selected model ({type(exc).__name__}): {exc}")
        return 1
    print(agent.run(DEMO_REQUEST))
    checks = [r for r in agent.last_results if isinstance(r, Readiness)]
    alternatives = [r for r in agent.last_results if isinstance(r, Alternatives)]
    if agent.last_errors or not checks or checks[0].status != "BLOCKED" or not alternatives or not alternatives[0].alternatives:
        print("FAIL: Live model did not complete error-free readiness and alternative execution.")
        return 1
    print(f"PASS: {agent.model} proposed a validated JSON readiness action; Python completed readiness and alternative search.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
