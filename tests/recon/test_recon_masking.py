"""NFR-03: no complete key in any recon output, repr or skipped-URL entry (SPEC §9 安全不變式; T-187)."""
from __future__ import annotations

import pytest

from rlsentry.contracts.recon import Candidate, FetchedFile
from rlsentry.recon.run import recon
from rlsentry.safety.mask import mask_text
from tests.fakes import Recorder, run
from tests.recon.helpers import (
    FIXTURE_SECRETS,
    FIXTURES,
    ORIGIN,
    SB_SECRET,
    SERVICE_JWT,
    StaticSite,
    assert_no_raw,
)

pytestmark = pytest.mark.safety


@pytest.mark.parametrize("fw", ["nextjs", "vite", "cra"])
def test_report_parts_and_repr_are_masked(fw: str) -> None:
    out = run(lambda c: recon(c, ORIGIN + "/"), Recorder(StaticSite(FIXTURES / fw)))
    raws = FIXTURE_SECRETS[fw]
    assert len(out.result.keys) == len(raws)        # every planted value was found …
    dumped = out.result.model_dump_json() + "".join(f.model_dump_json() for f in out.findings)
    assert_no_raw(dumped, raws)                     # … and none is in the report parts
    assert_no_raw(repr(out) + str(out), raws)
    assert mask_text(dumped) == dumped
    assert {k.masked[:6] for k in out.result.keys} <= {r[:6] for r in raws}


def test_skipped_url_with_token_is_masked() -> None:
    html = (f'<script src="https://cdn.example/sdk.js?key={SERVICE_JWT}"></script>'
            f'<script src="/missing.js?k={SB_SECRET}"></script>')
    site = StaticSite(None, extra={ORIGIN + "/": (200, html, {})})
    out = run(lambda c: recon(c, ORIGIN + "/"), Recorder(site))
    text = "".join(out.result.chunks_skipped)
    assert len(out.result.chunks_skipped) == 2
    assert_no_raw(text + out.result.model_dump_json() + repr(out), [SERVICE_JWT, SB_SECRET])


def test_in_memory_types_do_not_print_values() -> None:
    assert_no_raw(repr(Candidate(SERVICE_JWT, "jwt")) + str(Candidate(SB_SECRET, "sb_secret")),
                  [SERVICE_JWT, SB_SECRET])
    f = FetchedFile(url="http://h/a.js", kind="js", text=f'k="{SERVICE_JWT}"')
    assert_no_raw(repr(f) + str(f), [SERVICE_JWT])
