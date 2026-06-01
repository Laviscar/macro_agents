from graph.driver_shift import contested, detect_shift, dominant_edge
from schemas.graph_edge import GraphEdge


def _e(label, w):
    e = GraphEdge(id=f"{label}->G", src=label, dst="G", sign=1, driver_label=label)
    e.weight = w
    return e


# --- dominant_edge ---
def test_picks_max_weight():
    d = dominant_edge([_e("实际利率", 0.6), _e("央行购金", 0.3)], min_weight=0.15)
    assert d.driver_label == "实际利率"


def test_none_below_threshold():
    assert dominant_edge([_e("实际利率", 0.1)], min_weight=0.15) is None


def test_none_when_no_edges():
    assert dominant_edge([], min_weight=0.15) is None


# --- detect_shift ---
def test_shift_emitted_on_identity_change():
    s = detect_shift("GOLD", "实际利率", "央行购金", "2026-06-01T00:00:00Z")
    assert s is not None and s.from_driver == "实际利率" and s.to_driver == "央行购金"


def test_no_shift_when_same():
    assert detect_shift("GOLD", "实际利率", "实际利率", "t") is None


def test_no_shift_from_none_first_time():
    assert detect_shift("GOLD", None, "实际利率", "t") is None


def test_no_shift_to_none():
    assert detect_shift("GOLD", "实际利率", None, "t") is None


# --- contested ---
def test_contested_when_runner_up_close():
    assert contested([_e("实际利率", 0.42), _e("央行购金", 0.40)], gap=0.10) is True


def test_not_contested_when_clear_lead():
    assert contested([_e("实际利率", 0.6), _e("央行购金", 0.2)], gap=0.10) is False


def test_not_contested_single_edge():
    assert contested([_e("实际利率", 0.6)], gap=0.10) is False
