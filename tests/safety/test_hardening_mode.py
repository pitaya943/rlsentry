"""MS1 safety audit fixes for the write gate (T-083; ADR-020). Contract: rlsentry/contracts/safety.py."""
import pytest
from pydantic import ValidationError

from rlsentry.contracts.interfaces import WriteRefused
from rlsentry.contracts.models import Profile
from rlsentry.contracts.policy import ScanConfig
from rlsentry.safety.mode import require_write_allowed

LOCAL = "http://localhost:54321/rest/v1/notes"


@pytest.mark.safety
@pytest.mark.parametrize("profile", ["AUDIT", "audit", "dev", None, 0])
@pytest.mark.parametrize("method", ["POST", "GET"])
def test_unknown_profile_fails_closed(profile: object, method: str) -> None:
    with pytest.raises(WriteRefused):
        require_write_allowed(profile, method, LOCAL)  # deliberately not a Profile


@pytest.mark.safety
@pytest.mark.parametrize("path", ["/rest/v1/%72pc/f", "/rest/v1/%2572pc/f", "/REST/V1/RPC/f",
                                  "/rest/v1//rpc/f", "//rest/v1/rpc/f", "/rest/v1/rpc%2Ff"])
@pytest.mark.parametrize("profile", [Profile.DEV, Profile.CI])
def test_rpc_ban_survives_path_tricks(path: str, profile: Profile) -> None:
    with pytest.raises(WriteRefused):
        require_write_allowed(profile, "POST", f"http://localhost:54321{path}")


def test_non_rpc_paths_still_writable_in_dev() -> None:
    require_write_allowed(Profile.DEV, "POST", "http://localhost:54321/rest/v1/rpcs_log")
    require_write_allowed(Profile.DEV, "PATCH", "http://localhost:54321/rest/v1/notes?id=eq.1")


@pytest.mark.safety
@pytest.mark.parametrize("entry", ["preview.example.test:443", "preview.example.test:80"])
def test_write_hosts_default_port_rejected(entry: str) -> None:
    with pytest.raises(ValidationError, match="default port"):
        ScanConfig.model_validate({"target": "https://x.test", "write_hosts": [entry]})
