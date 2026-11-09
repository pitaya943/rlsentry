"""NFR-03 for URLs written to the report (MS5 audit S1–S3; ADR-036 補記; T-193)."""
from __future__ import annotations

import pytest

from rlsentry.recon.links import report_url, same_origin
from rlsentry.recon.run import recon
from tests.fakes import Recorder, run
from tests.recon.helpers import ORIGIN, SB_SECRET, SERVICE_JWT, StaticSite, assert_no_raw

pytestmark = pytest.mark.safety
GOOGLE = "AIzaSyQ7xT2mVb9KpL4zWc8RnJ5yHd3fGa6s1E"


def test_report_url_forms() -> None:
    assert report_url("http://h/assets/a.js") == "http://h/assets/a.js"
    assert report_url(f"http://h/a.js?apikey={GOOGLE}&v=1") == "http://h/a.js?…"
    assert report_url("http://h/a.js?") == "http://h/a.js"
    assert report_url("http://u:p@h:8080/a.js") == "http://h:8080/a.js"
    assert report_url(f"http://h/m/{SERVICE_JWT}/a.js") == f"http://h/m/{SERVICE_JWT[:6]}****{SERVICE_JWT[-4:]}/a.js"
    assert report_url(f"http://h/a.js.map?t=1#webpack://app/{SB_SECRET}.ts#x") == (
        f"http://h/a.js.map?…#webpack://app/{SB_SECRET[:6]}****{SB_SECRET[-4:]}.ts#x")
    once = report_url(f"http://h/a.js?k={SB_SECRET}#src/{SERVICE_JWT}")
    assert report_url(once) == once


def test_userinfo_is_never_same_origin() -> None:
    assert not same_origin("http://u:p@fixture.test/x.js", "http://fixture.test/")
    assert not same_origin("http://u@fixture.test/x.js", "http://fixture.test/")


def test_scanned_urls_and_sources_are_masked() -> None:
    js_url = f"{ORIGIN}/a.js?k={SB_SECRET}&g={GOOGLE}"
    map_url = f"{ORIGIN}/a.js.map"
    site = StaticSite(None, extra={
        ORIGIN + "/": (200, (f'<script src="/a.js?k={SB_SECRET}&g={GOOGLE}"></script>'
                             '<script src="http://u:p@fixture.test/b.js"></script>'), {}),
        js_url: (200, f'k="{SERVICE_JWT}"\n//# sourceMappingURL=/a.js.map', {}),
        map_url: (200, '{"sources":["src/' + SERVICE_JWT + '.ts"],"sourcesContent":["s()"]}', {}),
    })
    out = run(lambda c: recon(c, ORIGIN + "/"), Recorder(site))
    assert out.result.chunks_scanned == [ORIGIN + "/", ORIGIN + "/a.js?…", map_url]
    assert out.result.chunks_skipped == [f"{ORIGIN}/b.js (cross-origin)"]
    assert [k.source_file for k in out.result.keys if k.label == "jwt:service_role"] == [
        ORIGIN + "/a.js?…", map_url]   # the map JSON itself is scanned too
    assert all("u:p@" not in str(r.url) and "authorization" not in {h.lower() for h in r.headers}
               for r in site.requests)
    dumped = out.result.model_dump_json() + "".join(f.model_dump_json() for f in out.findings) + repr(out)
    assert_no_raw(dumped, [SB_SECRET, GOOGLE, SERVICE_JWT])
