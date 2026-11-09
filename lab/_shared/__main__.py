"""Shell entry for USAGE.md doctests and docs/demo.md (ADR-052). Contract: LAB_CLI in
rlsentry/contracts/lab.py. Only calls existing labctl functions."""
from __future__ import annotations

import argparse
import shlex
import signal
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from types import FrameType
from typing import NoReturn

from lab._shared import labctl
from rlsentry.contracts.ground_truth import LAB_USERS
from rlsentry.contracts.lab import LAB_ENV_ANON, LAB_ENV_DB
from rlsentry.contracts.models import Role


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return None


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        print(message, file=sys.stderr)
        raise SystemExit(2)


def _parser() -> _Parser:
    p = _Parser(prog="python -m lab._shared")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("up")
    sub.add_parser("env")
    sub.add_parser("sql")
    sub.add_parser("apply").add_argument("scenario")
    s = sub.add_parser("serve")
    s.add_argument("scenario")
    s.add_argument("--port", type=int, required=True)
    return p


def _serve(scenario: str, port: int) -> int:
    """Serve the frontend on 127.0.0.1 only; no lab lock because it only reads files."""
    root = labctl.scenario_dir(scenario) / "frontend"
    if not (root / "index.html").is_file():
        raise ValueError(f"scenario {scenario!r}: no frontend/index.html")
    server = ThreadingHTTPServer(("127.0.0.1", port), partial(_Quiet, directory=str(root)))
    stop = threading.Event()

    def _handler(signum: int, frame: FrameType | None) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    print(f"http://127.0.0.1:{port}/", flush=True)
    thread.start()
    try:
        stop.wait()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 2
    try:
        if args.cmd == "up":
            print(labctl.ensure_up().api_url)
        elif args.cmd == "apply":
            labctl.ensure_up()
            labctl.apply(args.scenario)
            print(f"applied {args.scenario}")
        elif args.cmd == "env":
            info = labctl.ensure_up()
            ua, ub = (LAB_USERS[r]["password_env"] for r in (Role.USER_A, Role.USER_B))
            vals = [(LAB_ENV_ANON, info.anon_key), (LAB_ENV_DB, info.db_url),
                    (ua, labctl.lab_password(Role.USER_A)), (ub, labctl.lab_password(Role.USER_B))]
            print("export " + " ".join(f"{k}={shlex.quote(v)}" for k, v in vals))
        elif args.cmd == "sql":
            labctl.execute(sys.stdin.read())
            print("ok")
        else:
            return _serve(args.scenario, args.port)
    except ValueError as e:
        print(str(e).replace("\n", " "), file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
