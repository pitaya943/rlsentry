"""require_write_allowed (T-051). NFR-01; contract: rlsentry/contracts/safety.py;
ADR-014 #1 #3, ADR-017. No request is ever sent: these are pure gate decisions."""
import pytest

from rlsentry.contracts.interfaces import WriteRefused
from rlsentry.contracts.models import Profile
from rlsentry.safety.mode import require_write_allowed

DEV, CI, AUDIT = Profile.DEV, Profile.CI, Profile.AUDIT
LOCAL = "http://127.0.0.1:54321/rest/v1/notes"
REMOTE = "https://preview.example.test/rest/v1/notes"
LOGIN = "https://prod.example.test/auth/v1/token?grant_type=password"
ALL = [DEV, CI, AUDIT]


def ok(profile: Profile, method: str, url: str, hosts: tuple[str, ...] = ()) -> None:
    require_write_allowed(profile, method, url, hosts)


def refused(profile: Profile, method: str, url: str, hosts: tuple[str, ...] = ()) -> str:
    with pytest.raises(WriteRefused) as e:
        require_write_allowed(profile, method, url, hosts)
    return str(e.value)


@pytest.mark.parametrize("profile", ALL)
@pytest.mark.parametrize("method", ["GET", "HEAD", "get", "head"])
def test_reads_always_allowed(profile: Profile, method: str) -> None:
    ok(profile, method, "https://anything.example.test/rest/v1/x?select=id")


@pytest.mark.safety
@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT", "DELETE", "OPTIONS", "post"])
def test_audit_refuses_every_write_even_on_localhost(method: str) -> None:
    refused(AUDIT, method, LOCAL)
    refused(AUDIT, method, REMOTE, ("preview.example.test",))


@pytest.mark.safety
@pytest.mark.parametrize("profile", ALL)
def test_login_allowed_in_every_profile(profile: Profile) -> None:
    ok(profile, "POST", LOGIN)
    ok(profile, "post", LOGIN)


@pytest.mark.safety
@pytest.mark.parametrize("url", [
    "https://prod.example.test/auth/v1/token?grant_type=refresh_token",
    "https://prod.example.test/auth/v1/token?grant_type=password&x=1",
    "https://prod.example.test/auth/v1/token",
    "https://prod.example.test/auth/v1/token/?grant_type=password",
    "https://prod.example.test/auth/v1/signup?grant_type=password",
    "https://prod.example.test/auth/v1/user",
])
def test_login_exception_is_exact(url: str) -> None:
    refused(AUDIT, "POST", url)


@pytest.mark.safety
def test_login_exception_is_post_only() -> None:
    refused(AUDIT, "PUT", LOGIN)
    refused(AUDIT, "DELETE", LOGIN)


@pytest.mark.safety
@pytest.mark.parametrize("profile", ALL)
def test_rpc_never_posted(profile: Profile) -> None:
    refused(profile, "POST", "http://localhost:54321/rest/v1/rpc/get_all_accounts")
    refused(profile, "POST", "https://preview.example.test/rest/v1/rpc/f", ("preview.example.test",))
    ok(profile, "GET", "http://localhost:54321/rest/v1/rpc/get_all_accounts")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "LOCALHOST"])
@pytest.mark.parametrize("profile", [DEV, CI])
def test_dev_and_ci_write_to_localhost(host: str, profile: Profile) -> None:
    ok(profile, "PATCH", f"http://{host}:54321/rest/v1/notes?id=eq.1")


@pytest.mark.safety
def test_dev_never_writes_remote_even_if_listed() -> None:
    refused(DEV, "POST", REMOTE)
    refused(DEV, "POST", REMOTE, ("preview.example.test",))


@pytest.mark.safety
def test_ci_writes_remote_only_when_listed_exactly() -> None:
    refused(CI, "POST", REMOTE)
    ok(CI, "POST", REMOTE, ("preview.example.test",))
    ok(CI, "POST", REMOTE, ("other.test", "PREVIEW.example.test"))
    refused(CI, "POST", REMOTE, ("example.test",))
    refused(CI, "POST", REMOTE, ("*.example.test",))
    refused(CI, "POST", "https://evil-preview.example.test/rest/v1/notes", ("preview.example.test",))
    refused(CI, "POST", "https://preview.example.test.evil.test/x", ("preview.example.test",))


@pytest.mark.safety
def test_ci_port_rules() -> None:
    url = "https://preview.example.test:8443/rest/v1/notes"
    ok(CI, "DELETE", url, ("preview.example.test",))
    ok(CI, "DELETE", url, ("preview.example.test:8443",))
    refused(CI, "DELETE", url, ("preview.example.test:9999",))
    refused(CI, "DELETE", REMOTE, ("preview.example.test:443",))


@pytest.mark.safety
def test_userinfo_cannot_disguise_host() -> None:
    refused(DEV, "POST", "http://localhost@evil.test/rest/v1/notes")
    refused(CI, "POST", "http://preview.example.test@evil.test/x", ("preview.example.test",))


@pytest.mark.safety
@pytest.mark.parametrize("url", ["ftp://localhost/x", "file:///etc/passwd", "localhost/rest", "http:///x"])
def test_bad_urls_refused_for_any_method(url: str) -> None:
    refused(DEV, "POST", url)
    refused(DEV, "GET", url)


@pytest.mark.safety
def test_message_names_context_but_not_query() -> None:
    msg = refused(AUDIT, "PATCH", "https://prod.example.test/rest/v1/notes?id=eq.SECRETROW&apikey=eyJx")
    assert "audit" in msg and "PATCH" in msg and "prod.example.test" in msg
    assert "SECRETROW" not in msg and "eyJx" not in msg
