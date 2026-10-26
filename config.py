"""Local model configuration; never modifies global settings."""
import os

HOST = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:4b"


def get_model():
    model = os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL).strip()
    if not model:
        raise ValueError("OLLAMA_MODEL must not be blank")
    return model
