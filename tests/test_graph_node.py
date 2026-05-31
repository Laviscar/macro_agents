from schemas.graph_node import GraphNode


def test_asset_node_defaults():
    n = GraphNode(id="GOLD", kind="asset", name="黄金", layer="asset_class", ticker="XAUUSD", resident=True)
    assert n.strength == 0.5 and n.confidence == 0.5 and n.status == "active"
    assert n.dominant_driver is None and n.tags_countries == [] and n.tags_regime is None


def test_factor_node():
    n = GraphNode(id="实际利率", kind="factor", name="实际利率", layer="factor")
    assert n.ticker is None and n.kind == "factor" and n.resident is False


def test_roundtrip_json():
    n = GraphNode(id="NVDA", kind="asset", name="NVIDIA", layer="theme", ticker="NVDA",
                  strength=0.7, dominant_driver="AI资本开支")
    again = GraphNode.model_validate_json(n.model_dump_json())
    assert again.dominant_driver == "AI资本开支" and again.strength == 0.7
