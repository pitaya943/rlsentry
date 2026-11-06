"""MS5 approval note 4 (ADR-038): JWTs whose role bypasses RLS are secret keys → Critical.

The set is measured (lab: roles with rolsuper or rolbypassrls), not guessed; `authenticated`
stays unverified (a human judges) and `anon` stays publishable with no finding at all.
"""
from __future__ import annotations

import pytest

from rlsentry.contracts.models import Evidence, KeyFinding, Severity, finding_id
from rlsentry.contracts.recon import SECRET_JWT_ROLES, Candidate
from rlsentry.recon.classify import classify_key, findings_from_keys, key_finding
from tests.recon.helpers import make_jwt

PRIVILEGED = ["service_role", "supabase_admin", "postgres", "supabase_etl_admin",
              "supabase_read_only_user"]


def test_the_measured_set_is_exactly_the_contract() -> None:
    assert set(PRIVILEGED) == SECRET_JWT_ROLES


@pytest.mark.parametrize("role", PRIVILEGED)
def test_privileged_role_is_a_critical_confirmed_secret(role: str) -> None:
    tok = make_jwt({"role": role, "ref": "abcdefghijklmnopqrst", "exp": 2000000000})
    kind, label, _ = classify_key(Candidate(tok, "jwt"))
    assert (kind, label) == ("secret", f"jwt:{role}")
    [f] = findings_from_keys([key_finding(Candidate(tok, "jwt"), "app.js")])
    assert (f.rule, f.evidence, f.severity) == ("SECRET_KEY_IN_BUNDLE", Evidence.CONFIRMED,
                                                Severity.CRITICAL)
    assert f.target == f"jwt:{role}" and f.id == finding_id(f"jwt:{role}", None, None, f.rule)
    assert tok not in f.model_dump_json()


def test_authenticated_stays_unverified_and_anon_stays_silent() -> None:
    auth = make_jwt({"role": "authenticated", "ref": "abcdefghijklmnopqrst"})
    anon = make_jwt({"role": "anon", "ref": "abcdefghijklmnopqrst"})
    keys = [key_finding(Candidate(anon, "jwt"), "a.js"), key_finding(Candidate(auth, "jwt"), "a.js")]
    assert [k.kind for k in keys] == ["publishable", "unverified"]
    fs = findings_from_keys(keys)
    assert [(f.target, f.rule, f.severity) for f in fs] == [
        ("jwt:authenticated", "UNVERIFIED_KEY", Severity.LOW)]


def test_lookalike_roles_are_not_privileged() -> None:
    # exact match only: a prefix or a different case is "unverified", never silently secret
    for role in ("supabase_admin_x", "postgres_ro", "service"):
        kind, label, _ = classify_key(Candidate(make_jwt({"role": role}), "jwt"))
        assert (kind, label) == ("unverified", f"jwt:{role}")


def test_report_model_rejects_a_privileged_label_marked_unverified() -> None:
    with pytest.raises(ValueError):
        KeyFinding(kind="unverified", label="jwt:supabase_admin", masked="eyJhbG****abcd",
                   source_file="a.js")
    KeyFinding(kind="secret", label="jwt:supabase_admin", masked="eyJhbG****abcd", source_file="a.js")
