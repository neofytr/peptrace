import json
import tempfile
from pathlib import Path

from peptrace.build import build
from peptrace.graph import Graph
from peptrace.reason import Reasoner, profile

DATA = Path(__file__).resolve().parent.parent / "data" / "peps"
G = build(DATA)
R = Reasoner(G)


def alts_of(num):
    return {G.nodes[e["dst"]]["title"]: e["dst"] for e in G.out(f"pep:{num}", "rejected")}


def test_graph_shape():
    counts = {}
    for v in G.nodes.values():
        counts[v["type"]] = counts.get(v["type"], 0) + 1
    assert counts["pep"] >= 40
    assert counts["alternative"] >= 150
    assert counts["person"] >= 30
    for e in G.edges:
        assert e["src"] in G.nodes and e["dst"] in G.nodes


def test_header_relations_become_edges():
    assert {e["dst"] for e in G.out("pep:563", "superseded_by")} == {"pep:649", "pep:749"}
    assert [e["dst"] for e in G.out("pep:742", "replaces")] == ["pep:724"]
    assert [e["dst"] for e in G.out("pep:749", "requires")] == ["pep:649"]


def test_feature_ownership():
    assert "feature:TypeGuard" in {e["dst"] for e in G.out("pep:647", "introduces")}
    # 742 talks about TypeGuard a lot but did not introduce it
    assert "feature:TypeGuard" in {e["dst"] for e in G.out("pep:742", "uses")}
    assert "feature:TypeGuard" not in {e["dst"] for e in G.out("pep:742", "introduces")}


def test_rejected_idea_extraction_and_reasons():
    alts = alts_of(647)
    assert "Decorator Syntax" in alts
    reasons = {e["dst"] for e in G.out(alts["Decorator Syntax"], "because")}
    assert "reason:runtime_cost" in reasons
    assert "Angle Brackets" in alts_of(695)
    # numbered headings lose their number, backticks are gone
    assert any(t.startswith("Add a new operator for Union") for t in alts_of(604))


def test_concepts_are_about_the_right_thing():
    top = max(G.out("pep:647", "about"), key=lambda e: e["salience"])["dst"]
    assert top == "concept:narrowing"
    top = max(G.out("pep:563", "about"), key=lambda e: e["salience"])["dst"]
    assert top == "concept:annotation_evaluation"


def test_profile_reads_names_case_sensitively():
    p = profile("TypeGuard and Self are names, self and guard are not")
    assert "TypeGuard" in p["features"] and "Self" in p["features"]
    assert p["peps_named"] == []
    assert profile("see PEP 484 and pep-526")["peps_named"] == [484, 526]


def test_ask_decorator_for_type_guards():
    res = R.ask("a decorator @typeguard(T) that marks a function as narrowing its first argument to T "
                "instead of a TypeGuard return annotation")
    assert res["prior_art"][0]["pep"] == 647
    assert res["rejected_before"][0]["idea"] == "Decorator Syntax"
    assert res["likely_objections"], "should surface reasons from the matched ideas"
    assert any(row["pep"] == 724 and row.get("replaced_by") == [742] for row in res["lineage"])


def test_ask_recognises_a_rejected_idea():
    res = R.ask("generic classes should use angle brackets like class Foo<T>: instead of square brackets")
    assert res["verdict"]["label"] == "considered_before"
    assert res["rejected_before"][0]["pep"] == 695
    assert res["rejected_before"][0]["idea"] == "Angle Brackets"


def test_ask_recognises_a_dead_pep():
    res = R.ask("callable type syntax like (int, str) -> bool instead of Callable[[int, str], bool]")
    assert res["prior_art"][0]["pep"] == 677
    assert res["verdict"]["label"] == "overlaps_dead_pep"


def test_ask_recognises_in_flight_work():
    res = R.ask('a typed dict literal like {"a": int} directly in an annotation instead of a TypedDict class')
    assert res["verdict"]["label"] == "in_flight"
    assert 764 in [p["pep"] for p in res["prior_art"][:2]]


def test_ask_handles_nonsense():
    res = R.ask("bananas are yellow")
    assert res["verdict"]["label"] in ("uncharted", "thin_prior_art")
    assert res["rejected_before"] == [] or res["rejected_before"][0]["score"] < 4


def test_json_round_trip():
    d = Path(tempfile.mkdtemp())
    G.to_json(d / "g.json")
    G.to_graphml(d / "g.graphml")
    g2 = Graph.from_json(d / "g.json")
    assert len(g2.nodes) == len(G.nodes) and len(g2.edges) == len(G.edges)
    assert g2.nodes["pep:647"]["title"] == G.nodes["pep:647"]["title"]
    doc = json.loads((d / "g.json").read_text())
    assert doc["meta"]["counts"]["nodes.pep"] == len([1 for v in G.nodes.values() if v["type"] == "pep"])
    assert (d / "g.graphml").read_text().count("<node ") == len(G.nodes)
