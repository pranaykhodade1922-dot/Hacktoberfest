"""Approval-gated preparation of ONE project-managed environment on this PC.

No model-selected packages, paths or commands. Inspection is read-only.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from typing import Literal
from uuid import uuid4

from pydantic import ConfigDict, Field, field_validator
from schemas import Contract
from process_runner import run_bounded
from dependency_resolution import ROOT_PINS, Resolution, resolve

ROOT = Path(__file__).resolve().parent
PINS = ROOT_PINS
Status = Literal["NOT PREPARED", "PREPARING", "READY", "PREPARATION FAILED", "MANUAL ATTENTION REQUIRED"]
BASE_PROBE = "import sys,json; print(json.dumps({'version':'.'.join(map(str,sys.version_info[:3])),'minor':'.'.join(map(str,sys.version_info[:2]))}))"
PROBE = r'''
import sys,json,importlib,importlib.util,importlib.metadata
r={'version':'.'.join(map(str,sys.version_info[:3])), 'minor':'.'.join(map(str,sys.version_info[:2])),
   'prefix':sys.prefix,'base_prefix':sys.base_prefix,'pip':importlib.util.find_spec('pip') is not None,'packages':{}}
modules={}
for name in ('numpy','pandas'):
    try:
        mod=importlib.import_module(name)
        modules[name]=mod
        r['packages'][name]={'version':importlib.metadata.version(name),'module_version':mod.__version__,'path':mod.__file__}
    except Exception as exc:
        r['packages'][name]={'error':type(exc).__name__+': '+str(exc)}
r['calculation']={'passed':False}
if len(modules)==2:
    try:
        a=int(modules['numpy'].array([1,2,3]).sum())
        b=int(modules['pandas'].DataFrame({'students':[20,20,20]})['students'].sum())
        r['calculation']={'numpy_sum':a,'pandas_sum':b,'expected_numpy_sum':6,'expected_pandas_sum':60,'passed':a==6 and b==60}
    except Exception as exc:
        r['calculation']={'passed':False,'error':str(exc)}
print('LABREADY_PROBE='+json.dumps(r))
'''


class Requirements(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    python_version: str = Field(default="3.12", pattern=r"^3\.\d+$")
    packages: tuple[Literal["numpy", "pandas"], ...] = ("numpy", "pandas")

    @field_validator("packages")
    @classmethod
    def recipe_only(cls, value):
        if value != ("numpy", "pandas"):
            raise ValueError("This recipe requires exactly numpy and pandas in that order")
        return value


class Inspection(Contract):
    status: Status
    target: str
    interpreter: str
    evidence: list[str]
    details: dict = Field(default_factory=dict)
    missing_packages: list[str] = Field(default_factory=list)
    environment_missing: bool = False
    fallback_allowed: bool = False


class Plan(Contract):
    id: str
    revision: str
    requirements: Requirements
    inspection: Inspection
    actions: list[str]
    commands: list[list[str]]
    resolution: Resolution | None = None


class Execution(Contract):
    status: Status
    plan_id: str
    evidence: list[str]
    inspection: Inspection | None = None
    events: list[dict] = Field(default_factory=list)
    fallback_allowed: bool = False


class ApprovalError(ValueError):
    pass


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@contextmanager
def machine_lock(path):
    """OS lock across browser sessions; the lock file is retained, never deleted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ApprovalError("Another preparation holds the computer lock. No actions were started; wait and inspect again.") from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ApprovalError("Another preparation holds the computer lock. No actions were started; wait and inspect again.") from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class PreparationService:
    def __init__(self, root=ROOT, *, runner=None, app_python=None, resolver=None):
        self.root = Path(root).resolve()
        self.target = self.root / ".labready" / "practicals" / "python-data"
        self.python = self.target / "Scripts" / "python.exe"
        self.app_python = Path(app_python or sys.executable).absolute()
        self.runner = runner or run_bounded
        self.resolver = resolver or resolve
        self._plan = None
        self._approvals = {}
        self._completed = {}
        self._guard = threading.Lock()

    def safe_target(self):
        relative = self.target.resolve().relative_to(self.root)
        if relative != Path(".labready/practicals/python-data"):
            raise ValueError("Managed target resolves outside the fixed practical environment")
        for item in (self.root / ".labready", self.root / ".labready/runtime", self.target.parent, self.target, self.target / "Scripts", self.python):
            if item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction()):
                raise ValueError("Linked or junction paths require manual attention")
        if self.python.exists() and not self.python.resolve().is_relative_to(self.target.resolve()):
            raise ValueError("Practical interpreter must be inside its dedicated environment")

    def run(self, argv, timeout):
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "PIP_"))}
        # pip treats this special setting even in isolated mode: suppress ALL
        # configuration files so a system/site prefix or index cannot redirect us.
        env["PIP_CONFIG_FILE"] = os.devnull
        return self.runner(list(argv), shell=False, cwd=str(self.root), env=env, timeout=timeout,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def inspect(self, requirements):
        requirements = Requirements.model_validate(requirements)
        evidence = []
        details = {}
        def finding(status, **extra):
            return Inspection(status=status, target=str(self.target), interpreter=str(self.python),
                              evidence=evidence, details=details, **extra)
        try:
            self.safe_target()
            if requirements.python_version != "3.12":
                evidence.append(f"Python {requirements.python_version} is not available through this recipe's configured creator. Only Python 3.12 is supported here; other installed interpreters are not searched or selected. Staff must provide the required interpreter manually; packages cannot install a different Python version.")
                return finding("MANUAL ATTENTION REQUIRED", fallback_allowed=True)
            if not self.target.exists():
                base = self.run([str(self.app_python), "-I", "-B", "-c", BASE_PROBE], 20)
                if base.returncode:
                    raise ValueError("Cannot inspect the environment creator: " + base.stderr[-2000:])
                details["creator"] = json.loads(base.stdout)
                if details["creator"]["minor"] != requirements.python_version:
                    evidence.append(f"Required Python {requirements.python_version}; available creator is {details['creator']['version']}. Install/provide the required interpreter manually; packages cannot fix this.")
                    return finding("MANUAL ATTENTION REQUIRED", fallback_allowed=True)
                evidence.extend(["Dedicated practical environment does not exist: Not prepared.",
                                 f"Available creator: Python {details['creator']['version']} at {self.app_python}.",
                                 "Package availability in the missing environment is unknown; app/global packages are not used as evidence."])
                return finding("NOT PREPARED", environment_missing=True, missing_packages=list(PINS))
            marker = self.target / ".labready-owner.json"
            if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")) != self.owner():
                raise ValueError("Existing target lacks the matching LabReady ownership marker. Do not overwrite it; staff must inspect it manually.")
            if not self.python.is_file():
                raise ValueError("Dedicated environment has no usable Scripts/python.exe. Automatic deletion or recreation is not supported.")
            completed = self.run([str(self.python), "-I", "-B", "-c", PROBE], 45)
            if completed.returncode:
                raise ValueError("Dedicated interpreter probe failed: " + completed.stderr[-2000:])
            lines = [line.removeprefix("LABREADY_PROBE=") for line in completed.stdout.splitlines() if line.startswith("LABREADY_PROBE=")]
            if len(lines) != 1:
                raise ValueError("Dedicated interpreter returned no unambiguous inspection record")
            details.update(json.loads(lines[0]))
            if Path(details["prefix"]).resolve() != self.target.resolve() or details["prefix"] == details["base_prefix"]:
                raise ValueError("Interpreter is not isolated in the approved dedicated environment")
            cfg = dict(line.lower().split("=", 1) for line in (self.target / "pyvenv.cfg").read_text(encoding="utf-8").splitlines()
                       if "=" in line and not line.lstrip().startswith("#"))
            cfg = {key.strip(): value.strip() for key, value in cfg.items()}
            if cfg.get("include-system-site-packages") != "false":
                raise ValueError("Environment must exclude system site-packages")
            evidence.append(f"Actual dedicated interpreter: Python {details['version']}.")
            if details["minor"] != requirements.python_version:
                evidence.append(f"Required Python {requirements.python_version}, found {details['minor']}; packages cannot change the interpreter.")
                return finding("MANUAL ATTENTION REQUIRED", fallback_allowed=True)
            if not details.get("pip"):
                raise ValueError("Dedicated environment has no pip; repair it manually before package preparation")
            missing = []
            for name, pin in PINS.items():
                package = details["packages"].get(name, {})
                if "path" in package and not Path(package["path"]).resolve().is_relative_to(self.target.resolve()):
                    raise ValueError(f"{name} imports from outside the dedicated environment")
                actual = package.get("version")
                if actual != pin or package.get("module_version") != pin:
                    missing.append(name)
                    evidence.append(f"{name}: requires {pin}; {package.get('error') or ('installed '+str(actual))}.")
                else:
                    evidence.append(f"{name} {actual} imported from {package['path']}.")
            if missing:
                return finding("NOT PREPARED", missing_packages=missing)
            calculation = details.get("calculation", {})
            if calculation.get("passed") is not True or calculation.get("numpy_sum") != 6 or calculation.get("pandas_sum") != 60:
                evidence.append("Imports alone are insufficient: the deterministic calculation failed.")
                return finding("PREPARATION FAILED", fallback_allowed=True)
            evidence.append("Verified calculations: numpy sum = 6; pandas student total = 60.")
            return finding("READY")
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            evidence.append(f"Inspection cannot establish safe readiness: {type(exc).__name__}: {exc}")
            return finding("MANUAL ATTENTION REQUIRED", fallback_allowed=True)

    def owner(self):
        return {"recipe": "python-data", "target": str(self.target)}

    def make_plan(self, requirements, inspection, revision, resolution=None):
        actions, commands = [], []
        if inspection.status == "NOT PREPARED" and resolution is not None:
            if inspection.environment_missing:
                actions.append("Create the isolated environment with the existing Python 3.12 interpreter (no system site-packages).")
                commands.append([str(self.app_python), "-I", "-B", "-m", "venv", "--copies", str(self.target)])
            packages = [f"{name}=={pin}" for name, pin in resolution.packages.items()]
            if packages:
                actions.append("Install the dependency-resolved, exact allowlisted package set into this dedicated environment only: " + ", ".join(packages))
                commands.append([str(self.python), "-I", "-m", "pip", "--isolated", "--require-virtualenv", "--disable-pip-version-check",
                                 "install", "--no-input", "--no-cache-dir", "--retries", "0", "--timeout", "20",
                                 "--index-url", "https://pypi.org/simple", "--only-binary=:all:", "--no-deps", *packages])
            actions.append("Reinspect Python, import numpy and pandas, record versions and verify sums 6 and 60. No READY status before verification.")
            commands.append([str(self.python), "-I", "-B", "-c", PROBE])
        payload = {"revision": revision, "requirements": requirements.model_dump(), "inspection": inspection.model_dump(), "actions": actions, "commands": commands,
                   "resolution": resolution.model_dump() if resolution else None}
        return Plan(id=fingerprint(payload), **payload)

    def propose(self, requirements):
        requirements = Requirements.model_validate(requirements)
        self._approvals.clear()
        inspection = self.inspect(requirements)
        resolution = None
        if inspection.status == "NOT PREPARED":
            try:
                resolution = self.resolver(self)
                inspection.evidence.append("Published wheels and the complete dependency set were verified by pip's non-installing resolver for Windows x64 / Python 3.12.")
            except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
                inspection.status = "MANUAL ATTENTION REQUIRED"
                inspection.evidence.append(f"Cannot approve an unresolved package set: {exc}. No installation occurred; inspect again explicitly after fixing the blocker.")
                inspection.fallback_allowed = True
        plan = self.make_plan(requirements, inspection, uuid4().hex, resolution)
        self._plan = plan.model_copy(deep=True)
        return plan

    def check_plan(self, plan):
        if self._plan is None or plan.model_dump() != self._plan.model_dump():
            raise ApprovalError("Plan changed or expired. Inspect again and approve the newly displayed plan.")

    def approve(self, plan):
        """Called only by the explicit staff UI button; never an agent tool."""
        self.check_plan(plan)
        if not plan.commands or plan.inspection.status != "NOT PREPARED":
            raise ApprovalError("This plan has no supported preparation actions to approve")
        token = secrets.token_urlsafe(32)
        self._approvals[token] = plan.id
        return token

    def execute(self, plan, approval, on_event=None):
        self.check_plan(plan)
        if self._approvals.get(approval) != plan.id:
            raise ApprovalError("Explicit staff approval is required for this exact plan")
        if plan.id in self._completed:
            return self._completed[plan.id].model_copy(deep=True)
        if not self._guard.acquire(blocking=False):
            raise ApprovalError("This preparation is already running; duplicate execution was prevented")
        events = []
        def event(kind, **details):
            record = {"event": kind, **details}
            events.append(record)
            if on_event:
                on_event(record)
        result = Execution(status="PREPARING", plan_id=plan.id, evidence=["Staff approved this exact plan."], events=events)
        try:
            self.safe_target()
            with machine_lock(self.root / ".labready" / "runtime" / "python-data.lock"):
                event("reinspection_started")
                current = self.inspect(plan.requirements)
                event("reinspection_finished", result=current.model_dump())
                if plan.resolution and current.status == "NOT PREPARED":
                    current.evidence.append("Published wheels and the complete dependency set were verified by pip's non-installing resolver for Windows x64 / Python 3.12.")
                fresh = self.make_plan(plan.requirements, current, plan.revision, plan.resolution)
                if fresh.id != plan.id:
                    raise ApprovalError("Inspection or requirements changed after planning. No preparation was executed. Inspect again and approve a fresh plan.")
                event("preparing", status="PREPARING", target=str(self.target))
                for command in fresh.commands[:-1]:
                    is_creation = command[0] == str(self.app_python)
                    event("command_started", argv=command, timeout_seconds=120 if is_creation else 240)
                    completed = self.run(command, 120 if is_creation else 240)
                    event("command_finished", returncode=completed.returncode, stdout=completed.stdout[-10000:], stderr=completed.stderr[-10000:])
                    if completed.returncode:
                        raise RuntimeError("Environment creation or package installation failed. Check the captured output and internet access. No automatic retry will run.")
                    if is_creation:
                        self.safe_target()
                        (self.target / ".labready-owner.json").write_text(json.dumps(self.owner()), encoding="utf-8")
                event("verification_started")
                verified = self.inspect(plan.requirements)
                event("verification_finished", result=verified.model_dump())
                result.inspection = verified
                result.status = "READY" if verified.status == "READY" else "PREPARATION FAILED"
                result.evidence = verified.evidence if result.status == "READY" else ["Preparation commands finished, but independent verification did not establish readiness.", *verified.evidence]
                result.fallback_allowed = result.status != "READY"
        except ApprovalError as exc:
            result.status = "MANUAL ATTENTION REQUIRED"
            result.evidence = [str(exc)]
            event("approval_invalidated", error=str(exc))
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            result.status = "PREPARATION FAILED"
            result.fallback_allowed = True
            result.evidence = [f"{type(exc).__name__}: {exc}", "No automatic retry. Inspect again and approve a new plan if a retry is appropriate."]
            if isinstance(exc, subprocess.TimeoutExpired):
                event("command_timed_out", timeout_seconds=exc.timeout, stdout=str(exc.stdout or "")[-10000:], stderr=str(exc.stderr or "")[-10000:])
            else:
                event("preparation_failed", error=str(exc))
        finally:
            result.events = events
            self._completed[plan.id] = result.model_copy(deep=True)
            self._guard.release()
        return result


class PreparationController:
    """Per-user approval state. A new inspection invalidates earlier outcomes."""
    def __init__(self, service=None):
        self.service = service or PreparationService()
        self.plan = None
        self.result = None
        self.busy = False

    def invalidate(self):
        self.plan = None
        self.result = None
        self.service._approvals.clear()

    def inspect(self, requirements):
        self.invalidate()
        self.plan = self.service.propose(requirements)
        return self.plan

    def prepare(self, requirements, plan_id, on_event=None):
        if self.busy:
            raise ApprovalError("Preparation already running")
        if self.plan is None or self.plan.id != plan_id or self.plan.requirements != requirements:
            self.invalidate()
            raise ApprovalError("Requirements or plan changed. Inspect again before approval.")
        if self.result is not None:
            return self.result
        self.busy = True
        self.result = None
        try:
            approval = self.service.approve(self.plan)
            self.result = self.service.execute(self.plan, approval, on_event)
            return self.result
        finally:
            self.busy = False
