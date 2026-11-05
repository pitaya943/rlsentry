"""recon() over real HTTP against every lab frontend (labctl.serve_frontend; no Docker; T-189/T-190).

MS5 focus: the service_role key in L08 is Critical; the anon key present in all 16 frontends is
never reported as a finding.
"""
from __future__ import annotations

import asyncio
import re

import pytest

from lab._shared import labctl
from rlsentry.contracts.models import Profile, Severity
from rlsentry.contracts.recon import ReconOutput
from rlsentry.recon.run import recon
from rlsentry.safety.http import SafeClient
from rlsentry.safety.ratelimit import RateLimiter
from tests.recon.helpers import assert_no_raw

SCENARIOS = ["L01", "L02", "L03", "L04", "L05", "L06", "L07", "L08", "L09", "L10", "L11", "L12",
             "C01", "C02", "C03", "C04"]


def _recon(sid: str) -> tuple[ReconOutput, str]:
    async def go(url: str) -> ReconOutput:
        async with SafeClient(profile=Profile.AUDIT, limiter=RateLimiter(rps=50, concurrency=4)) as c:
            return await recon(c, url)
    with labctl.serve_frontend(sid) as url:
        return asyncio.run(go(url)), url


@pytest.mark.parametrize("sid", SCENARIOS)
def test_lab_frontend(sid: str) -> None:
    out, url = _recon(sid)
    assert out.result.supabase_url == "http://127.0.0.1:54321"
    assert out.result.chunks_scanned == [url, url + "assets/app.js"]
    labels = [(k.label, k.kind) for k in out.result.keys]
    assert ("jwt:anon", "publishable") in labels
    assert out.anon_key is not None and out.anon_key.startswith("eyJ")
    if sid == "L08":
        assert [(f.target, f.rule, f.severity) for f in out.findings] == [
            ("jwt:service_role", "SECRET_KEY_IN_BUNDLE", Severity.CRITICAL)]
        assert labels == [("jwt:service_role", "secret"), ("jwt:anon", "publishable")]
    else:
        assert out.findings == [] and labels == [("jwt:anon", "publishable")]


@pytest.mark.safety
def test_l08_report_has_no_raw_key() -> None:
    out, _ = _recon("L08")
    text = (labctl.scenario_dir("L08") / "frontend" / "assets" / "app.js").read_text("utf-8")
    raws = re.findall(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", text)
    assert len(raws) == 2
    assert_no_raw(out.result.model_dump_json() + "".join(f.model_dump_json() for f in out.findings)
                  + repr(out), raws)
