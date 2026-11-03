"""log_line_prefix is set explicitly by ensure_up (T-085; MS1 audit P2-1). Needs Docker."""
from pathlib import Path

from lab._shared import labctl
from rlsentry.contracts.lab import LOG_LINE_PREFIX, LabInfo


def test_log_line_prefix_is_the_contract_value(lab_info: LabInfo) -> None:
    assert labctl.query("show log_line_prefix") == [(LOG_LINE_PREFIX,)]


def test_parser_uses_the_contract_prefix() -> None:
    src = Path(labctl.__file__ or "").read_text(encoding="utf-8")
    assert "LOG_LINE_PREFIX" in src, "labctl must import LOG_LINE_PREFIX instead of hard-coding a format"
