"""discovery/bundle.py (FR-05). Contract: rlsentry/contracts/discovery.py; ADR-023 #2."""
from rlsentry.contracts.models import Target
from rlsentry.discovery.bundle import infer_from_bundle


def t(name: str, kind: str = "table") -> Target:
    return Target(name=name, kind=kind, discovered_by="bundle", confidence="inferred")


def test_from_and_rpc_with_each_quote_style() -> None:
    src = """const a = await supabase.from('todos').select('*');
    sb.from("notes").select(); x.rpc('get_all', {}); y.from(`diary`).insert(r)"""
    assert infer_from_bundle([src]) == [t("diary"), t("get_all", "rpc"), t("notes"), t("todos")]


def test_minified_receivers_and_whitespace() -> None:
    src = 'e.from("a").select("id"),(0,n.default)(r).from( \'b\' ),A . from("c");q.rpc("f")'
    assert [x.name for x in infer_from_bundle([src])] == ["a", "b", "c", "f"]


def test_storage_and_builtins_are_not_tables() -> None:
    src = """supabase.storage.from('avatars').upload(p); e.storage.from("docs");
    Array.from('abc'); Buffer.from("hello"); Uint8Array.from('x'); s.from('real_table')"""
    assert infer_from_bundle([src]) == [t("real_table")]


def test_variables_and_odd_names_are_ignored() -> None:
    src = """s.from(name); s.from('a-b'); s.from('public.x'); s.from('x' + y); s.rpc(fn);
    s.from(''); s.from('ok')"""
    assert infer_from_bundle([src]) == [t("ok")]


def test_deduplicated_across_sources_and_kinds_kept_apart() -> None:
    got = infer_from_bundle(["s.from('x')", "s.from('x'); s.rpc('x')", "s.rpc('x')"])
    assert got == [t("x", "rpc"), t("x")]


def test_empty_input() -> None:
    assert infer_from_bundle([]) == [] and infer_from_bundle(["no calls here"]) == []
