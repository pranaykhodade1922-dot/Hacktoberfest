"""Check the workshop's existing Python environment and local Ollama model."""

import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from config import HOST, get_model

ROOT = Path(__file__).resolve().parent


def main():
    print(f"Python {sys.version.split()[0]}: {sys.executable}")
    if Path(sys.prefix).resolve() != (ROOT / "venv").resolve() or sys.prefix == sys.base_prefix:
        print(r"ERROR: Use the workshop environment: .\venv\Scripts\python.exe .\check_setup.py")
        return 1
    if sys.version_info < (3, 12):
        print("ERROR: This workshop requires Python 3.12 or later.")
        return 1
    print("OK: Using the workshop virtual environment.")

    try:
        package_version = version("ollama")
        import ollama
    except (PackageNotFoundError, ImportError) as exc:
        print(f"ERROR: Cannot load the ollama package: {exc}")
        print(r"Install dependencies: .\venv\Scripts\python.exe -m pip install -r .\requirements.txt")
        return 1
    print(f"OK: ollama {package_version} is installed.")

    try:
        model = get_model()
        client = ollama.Client(host=HOST, timeout=120.0)
        available = client.list()
        print(f"OK: Connected to {HOST}.")
        names = [model.model for model in available.models]
        if model not in names:
            print(f"ERROR: {model} is unavailable. Available models: {', '.join(names) or '(none)'}")
            print("Run 'ollama list' and verify you are using the intended local Ollama server.")
            print(f"To install the selected model explicitly: ollama pull {model}")
            return 1
        print(f"OK: {model} is available.")
        capabilities = client.show(model).capabilities or []
        print(f"Model capabilities: {', '.join(capabilities) or '(not advertised)'}")
        print("LabReady uses validated structured-JSON actions; native tool calling is not required.")
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": 'Reply as JSON: {"status":"Workshop ready"}'}],
            format={"type": "object", "properties": {"status": {"type": "string", "enum": ["Workshop ready"]}},
                    "required": ["status"], "additionalProperties": False},
            options={"temperature": 0, "num_predict": 32},
            stream=False,
        )
        reply = (response.message.content or "").strip()
        if not reply:
            print("ERROR: The model returned an empty response. Retry the check and inspect the Ollama logs if it persists.")
            return 1
        import json
        if json.loads(reply) != {"status": "Workshop ready"}:
            print(f"ERROR: Model returned an invalid structured response: {reply}")
            return 1
        print(f"OK: Model returned validated JSON: {reply}")
    except Exception as exc:
        print(f"ERROR: Ollama check failed ({type(exc).__name__}): {exc}")
        print(f"Ensure the Ollama app is running at {HOST}, then run 'ollama list'.")
        print("Check OLLAMA_MODEL and try 'ollama run <selected-model>' to diagnose model errors, then rerun this check.")
        return 1

    print("SUCCESS: Workshop environment is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
