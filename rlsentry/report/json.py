"""report/json.py: the JSON report (FR-12; NFR-03; ADR-044)."""
from __future__ import annotations

from rlsentry.contracts.models import ScanReport
from rlsentry.recon.links import report_url
from rlsentry.safety.mask import mask_text


def render_json(report: ScanReport) -> str:
    """Serialise the whole report; the target loses its query string and keys are masked.

    Why mask again here: per-module masking can miss a field, and the JSON file is the one
    artefact CI uploads, so a final pass guarantees no key leaves the process (NFR-03).
    """
    update: dict[str, object] = {"target": report_url(report.target)}
    if report.recon is not None and report.recon.supabase_url:
        update["recon"] = report.recon.model_copy(
            update={"supabase_url": report_url(report.recon.supabase_url)}
        )
    safe = report.model_copy(update=update)
    return mask_text(safe.model_dump_json(indent=2, by_alias=True))
