from streamlit_app import _initialize_selection
from view_models.warehouse_detail import NewsListItem


class FakeSt:
    def __init__(self):
        self.session_state = {}


def _item(nid, status):
    return NewsListItem(news_item_id=nid, title=f"t{nid}", source_name="s",
                        published_at="2026-05-30T10:00:00Z", summary="x", analysis_status=status)


def test_defaults_to_first_analyzed_item():
    st = FakeSt()
    items = [_item(402, "pending_sort"), _item(401, "pending_sort"), _item(343, "analyzed")]
    _initialize_selection(st, items)
    assert st.session_state["selected_news_id"] == 343  # analyzed, not the newest pending


def test_falls_back_to_first_when_none_analyzed():
    st = FakeSt()
    items = [_item(402, "pending_sort"), _item(401, "skipped")]
    _initialize_selection(st, items)
    assert st.session_state["selected_news_id"] == 402


def test_keeps_valid_existing_selection():
    st = FakeSt()
    st.session_state["selected_news_id"] = 401
    items = [_item(402, "analyzed"), _item(401, "pending_sort")]
    _initialize_selection(st, items)
    assert st.session_state["selected_news_id"] == 401  # respected, not overridden
