import yaml
from pathlib import Path

CFG = Path("config")


def _load(name):
    return yaml.safe_load((CFG / name).read_text(encoding="utf-8"))


def test_assets_count_and_layers():
    assets = _load("narrative_assets.yaml")["assets"]
    by = lambda L: [a for a in assets if a["layer"] == L]
    assert len(by("anchor")) == 8
    assert len(by("asset_class")) == 13
    assert len(by("theme")) == 20
    assert all(a["resident"] for a in by("anchor") + by("asset_class"))
    assert all(not a["resident"] for a in by("theme"))


def test_asset_ids_unique():
    ids = [a["id"] for a in _load("narrative_assets.yaml")["assets"]]
    assert len(ids) == len(set(ids))


def test_seed_edges_reference_known_nodes_and_vocab():
    vocab = set(_load("driver_vocabulary.yaml")["factors"])
    asset_ids = {a["id"] for a in _load("narrative_assets.yaml")["assets"]}
    nodes = asset_ids | vocab
    edges = _load("transmission_seed.yaml")["edges"]
    assert edges, "seed graph must not be empty"
    for e in edges:
        assert e["dst"] in asset_ids, f"dst {e['dst']} not an asset"
        assert e["src"] in nodes, f"src {e['src']} unknown"
        assert e["driver_label"] in vocab, f"driver {e['driver_label']} not in vocab"
        assert e["sign"] in (1, -1)
        assert 0.0 <= e["init_weight"] <= 1.0


def test_no_duplicate_driver_into_same_node():
    # 同一资产不应有两条相同 driver_label 的入边,否则该驱动被重复计数
    edges = _load("transmission_seed.yaml")["edges"]
    seen = {}
    for e in edges:
        key = (e["dst"], e["driver_label"])
        seen.setdefault(key, []).append(e["src"])
    dups = {k: v for k, v in seen.items() if len(v) > 1}
    assert not dups, f"duplicate (dst, driver) edges: {dups}"


def test_gold_has_competing_drivers():
    edges = _load("transmission_seed.yaml")["edges"]
    gold_drivers = {e["driver_label"] for e in edges if e["dst"] == "GOLD"}
    assert {"实际利率", "央行购金"} <= gold_drivers  # 用户的"黄金驱动切换"例子要有 ≥2 候选
