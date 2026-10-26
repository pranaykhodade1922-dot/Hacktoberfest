"""LabReady CLI. --demo runs domain logic without contacting Ollama."""
import argparse

from render import NOTICE, render
from schemas import Session
from tools import check_session_readiness, find_alternatives

DEMO_REQUEST = "Check a Python 3.12 practical for 60 students on 2026-10-27 from 10:00 to 12:00."


def demo_session():
    return Session(date="2026-10-27", start="10:00", end="12:00", students=60,
                   software=[{"name": "Python", "version": "3.12"}])


def main():
    parser = argparse.ArgumentParser(description="LabReady local workshop CLI")
    parser.add_argument("--demo", action="store_true", help="deterministic domain demo; no AI")
    parser.add_argument("--debug", action="store_true", help="show actual Ollama tool calls and results")
    parser.add_argument("--request", help="run one natural-language request through Ollama and exit")
    args = parser.parse_args()
    if args.demo and args.request:
        parser.error("--demo and --request are separate modes")
    print(NOTICE)
    print("Recommendations do not reserve a lab. All times: Asia/Kolkata.")
    try:
        if args.demo:
            print("DEMO: deterministic Python domain logic; no AI.\n" + DEMO_REQUEST)
            session = demo_session()
            print(render(check_session_readiness(session)))
            print(render(find_alternatives(session)))
            return 0
        from agent import Agent
        agent = Agent(debug=args.debug)
        print(f"AI mode: local Ollama {agent.model}, validated JSON actions; /exit to quit.")
        if args.request:
            print(agent.run(args.request))
            return 0 if agent.last_results else 1
        while True:
            try:
                text = input("\nLabReady> ").strip()
            except EOFError:
                break
            if text.casefold() == "/exit":
                break
            if text:
                print(agent.run(text))
        return 0
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except (ValueError, OSError, KeyError) as exc:
        print(f"ERROR: {exc}. Check the local data files and request values.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
