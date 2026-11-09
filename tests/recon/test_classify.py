"""recon/classify.py: JWT decoded without verification, FR-03 classes, labels, findings (T-182)."""
from __future__ import annotations

import pytest

from rlsentry.contracts.models import Evidence, Severity, finding_id
from rlsentry.contracts.recon import KEY_LABEL_RE, Candidate
from rlsentry.recon.classify import classify_key, decode_jwt_claims, findings_from_keys, key_finding
from tests.recon.helpers import ANON_JWT, SB_PUBLISHABLE, SB_SECRET, SERVICE_JWT, make_jwt


def test_decode_keeps_only_role_ref_exp() -> None:
    tok = make_jwt({"role": "anon", "ref": "abc", "exp": 1983812996, "sub": "u-1",
                    "email": "a@example.com", "iat": 1})
    assert decode_jwt_claims(tok) == {"role": "anon", "ref": "abc", "exp": 1983812996}


def test_decode_ignores_signature_and_header() -> None:
    # 不驗簽（FR-03）：任何簽章、甚至 alg=none 都照樣解出 payload。
    tok = make_jwt({"role": "service_role"}, header={"alg": "none"}, sig="")
    assert decode_jwt_claims(tok) == {"role": "service_role"}


@pytest.mark.parametrize("bad", [
    "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9",            # two parts
    "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5v!!!.sig",         # bad base64
    "eyJhbGciOiJIUzI1NiJ9.bm90IGpzb24.sig",                 # not JSON
    "eyJhbGciOiJIUzI1NiJ9.WzEsMl0.sig",                     # JSON array, not object
    "a.b.c.d",
])
def test_decode_rejects_malformed(bad: str) -> None:
    assert decode_jwt_claims(bad) is None


def test_decode_non_scalar_claims_become_none() -> None:
    tok = make_jwt({"role": ["anon"], "exp": True, "ref": 7})
    assert decode_jwt_claims(tok) == {"role": None, "exp": None, "ref": 7}


@pytest.mark.parametrize("cand, kind, label", [
    (Candidate(ANON_JWT, "jwt"), "publishable", "jwt:anon"),
    (Candidate(SERVICE_JWT, "jwt"), "secret", "jwt:service_role"),
    (Candidate(make_jwt({"role": "authenticated"}), "jwt"), "unverified", "jwt:authenticated"),
    (Candidate(make_jwt({"role": "Service-Role"}), "jwt"), "unverified", "unverified"),
    (Candidate(make_jwt({"iss": "x"}), "jwt"), "unverified", "unverified"),
    (Candidate("eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoi.zz", "jwt"), "unverified", "unverified"),
    (Candidate(SB_PUBLISHABLE, "sb_publishable"), "publishable", "sb_publishable"),
    (Candidate(SB_SECRET, "sb_secret"), "secret", "sb_secret"),
    (Candidate("AIzaSyQ7xT2mVb9KpL4zWc8RnJ5yHd3fGa6s1E", "generic"), "unverified", "unverified"),
])
def test_classify_key(cand: Candidate, kind: str, label: str) -> None:
    got_kind, got_label, _ = classify_key(cand)
    assert (got_kind, got_label) == (kind, label)
    assert KEY_LABEL_RE.match(got_label)


def test_key_finding_masks_and_keeps_claims() -> None:
    kf = key_finding(Candidate(SERVICE_JWT, "jwt"), "http://h/assets/admin.js")
    assert kf.kind == "secret" and kf.label == "jwt:service_role"
    assert kf.masked == SERVICE_JWT[:6] + "****" + SERVICE_JWT[-4:]
    assert kf.jwt_claims == {"role": "service_role", "ref": "abcdefghijklmnopqrst", "exp": 2000000000}
    assert SERVICE_JWT not in kf.model_dump_json()


def test_findings_service_role_is_critical_anon_is_silent() -> None:
    keys = [key_finding(Candidate(ANON_JWT, "jwt"), "a.js"),
            key_finding(Candidate(SB_PUBLISHABLE, "sb_publishable"), "a.js"),
            key_finding(Candidate(SERVICE_JWT, "jwt"), "b.js"),
            key_finding(Candidate(SERVICE_JWT, "jwt"), "c.js"),
            key_finding(Candidate(SB_SECRET, "sb_secret"), "c.js"),
            key_finding(Candidate("AIzaSyQ7xT2mVb9KpL4zWc8RnJ5yHd3fGa6s1E", "generic"), "d.js")]
    fs = findings_from_keys(keys)
    assert [(f.target, f.rule) for f in fs] == [
        ("jwt:service_role", "SECRET_KEY_IN_BUNDLE"), ("sb_secret", "SECRET_KEY_IN_BUNDLE"),
        ("unverified", "UNVERIFIED_KEY")]
    secret = fs[0]
    assert (secret.evidence, secret.severity) == (Evidence.CONFIRMED, Severity.CRITICAL)
    assert secret.role is None and secret.op is None and secret.correlation is None
    assert secret.id == finding_id("jwt:service_role", None, None, "SECRET_KEY_IN_BUNDLE")
    assert (fs[2].evidence, fs[2].severity) == (Evidence.CONFIG_WARNING, Severity.LOW)


def test_findings_only_publishable_gives_nothing() -> None:
    keys = [key_finding(Candidate(ANON_JWT, "jwt"), "a.js"),
            key_finding(Candidate(SB_PUBLISHABLE, "sb_publishable"), "b.js")]
    assert findings_from_keys(keys) == []
