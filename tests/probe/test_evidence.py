"""probe/evidence.py (NFR-03: masked reproduction commands). Contract: rlsentry/contracts/probe.py."""
import shlex

import pytest

from rlsentry.contracts.safety import JWT_RE, SB_KEY_RE
from rlsentry.probe.evidence import curl_command
from rlsentry.safety.mask import mask
from tests.fakes import ANON, URL, fake_jwt

TOKEN = fake_jwt("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def test_head_command_shape() -> None:
    url = URL + "/rest/v1/notes?select=id&id=in.(%221%22)"
    cmd = curl_command("HEAD", url, {"apikey": ANON, "Authorization": f"Bearer {TOKEN}", "Prefer": "count=exact"})
    assert cmd == ("curl -sS -I " + shlex.quote(url) + " -H " + shlex.quote(f"apikey: {mask(ANON)}")
                   + " -H " + shlex.quote(f"Authorization: Bearer {mask(TOKEN)}") + " -H 'Prefer: count=exact'")


def test_other_methods_use_x_flag() -> None:
    assert curl_command("GET", URL + "/rest/v1/", {}) == f"curl -sS -X GET {URL}/rest/v1/"


@pytest.mark.safety
def test_non_jwt_secrets_in_auth_headers_are_masked() -> None:
    opaque = "opaque-session-token-0123456789abcdef"
    cmd = curl_command("HEAD", URL, {"APIKEY": opaque, "authorization": opaque})
    assert opaque not in cmd and cmd.count(mask(opaque)) == 2


@pytest.mark.safety
def test_secrets_anywhere_are_masked() -> None:
    sb = "sb_secret_" + "N7UND0UgjKTVK" + "-4p6Ew_NfJCnkYPZmsk"
    cmd = curl_command("GET", f"{URL}/x?token={TOKEN}&k={sb}", {"X-Debug": TOKEN})
    assert JWT_RE.search(cmd.replace(mask(TOKEN), "")) is None and SB_KEY_RE.search(cmd) is None
    assert TOKEN not in cmd and sb not in cmd


def test_quoting_is_shell_safe() -> None:
    url = URL + "/rest/v1/t?x=it's"
    assert shlex.split(curl_command("HEAD", url, {"Prefer": "a b"})) == ["curl", "-sS", "-I", url, "-H", "Prefer: a b"]
