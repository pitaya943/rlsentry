"""MS6 audit (ADR-047): recon.supabase_url comes from the target's bundle, so reports write it
through report_url (no userinfo, no query) like every other URL."""
from __future__ import annotations

from rlsentry.contracts.models import ReconResult
from rlsentry.report.html import render_html
from rlsentry.report.json import render_json
from tests.report.helpers import report


def test_bundle_url_is_reported_without_userinfo_or_query() -> None:
    rep = report().model_copy(update={"recon": ReconResult(supabase_url="https://u:pw@x.test/?apikey=opaque123")})
    for text in (render_json(rep), render_html(rep)):
        assert "pw@" not in text and "opaque123" not in text and "x.test" in text
