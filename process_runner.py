"""Capture subprocess output and bound the whole spawned process tree."""
import os
from pathlib import Path
import signal
import subprocess


def run_bounded(argv, *, timeout, capture_output, text, encoding, errors, shell, **kwargs):
    if shell or not capture_output or not text:
        raise ValueError("Only captured, shell=False argument-array commands are supported")
    if os.name != "nt":
        kwargs["start_new_session"] = True
    with subprocess.Popen(argv, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding=encoding, errors=errors, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                # Only the PID we just spawned and its children, never a port owner.
                taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
                subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"], shell=False,
                               capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
            raise subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
