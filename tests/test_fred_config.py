import yaml
from pathlib import Path


def test_fred_series_structure_and_node_refs():
    cfg = yaml.safe_load((Path("config") / "fred_series.yaml").read_text(encoding="utf-8"))["series"]
    ids = [s["series_id"] for s in cfg]
    assert len(ids) == len(set(ids)) == 13
    mapped = [s for s in cfg if s.get("node_id")]
    assert len(mapped) == 9
    asset_cfg = yaml.safe_load((Path("config") / "narrative_assets.yaml").read_text(encoding="utf-8"))["assets"]
    vocab = yaml.safe_load((Path("config") / "driver_vocabulary.yaml").read_text(encoding="utf-8"))["factors"]
    known = {a["id"] for a in asset_cfg} | set(vocab)
    for s in mapped:
        assert s["node_id"] in known, s["node_id"]
