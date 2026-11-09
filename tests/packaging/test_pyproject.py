"""Packaging (T-040; MS0 approval note #1): the wheel holds the product package and nothing else.

The build runs on a copy of the repository (so no build/ or *.egg-info is left behind) that
keeps every top-level directory, because their presence is what broke setuptools' automatic
flat-layout discovery. --no-build-isolation keeps the test offline: it uses the installed
setuptools (dev extra, >= 75; Debian's patched 68.x cannot build wheels).
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = shutil.ignore_patterns(".git", ".claude", "build", "*.egg-info", "__pycache__", "logs")


def test_wheel_contains_only_rlsentry(tmp_path: Path) -> None:
    src = tmp_path / "src"
    shutil.copytree(ROOT, src, ignore=SKIP)
    (src / "logs").mkdir()          # keep the directory that confused discovery, not its content
    out = tmp_path / "dist"
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
                        "-q", "-w", str(out), str(src)], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr[-800:]
    wheels = list(out.glob("rlsentry-*.whl"))
    assert len(wheels) == 1
    names = zipfile.ZipFile(wheels[0]).namelist()
    top = {n.split("/")[0] for n in names if not n.split("/")[0].endswith(".dist-info")}
    assert top == {"rlsentry"}
    assert "rlsentry/contracts/models.py" in names
