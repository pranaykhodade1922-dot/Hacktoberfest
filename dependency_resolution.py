"""Read-only pip resolution of a fixed, published Windows/Python 3.12 recipe."""
import json
import re
from urllib.parse import urlparse

from schemas import Contract

ROOT_PINS = {"numpy": "2.2.6", "pandas": "2.2.3"}
ALLOWED_DISTRIBUTIONS = frozenset({"numpy", "pandas", "python-dateutil", "pytz", "tzdata", "six"})


class Resolution(Contract):
    packages: dict[str, str]
    artifacts: list[dict]
    python_version: str = "3.12"
    platform: str = "win_amd64"


def resolve(service):
    command = [str(service.app_python), "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check",
               "install", "--dry-run", "--ignore-installed", "--report", "-", "--quiet", "--no-input",
               "--no-cache-dir", "--retries", "0", "--timeout", "20", "--index-url", "https://pypi.org/simple",
               "--only-binary=:all:", "--python-version", "3.12", "--platform", "win_amd64", "--implementation", "cp",
               "--abi", "cp312", *[f"{name}=={pin}" for name, pin in ROOT_PINS.items()]]
    completed = service.run(command, 120)
    if completed.returncode:
        raise ValueError("Dependency resolution failed; no packages were installed. Check internet/PyPI availability. " + completed.stderr[-2000:])
    report = json.loads(completed.stdout)
    packages, artifacts = {}, []
    for item in report.get("install", []):
        metadata, download = item["metadata"], item["download_info"]
        name = metadata["name"].lower().replace("_", "-")
        version = metadata["version"]
        url = urlparse(download["url"])
        digest = download.get("archive_info", {}).get("hashes", {}).get("sha256", "")
        if name not in ALLOWED_DISTRIBUTIONS or name in packages:
            raise ValueError("Resolver returned an unapproved or duplicate distribution: " + name)
        if not re.fullmatch(r"\d+(?:\.\d+)*(?:[a-zA-Z0-9.+-]*)", version):
            raise ValueError("Invalid resolved package version")
        if url.scheme != "https" or url.hostname != "files.pythonhosted.org" or not url.path.endswith(".whl") or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Resolver returned an unapproved artifact source or missing wheel hash")
        packages[name] = version
        artifacts.append({"name": name, "version": version, "url": download["url"], "sha256": digest})
    if any(packages.get(name) != pin for name, pin in ROOT_PINS.items()):
        raise ValueError("Resolver did not establish the complete fixed recipe")
    return Resolution(packages=dict(sorted(packages.items())), artifacts=sorted(artifacts, key=lambda x: x["name"]))
