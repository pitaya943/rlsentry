"""bench.score.score_scenario / splinter_status / lint_labels (SPEC §9; ADR-011, ADR-033). Pure."""
from __future__ import annotations

from rlsentry.bench.score import lint_labels, score_scenario, splinter_status
from rlsentry.contracts.ground_truth import ScenarioResult
from rlsentry.contracts.models import AccessMatrix, Evidence, Op, Outcome, Profile, Role
from tests.bench.helpers import cell, fnd, gt, lint, matrix

A, B, ANON = Role.USER_A, Role.USER_B, Role.ANON
S, I, U, D = Op.SELECT, Op.INSERT, Op.UPDATE, Op.DELETE
AL, DE, IN, NT = Outcome.ALLOWED, Outcome.DENIED, Outcome.INCONCLUSIVE, Outcome.NOT_TESTED


def verdicts(res: ScenarioResult) -> dict[str, str]:
    return {c.case_id: c.verdict for c in res.cases}


def l04_matrix() -> AccessMatrix:
    return matrix(cell("notes", B, S, AL), cell("notes", A, S, AL), cell("notes", ANON, S, DE),
                  cell("notes", B, U, DE), cell("notes", A, D, DE), cell("notes", ANON, I, DE),
                  cell("notes", B, I, DE))


def test_perfect_l04_in_dev() -> None:
    fs = [fnd("notes", B, S, "CROSS_TENANT_READ", correlation="probe_only"),
          fnd("notes", A, S, "CROSS_TENANT_READ", correlation="probe_only")]
    res = score_scenario(gt("L04"), Profile.DEV, l04_matrix(), fs, 1.5)
    assert verdicts(res) == {"L04-V1": "tp", "L04-V2": "tp", "L04-S1": "tn", "L04-S2": "tn",
                             "L04-S3": "tn", "L04-S4": "tn", "L04-S5": "tn"}
    assert res.unmatched_findings == [] and res.scored and res.profile is Profile.DEV
    assert (res.cells_total, res.cells_tested, res.cells_inconclusive) == (7, 7, 0)
    assert (res.safe_denied_total, res.safe_denied_decided) == (5, 5)
    assert res.probe_only == ["L04-V1", "L04-V2"] and res.runtime_s == 1.5
    assert res.splinter is None and res.splinter_lints == [] and res.splinter_match is None


def test_audit_scores_only_cases_listing_audit() -> None:
    res = score_scenario(gt("L04"), Profile.AUDIT, l04_matrix(), [], 0.1, db_writes=0)
    assert set(verdicts(res)) == {"L04-V1", "L04-V2", "L04-S1"}     # write cases are dev/ci only
    assert verdicts(res)["L04-V1"] == "fn" and res.db_writes == 0
    assert res.cells_total == 3


def test_match_requires_rule_role_op_and_confirmed() -> None:
    wrong = [fnd("notes", B, S, "ANON_READ_OWNER_SCOPED"),                    # wrong rule
             fnd("notes", A, S, "CROSS_TENANT_READ", evidence=Evidence.SUSPECTED),  # not proven
             fnd("notes", B, U, "CROSS_TENANT_READ")]                          # wrong op
    res = score_scenario(gt("L04"), Profile.DEV, l04_matrix(), wrong, 0.0)
    v = verdicts(res)
    assert v["L04-V1"] == "fn" and v["L04-V2"] == "fn"
    assert "allowed" in {c.case_id: c.detail for c in res.cases}["L04-V1"]
    # proven findings matching no case are FPs (the suspected one is not proven)
    assert sorted(res.unmatched_findings) == sorted([wrong[0].id, wrong[2].id])
    assert v["L04-S2"] == "fp"          # a proven finding sits on safe cell (notes, user_b, update)


def test_non_vulnerability_rules_never_count() -> None:
    fs = [fnd("notes", ANON, S, "INCONCLUSIVE_CELL"), fnd("notes", ANON, S, "LINT_ONLY", correlation="lint_only")]
    res = score_scenario(gt("L04"), Profile.DEV, l04_matrix(), fs, 0.0)
    assert res.unmatched_findings == [] and verdicts(res)["L04-S1"] == "tn"


def test_inconclusive_cases_c03() -> None:
    m = matrix(cell("announcements", ANON, S, IN), cell("announcements", A, S, DE),
               cell("announcements", ANON, I, DE), cell("announcements", A, I, DE))
    res = score_scenario(gt("C03"), Profile.DEV, m, [], 0.0)
    v = verdicts(res)
    assert v["C03-I1"] == "inconclusive_ok"
    assert v["C03-I2"] == "inconclusive_violation"     # denied reported where nothing is knowable
    assert v["C03-I3"] == "inconclusive_violation"     # no cell at all
    assert {c.case_id: c.detail for c in res.cases}["C03-I3"] == "no cell"
    assert (res.cells_total, res.cells_tested, res.cells_inconclusive) == (5, 4, 1)


def test_not_tested_cell_is_not_coverage() -> None:
    m = matrix(cell("notes", B, S, NT), cell("notes", A, S, AL), cell("notes", ANON, S, DE))
    res = score_scenario(gt("L04"), Profile.AUDIT, m, [], 0.0)
    assert (res.cells_total, res.cells_tested) == (3, 2)


def test_warning_cases_l07() -> None:
    warn = fnd("ping_definer", ANON, S, "SECURITY_DEFINER_EXECUTABLE", correlation="lint_only")
    m = matrix(cell("ping_definer", ANON, S, IN))
    seen = score_scenario(gt("L07"), Profile.AUDIT, m, [warn], 0.0)
    assert verdicts(seen)["L07-W1"] == "warning_seen" and verdicts(seen)["L07-I1"] == "inconclusive_ok"
    other_role = fnd("ping_definer", None, S, "SECURITY_DEFINER_EXECUTABLE")
    missing = score_scenario(gt("L07"), Profile.AUDIT, m, [other_role], 0.0)
    assert verdicts(missing)["L07-W1"] == "warning_missing"


def test_key_case_matches_on_target_label_and_rule() -> None:
    ok = fnd("jwt:service_role", None, None, "SECRET_KEY_IN_BUNDLE")
    anon_key = fnd("jwt:anon", None, None, "SECRET_KEY_IN_BUNDLE")
    g = gt("L08")
    assert verdicts(score_scenario(g, Profile.DEV, matrix(), [ok], 0.0))["L08-V1"] == "tp"
    r = score_scenario(g, Profile.DEV, matrix(), [anon_key], 0.0)
    assert verdicts(r)["L08-V1"] == "fn" and r.unmatched_findings == [anon_key.id]
    assert {c.case_id: c.detail for c in r.cases}["L08-V1"] == "no finding"


def test_p2_is_not_scored() -> None:
    assert score_scenario(gt("L11"), Profile.DEV, matrix(), [], 0.0).scored is False


def test_splinter_fields() -> None:
    lints = [lint("rls_disabled_in_public", "customers"), lint("auth_rls_initplan", "customers", "PERFORMANCE")]
    g = gt("L01")
    assert splinter_status(g, lints) == "reported"
    assert lint_labels(lints) == ["rls_disabled_in_public:customers"]
    assert lint_labels([lint("extension_in_public", None)]) == ["extension_in_public:"]
    r = score_scenario(g, Profile.DEV, matrix(), [], 0.0, lints=lints)
    assert (r.splinter, r.splinter_lints, r.splinter_match) == ("reported", ["rls_disabled_in_public:customers"], None)
    r2 = score_scenario(gt("L01", splinter_expected="not_reported"), Profile.DEV, matrix(), [], 0.0, lints=lints)
    assert r2.splinter_match is False
    r3 = score_scenario(gt("L01", splinter_expected="not_reported"), Profile.DEV, matrix(), [], 0.0, lints=[])
    assert (r3.splinter, r3.splinter_match) == ("not_reported", True)


def test_splinter_status_only_counts_vulnerable_targets() -> None:
    assert splinter_status(gt("L12"), [lint("rls_enabled_no_policy", "audit_log")]) == "not_reported"
    assert splinter_status(gt("C01"), [lint("rls_disabled_in_public", "todos")]) == "not_reported"
    assert splinter_status(gt("L07"), [lint("anon_security_definer_function_executable", "get_all_accounts")]) == "reported"


def test_probe_only_uses_first_matching_finding() -> None:
    first = fnd("notes", B, S, "CROSS_TENANT_READ", correlation="confirmed")
    second = first.model_copy(update={"correlation": "probe_only"})
    res = score_scenario(gt("L04"), Profile.DEV, l04_matrix(), [first, second], 0.0)
    assert res.probe_only == []
