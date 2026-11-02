"""Parse rlsentry.yaml text into a ScanConfig (SPEC §6, FR-10). Pure: no file or env access."""
from __future__ import annotations

import yaml
from pydantic import ValidationError

from rlsentry.contracts.policy import ConfigError, ScanConfig


def load_config(text: str) -> ScanConfig:
    """Validate config text; every failure becomes a ConfigError naming the key path.

    Why: a mistyped key silently ignored would hide a policy rule, so errors must be
    precise. Environment variables are never read.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError("config root must be a mapping")
    try:
        return ScanConfig.model_validate(data)
    except ValidationError as e:
        parts = []
        for err in e.errors():
            path = ".".join(str(p) for p in err["loc"]) or "<root>"
            parts.append(f"{path}: {err['msg']}")
        raise ConfigError("; ".join(parts)) from e
