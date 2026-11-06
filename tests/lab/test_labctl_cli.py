"""lab/_shared/__main__.py: the shell entry used by USAGE.md doctests and docs/demo.md (ADR-052).

Contract: rlsentry/contracts/lab.py LAB_CLI. Commands that touch the lab are called in-process
(main(argv)) because this pytest session holds the lab lock; `serve` runs as a child process
because it never takes the lock and must be stopped by a signal.
"""
from __future__ import annotations

import shlex
import signal
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from lab._shared.__main__ import main

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS
from rlsentry.contracts.lab import LAB_ENV_ANON, LAB_ENV_DB, LabInfo
from rlsentry.contracts.models import Role


def run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_env_prints_one_export_line_with_the_lab_values(lab_info: LabInfo, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(["env"], capsys)
    lines = out.strip().splitlines()
    assert code == 0 and len(lines) == 1 and lines[0].startswith("export ")
    pairs = [w.split("=", 1) for w in shlex.split(lines[0])[1:]]
    names = [LAB_ENV_ANON, LAB_ENV_DB, LAB_USERS[Role.USER_A]["password_env"], LAB_USERS[Role.USER_B]["password_env"]]
    assert [k for k, _ in pairs] == names
    assert dict(pairs) == {LAB_ENV_ANON: lab_info.anon_key, LAB_ENV_DB: lab_info.db_url,
                           names[2]: labctl.lab_password(Role.USER_A), names[3]: labctl.lab_password(Role.USER_B)}


def test_up_prints_the_api_url(lab_info: LabInfo, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["up"], capsys)[:2] == (0, lab_info.api_url + "\n")


def test_apply_loads_the_scenario(lab_info: LabInfo, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["apply", "L04"], capsys)[:2] == (0, "applied L04\n")
    assert labctl.query("SELECT count(*) FROM pg_policies WHERE tablename = 'notes'") == [("4",)]
    code, _, err = run(["apply", "L99"], capsys)
    assert code == 2 and err.strip() and len(err.strip().splitlines()) == 1


def test_sql_reads_stdin_and_reports_errors(lab_info: LabInfo, capsys: pytest.CaptureFixture[str],
                                            monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    run(["apply", "L04"], capsys)
    monkeypatch.setattr(sys, "stdin", io.StringIO("DROP POLICY notes_select ON public.notes;"))
    assert run(["sql"], capsys)[:2] == (0, "ok\n")
    assert labctl.query("SELECT count(*) FROM pg_policies WHERE policyname = 'notes_select'") == [("0",)]
    monkeypatch.setattr(sys, "stdin", io.StringIO("SELECT * FROM no_such_table;"))
    code, _, err = run(["sql"], capsys)
    assert code == 1 and "no_such_table" in err
    run(["apply", "L04"], capsys)


@pytest.mark.parametrize("argv", [[], ["nope"]])
def test_usage_errors_exit_2(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert run(argv, capsys)[0] == 2


def listeners(port: int) -> list[str]:
    """Local IPv4 addresses (hex, /proc/net/tcp) listening on `port` (state 0A = LISTEN)."""
    out = []
    for line in Path("/proc/net/tcp").read_text().splitlines()[1:]:
        f = line.split()
        addr, p = f[1].split(":")
        if f[3] == "0A" and int(p, 16) == port:
            out.append(addr)
    return out


def test_serve_binds_localhost_and_stops_on_sigterm() -> None:
    port = 18741
    p = subprocess.Popen([sys.executable, "-m", "lab._shared", "serve", "L04", "--port", str(port)],
                         stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout is not None
        assert p.stdout.readline().strip() == f"http://127.0.0.1:{port}/"
        r = httpx.get(f"http://127.0.0.1:{port}/index.html", timeout=5)
        assert r.status_code == 200 and "<" in r.text
        assert listeners(port) == ["0100007F"]                # 127.0.0.1 only, never 0.0.0.0
    finally:
        p.send_signal(signal.SIGTERM)
        assert p.wait(timeout=10) == 0


def test_serve_unknown_scenario_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["serve", "L99", "--port", "18742"], capsys)[0] == 2
