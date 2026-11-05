"""labctl imports without fcntl (Windows) and only lock() needs it (MS2 approval note 5).

Contract: rlsentry/contracts/lab.py LabCtl.lock. No Docker needed. The fcntl-absent case runs
in a SUBPROCESS: reloading the shared labctl module in-process would rebind its lock
threadlocal and deadlock against the session-scoped lab flock held by tests/lab/conftest.py
when the whole suite runs together (T-131).
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from lab._shared import labctl

ROOT = Path(__file__).resolve().parents[2]

# Simulate a platform without fcntl: sys.modules["fcntl"] = None makes `import fcntl` raise
# ImportError. labctl must still import and run its Docker-free pure helpers; only lock() fails.
_SCRIPT = textwrap.dedent(
    """
    import sys
    sys.modules["fcntl"] = None
    from lab._shared import labctl
    assert labctl.write_command('UPDATE "public"."t" SET "a" = $1') == "UPDATE"
    try:
        with labctl.lock():
            pass
    except ImportError:
        print("LOCK_RAISED_IMPORTERROR")
    else:
        raise AssertionError("lock() must raise ImportError without fcntl")
    print("IMPORT_OK")
    """
)


def _run_without_fcntl() -> subprocess.CompletedProcess[str]:
    # Not -I: isolated mode drops PYTHONPATH, so the `lab` package would not import. This is our
    # own inline script, run from the repo root with PYTHONPATH set.
    return subprocess.run([sys.executable, "-c", _SCRIPT], cwd=ROOT, text=True,
                          capture_output=True, env={"PYTHONPATH": str(ROOT)}, timeout=60, check=False)


def test_module_imports_and_classifies_without_fcntl() -> None:
    proc = _run_without_fcntl()
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "IMPORT_OK" in proc.stdout


def test_lock_is_the_only_part_that_needs_fcntl() -> None:
    proc = _run_without_fcntl()
    assert "LOCK_RAISED_IMPORTERROR" in proc.stdout, f"stdout: {proc.stdout} stderr: {proc.stderr}"


def test_lock_still_works_where_fcntl_exists() -> None:
    # In-process, no reload: re-entrant use is safe even under the session lab lock.
    with labctl.lock(), labctl.lock():
        pass
