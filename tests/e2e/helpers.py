"""Shared helpers for the e2e tests: load a scenario and run run_scan through a recording transport."""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import yaml

from lab._shared import labctl
from rlsentry import run_scan
from rlsentry.contracts.ground_truth import GroundTruth
from rlsentry.contracts.models import Evidence, Finding, ScanReport
from rlsentry.contracts.rules import RULES


class Recording(httpx.AsyncBaseTransport):
    """Real network transport (localhost only: the lab) that remembers every request."""

    def __init__(self) -> None:
        self.inner = httpx.AsyncHTTPTransport()
        self.seen: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()

    def ports(self) -> set[int | None]:
        return {r.url.port for r in self.seen}


def gt(sid: str) -> GroundTruth:
    return GroundTruth.model_validate(yaml.safe_load((labctl.scenario_dir(sid) / "expected.yaml").read_text("utf-8")))


def scan(config: Any, env: dict[str, str], rec: Recording | None = None, **kw: Any) -> ScanReport:
    return asyncio.run(run_scan(config, env=env, transport=rec, confirmed_by="e2e", **kw))


def proven(rep: ScanReport) -> list[Finding]:
    return [f for f in rep.findings if f.evidence is Evidence.CONFIRMED and RULES[f.rule].vulnerability]


def keys(fs: list[Finding]) -> set[tuple[str | None, str | None, str]]:
    return {(f.target, f.role.value if f.role else None, f.rule) for f in fs}
