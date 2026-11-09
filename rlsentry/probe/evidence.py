"""probe/evidence.py (NFR-03): masked curl reproduction commands."""
import shlex
from collections.abc import Mapping

from rlsentry.safety.mask import mask, mask_text

_BEARER = "Bearer "


def _header_value(name: str, value: str) -> str:
    lowered = name.lower()
    if lowered == "apikey":
        return mask(value)
    if lowered == "authorization":
        if value.startswith(_BEARER):
            return _BEARER + mask(value[len(_BEARER):])
        return mask(value)
    return value


def curl_command(method: str, url: str, headers: Mapping[str, str]) -> str:
    """Build a reproduction command whose secrets are masked, so evidence is safe to publish.

    Auth headers are masked by name (covers opaque tokens); mask_text then catches any
    JWT or sb_ key elsewhere, such as in the URL.
    """
    parts = ["curl -sS", " -I" if method.upper() == "HEAD" else f" -X {method.upper()}", " ", shlex.quote(url)]
    for name, value in headers.items():
        parts.append(" -H " + shlex.quote(f"{name}: {_header_value(name, value)}"))
    return mask_text("".join(parts))
