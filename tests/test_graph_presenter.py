import json
from pathlib import Path

from presenters.graph_presenter import build_graph_view, export_graph_json
from repositories.graph_repository import GraphRepository

CONFIG = str(Path(__file__).resolve().parent.parent / "config")


def _repo(tmp_path):
    r = GraphRepository(tmp_path, CONFIG)
    r.seed_if_empty()
    return r


def test_build_view_seeds_and_includes_gold(tmp_path):
    repo = GraphRepository(tmp_path, CONFIG)  # not seeded yet
    view = build_graph_view(repo)
    ids = {n.id for n in view.nodes}
    assert "GOLD" in ids and "实际利率" in ids       # seeded on demand
    assert any(e.dst == "GOLD" and e.driver_label == "实际利率" for e in view.edges)


def test_dominant_edge_marked(tmp_path):
    repo = _repo(tmp_path)
    view = build_graph_view(repo)
    gold_dom = [e for e in view.edges if e.dst == "GOLD" and e.is_dominant]
    assert len(gold_dom) == 1 and gold_dom[0].driver_label == "实际利率"  # 0.6 seed prior wins


def test_focus_restricts_to_neighborhood(tmp_path):
    repo = _repo(tmp_path)
    view = build_graph_view(repo, focus="GOLD")
    ids = {n.id for n in view.nodes}
    assert "GOLD" in ids and "实际利率" in ids
    assert "NVDA" not in ids                          # unrelated node excluded


def test_layer_filter(tmp_path):
    repo = _repo(tmp_path)
    view = build_graph_view(repo, layer="anchor")
    assert view.nodes and all(n.layer == "anchor" for n in view.nodes)


def test_dormant_hidden_by_default(tmp_path):
    repo = _repo(tmp_path)
    nvda = repo.get_node("NVDA")
    nvda.status = "dormant"
    repo.save_node(nvda)
    assert "NVDA" not in {n.id for n in build_graph_view(repo).nodes}
    assert "NVDA" in {n.id for n in build_graph_view(repo, include_dormant=True).nodes}


def test_export_json_contract(tmp_path):
    repo = _repo(tmp_path)
    out = tmp_path / "graph_export.json"
    export_graph_json(repo, out)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert "nodes" in doc and "edges" in doc
    assert any(n["id"] == "GOLD" for n in doc["nodes"])


def test_graph_to_dot_renders(tmp_path):
    from presenters.graph_presenter import graph_to_dot
    repo = _repo(tmp_path)
    dot = graph_to_dot(build_graph_view(repo, focus="GOLD"))
    assert dot.startswith("digraph G {") and dot.rstrip().endswith("}")
    assert '"GOLD"' in dot and '"实际利率" -> "GOLD"' in dot
