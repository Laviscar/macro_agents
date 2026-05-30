from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from presenters.briefing_presenter import build_briefing_overview
from presenters.challenges_presenter import build_challenges_overview
from presenters.timeline_presenter import build_narrative_timeline
from presenters.data_presenter import build_debug_payload, build_news_detail_view, build_news_list_items
from presenters.ingestion_presenter import build_ingestion_qa_overview
from presenters.operations_presenter import build_operations_overview
from presenters.research_presenter import build_research_overview
from repositories.news_repository import SQLiteNewsRepository
from view_models.ingestion_qa import IngestionQAOverview
from view_models.research_overview import MainNarrativeCard, ResearchOverview
from view_models.warehouse_detail import NewsDetailView, NewsListItem
from utils.dotenv import load_dotenv

load_dotenv()  # populate os.environ from .env on app startup (shell exports still win)


APP_ROOT = Path(__file__).resolve().parent
STORAGE_ROOT = APP_ROOT / "storage"
DEFAULT_DB_PATH = STORAGE_ROOT / "macro_agents.sqlite3"
DEFAULT_INGESTION_QA_REPORT = STORAGE_ROOT / "qa" / "ingestion_report.json"
STATUS_ORDER = ["pending_sort", "pending_analysis", "analyzed", "skipped", "error"]
RELATION_LABELS = {
    "supports": "支持当前主线",
    "raises_probability_of": "提高主线成立概率",
    "conflicts_with": "与当前主线冲突",
    "complicates": "让主线更脆弱/更复杂",
    "lowers_probability_of": "降低主线成立概率",
}
EVIDENCE_TYPE_LABELS = {
    "supports": "支持",
    "raises_probability_of": "强化",
    "conflicts_with": "冲突",
    "complicates": "扰动",
    "lowers_probability_of": "削弱",
}


def main() -> None:
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("streamlit is not installed. Add it to the environment before launching the UI.") from exc

    db_path = Path(os.environ.get("MACRO_AGENTS_DB_PATH", DEFAULT_DB_PATH))
    repository = SQLiteNewsRepository(db_path)
    briefing = build_briefing_overview(STORAGE_ROOT)
    timeline = build_narrative_timeline(STORAGE_ROOT)
    challenges = build_challenges_overview(STORAGE_ROOT)
    research = build_research_overview(STORAGE_ROOT)
    operations = build_operations_overview(repository, STORAGE_ROOT)
    ingestion_qa = build_ingestion_qa_overview(DEFAULT_INGESTION_QA_REPORT)
    data_rows = repository.list_news_items(limit=50)
    news_items = build_news_list_items(data_rows)

    st.set_page_config(page_title="Macro Agents Workbench", layout="wide")
    st.title("Macro Agents Research Workbench")
    st.caption("页面只负责展示；底层状态会先翻译成 view models，再交给 UI 渲染。")

    briefing_tab, narrative_tab, challenges_tab, workbench_tab, system_tab = st.tabs(
        ["今日叙事", "叙事", "分歧预警", "新闻工作台", "系统"]
    )

    with briefing_tab:
        _render_briefing_view(st, briefing)

    with narrative_tab:
        # 叙事页 = 演变时间线 + 当前主线（挑战分支独立到「分歧预警」页；后续再加 P4 溯源）
        _render_timeline_view(st, timeline)
        st.divider()
        _render_research_view(st, research)

    with challenges_tab:
        _render_challenges_view(st, challenges)

    with workbench_tab:
        _render_data_view(st, repository, news_items, data_rows)

    with system_tab:
        st.caption("系统运行视图：给开发/运维看，不是产品价值面。")
        health_tab, qa_tab = st.tabs(["运行健康", "抓取自检 (fixture)"])
        with health_tab:
            _render_operations_view(st, operations)
        with qa_tab:
            _render_ingestion_qa_view(st, ingestion_qa)


def _render_briefing_view(st: Any, b: Any) -> None:
    st.subheader("今日叙事 · Briefing")
    st.caption("一屏看懂：当前叙事怎么读、在往哪走、什么在动摇它。")

    if not b.available:
        st.info("还没有叙事数据。先跑 run_harness 处理一些待办新闻，这一页就有内容了。")
        st.code("python run_harness.py", language="bash")
        return

    # ① 当前叙事读数
    st.markdown(f"### {b.title}　`{b.status}`")
    if b.read_line:
        st.info(b.read_line)
    else:
        st.caption("（本轮还没有生成一句话读数——配好 LLM key 后由 run_harness 生成）")

    metric_col, conf_col, trend_col = st.columns([1, 1, 2])
    metric_col.metric(
        "强度 Strength",
        f"{round(b.strength * 100)}%",
        delta=f"{round(b.strength_delta * 100):+d} pts" if b.strength_delta is not None else None,
    )
    conf_col.metric(
        "置信 Confidence",
        f"{round(b.confidence * 100)}%",
        delta=f"{round(b.confidence_delta * 100):+d} pts" if b.confidence_delta is not None else None,
    )
    with trend_col:
        st.caption("强度走势")
        if len(b.strength_series) >= 2:
            st.line_chart(b.strength_series, height=140)
        else:
            st.caption("数据点不足，多处理几轮新闻后显示。")

    st.divider()

    # ② 最近发生了什么
    st.markdown("### 最近发生了什么")
    if not b.recent_changes:
        st.caption("暂无更新记录。")
    else:
        badges = {"强化": "🟢 强化", "削弱": "🔴 削弱", "挑战": "⚠️ 挑战", "中性": "⚪ 中性"}
        for change in b.recent_changes:
            st.markdown(
                f"- {badges.get(change.direction, change.direction)} · "
                f"`{_format_datetime(change.when)}` · {change.summary}"
            )

    st.divider()

    # ③ 最该警惕的分歧
    st.markdown("### 最该警惕的分歧")
    if not b.top_branches:
        st.caption("当前没有成型挑战分支。")
    else:
        for branch in b.top_branches:
            with st.container(border=True):
                st.markdown(f"**{branch.title}**　挑战概率 {round(branch.challenge_probability * 100)}%")
                st.progress(min(max(branch.challenge_probability, 0.0), 1.0))
                if branch.key_triggers:
                    st.caption("关键触发点：" + " · ".join(branch.key_triggers))


def _render_timeline_view(st: Any, t: Any) -> None:
    st.subheader("演变时间线 · Narrative Evolution")
    st.caption("主线强度/置信随时间怎么走，每一步是哪条更新推动的。")

    if not t.available:
        st.info("还没有可展示的演变历史。多跑几轮 run_harness 后，commit 历史会在这里累积成曲线。")
        st.code("python run_harness.py", language="bash")
        return

    st.markdown(f"### {t.title}　共 {t.total_commits} 次更新")

    if len(t.strength_series) >= 2:
        st.line_chart(
            {"强度 Strength": t.strength_series, "置信 Confidence": t.confidence_series},
            height=260,
        )
    else:
        st.caption("数据点不足（至少需要 2 次更新），继续处理新闻后显示曲线。")

    st.divider()
    st.markdown("### 关键节点（最近在前）")
    badges = {"强化": "🟢 强化", "削弱": "🔴 削弱", "挑战": "⚠️ 挑战", "中性": "⚪ 中性"}
    for point in t.points:
        with st.container(border=True):
            head = f"{badges.get(point.direction, point.direction)} · `{_format_datetime(point.when)}`"
            if point.evidence_count:
                head += f" · 证据 {point.evidence_count}"
            st.markdown(head)
            st.write(point.summary or "（无摘要）")
            if point.strength_from is not None and point.strength_to is not None:
                st.caption(
                    f"强度 {round(point.strength_from * 100)}% → {round(point.strength_to * 100)}%"
                    + (
                        f"　置信 {round(point.confidence_from * 100)}% → {round(point.confidence_to * 100)}%"
                        if point.confidence_from is not None and point.confidence_to is not None
                        else ""
                    )
                )


def _render_challenges_view(st: Any, c: Any) -> None:
    st.subheader("分歧预警 · Challenges & Alerts")
    st.caption("什么在动摇主线、概率多高、会走向哪个情景 —— 共识何时可能裂开。")

    if not c.available:
        st.info("当前没有挑战分支或预警。出现 conflicts/lowers 类证据时，这里会生成分支。")
        return

    st.info(c.headline)

    # 预警（高概率、已触发）
    st.markdown("### 🔔 预警")
    if not c.alerts:
        st.caption("当前没有触发级预警（挑战概率达到阈值才触发）。")
    else:
        for alert in c.alerts:
            st.error(
                f"**{alert.challenged_claim}**　挑战概率 {round(alert.challenge_probability * 100)}%"
                + (f"\n\n来源分支：{alert.branch_title}" if alert.branch_title else "")
                + (f"\n\n关键触发点：{' · '.join(alert.key_triggers)}" if alert.key_triggers else "")
            )

    # 全部挑战分支（按概率排序）
    st.markdown("### 挑战分支（按概率排序）")
    for item in c.challenges:
        with st.container(border=True):
            st.markdown(f"**{item.title}**　`{item.status}`　挑战概率 {round(item.challenge_probability * 100)}%")
            st.progress(min(max(item.challenge_probability, 0.0), 1.0))
            if item.core_claims:
                st.write("核心主张：" + "；".join(item.core_claims))
            if item.key_triggers:
                st.caption("关键触发点：" + " · ".join(item.key_triggers))
            st.caption(f"分支强度 {round(item.branch_strength * 100)}% · 支撑证据 {item.supporting_evidence_count} 条")
            if item.scenario is not None:
                s = item.scenario
                a_col, b_col = st.columns(2)
                a_col.metric(f"情景A · {s.scenario_a_name}", f"{round(s.scenario_a_prob * 100)}%")
                b_col.metric(f"情景B · {s.scenario_b_name}", f"{round(s.scenario_b_prob * 100)}%")


def _render_research_view(st: Any, overview: ResearchOverview) -> None:
    st.subheader("Research")
    st.caption("首页先回答：当前主线是什么、稳不稳、哪些因素在强化或挑战它。")

    if not overview.main_cards:
        st.info("当前还没有可展示的主线叙事。")
        return

    st.info(overview.global_headline)
    st.write(overview.global_summary)

    st.markdown("### Current Main Narratives")
    columns = st.columns(max(len(overview.main_cards), 1))
    for index, card in enumerate(overview.main_cards):
        with columns[index]:
            _render_main_narrative_card(st, card)

    lead_card = overview.main_cards[0]
    st.markdown("### Main Narrative Detail")
    left, right = st.columns([1.3, 1.0], gap="large")
    with left:
        _render_list_section(st, "强化因素", lead_card.reinforcing_factors, "当前还没有明显强化因素。")
        _render_list_section(st, "当前重点观察", lead_card.watch_items, "当前没有额外 watch items。")
    with right:
        _render_list_section(st, "脆弱点 / 复杂化因素", lead_card.fragility_factors, "当前没有明显复杂化因素。")
        st.markdown("### 主线摘要")
        st.write(lead_card.summary)

    if overview.challenge_branches:
        st.caption(f"⚔️ 当前有 {len(overview.challenge_branches)} 条挑战分支 —— 详见「分歧预警」页。")


def _render_operations_view(st: Any, overview: Any) -> None:
    st.subheader("Operations")
    st.caption("先看两个员工的工作状态，再看链路健康。")

    analyst_col, narrative_col = st.columns(2, gap="large")
    with analyst_col:
        st.markdown("### Analyst")
        cols = st.columns(3)
        cols[0].metric("已处理新闻", overview.analyst.processed_news_count)
        cols[1].metric("analysis", overview.analyst.analyzed_count)
        cols[2].metric("evidence", overview.analyst.evidence_generated_count)
        cols = st.columns(3)
        cols[0].metric("skipped", overview.analyst.skipped_count)
        cols[1].metric("error", overview.analyst.error_count)
        cols[2].metric("latest run", _format_datetime(overview.analyst.latest_run_at))
        st.write(overview.analyst.status_text)

    with narrative_col:
        st.markdown("### Narrative Manager")
        cols = st.columns(3)
        cols[0].metric("main updates", overview.narrative_manager.main_updates_count)
        cols[1].metric("branch updates", overview.narrative_manager.branch_updates_count)
        cols[2].metric("commits", overview.narrative_manager.commit_count)
        cols = st.columns(3)
        cols[0].metric("alerts", overview.narrative_manager.alert_count)
        cols[1].metric("latest run", _format_datetime(overview.narrative_manager.latest_run_at))
        cols[2].metric("pending", overview.pipeline_health.pending_sort_count + overview.pipeline_health.pending_analysis_count)
        st.write(overview.narrative_manager.status_text)

    st.markdown("### Pipeline Health")
    cols = st.columns(len(STATUS_ORDER))
    values = [
        overview.pipeline_health.pending_sort_count,
        overview.pipeline_health.pending_analysis_count,
        overview.pipeline_health.analyzed_count,
        overview.pipeline_health.skipped_count,
        overview.pipeline_health.error_count,
    ]
    for index, status in enumerate(STATUS_ORDER):
        cols[index].metric(status, values[index])
    st.caption(
        f"Latest fetch: {_format_datetime(overview.pipeline_health.latest_fetch_at)} | "
        f"Latest analysis: {_format_datetime(overview.pipeline_health.latest_analysis_at)}"
    )


def _render_data_view(
    st: Any,
    repository: SQLiteNewsRepository,
    news_items: list[NewsListItem],
    rows: list[dict],
) -> None:
    st.subheader("新闻工作台 · Workbench")
    st.caption("逐条看新闻原文 + 它的 analysis / evidence 明细,以及调试入口。")

    if not news_items:
        st.info("当前 SQLite 中还没有新闻记录。")
        return

    _initialize_selection(st, news_items)
    selected_item = next(item for item in news_items if item.news_item_id == st.session_state["selected_news_id"])
    selected_row = next(row for row in rows if int(row["id"]) == selected_item.news_item_id)
    detail = build_news_detail_view(repository, selected_row)
    debug_payload = build_debug_payload(repository, selected_row)

    left, right = st.columns([1.05, 1.7], gap="large")
    with left:
        st.markdown("### News / Warehouse")
        for item in news_items:
            with st.container(border=True):
                title_col, action_col = st.columns([5, 1])
                with title_col:
                    st.markdown(f"**{item.title}**")
                    st.caption(f"{item.source_name} | {_format_datetime(item.published_at)} | {item.analysis_status}")
                    st.write(item.summary)
                with action_col:
                    if st.button(
                        "查看",
                        key=f"select-news-{item.news_item_id}",
                        use_container_width=True,
                        type="primary" if item.news_item_id == selected_item.news_item_id else "secondary",
                    ):
                        st.session_state["selected_news_id"] = item.news_item_id
                        st.rerun()

    with right:
        _render_news_detail(st, detail)
        with st.expander("Debug / Raw JSON"):
            st.caption("需要排查字段或比对 schema 时再展开。")
            st.json(debug_payload)


def _render_ingestion_qa_view(st: Any, overview: IngestionQAOverview) -> None:
    st.subheader("Ingestion QA")
    st.warning("⚠️ 本页是**固定 fixture 的管道自检**(造的假源/假数据),**不是实时 Finnhub 数据**。真实新闻见「新闻工作台」。")
    st.caption("用刁难数据验证第一段链路：抓新闻、去重、清洗、容错、入库。")

    if not overview.report_available:
        st.info(overview.headline)
        st.write(overview.summary)
        st.code("python -m pipelines.ingestion_qa", language="bash")
        return

    st.info(overview.headline)
    st.write(overview.summary)
    if overview.generated_at:
        st.caption(f"Latest QA run: {_format_datetime(overview.generated_at)}")

    st.markdown("### Run Summary")
    cols = st.columns(6)
    cols[0].metric("sources", overview.run_summary.source_count)
    cols[1].metric("failed", overview.run_summary.failed_source_count)
    cols[2].metric("payloads", overview.run_summary.payload_seen_count)
    cols[3].metric("normalized", overview.run_summary.normalized_seen_count)
    cols[4].metric("inserted", overview.run_summary.inserted_count)
    cols[5].metric("deduped", overview.run_summary.deduped_count)
    st.caption(
        f"Enabled sources: {', '.join(overview.run_summary.enabled_sources)} | "
        f"invalid payloads: {overview.run_summary.invalid_payload_count}"
    )

    st.markdown("### Current Status Counts")
    cols = st.columns(5)
    cols[0].metric("pending_sort", overview.status_summary.pending_sort_count)
    cols[1].metric("pending_analysis", overview.status_summary.pending_analysis_count)
    cols[2].metric("analyzed", overview.status_summary.analyzed_count)
    cols[3].metric("skipped", overview.status_summary.skipped_count)
    cols[4].metric("error", overview.status_summary.error_count)

    st.markdown("### Cleaning Metrics")
    cols = st.columns(3)
    cols[0].metric("resource cards", overview.cleaning_summary.resource_card_count)
    cols[1].metric(
        "avg readiness",
        _format_confidence(overview.cleaning_summary.average_analysis_readiness_score or 0.0)
        if overview.cleaning_summary.average_analysis_readiness_score is not None
        else "n/a",
    )
    cols[2].metric("sources in DB", len(overview.cleaning_summary.source_distribution))
    st.write(
        "Route distribution: "
        + ", ".join(f"{route}={count}" for route, count in overview.cleaning_summary.route_distribution.items())
    )
    st.write(
        "Route percentages: "
        + ", ".join(
            f"{route}={_format_confidence(value)}" for route, value in overview.cleaning_summary.route_percentages.items()
        )
    )
    if overview.cleaning_summary.latest_titles:
        _render_list_section(st, "Latest Titles", overview.cleaning_summary.latest_titles, "暂无样本标题。")

    st.markdown("### Source Results")
    for source_run in overview.source_runs:
        with st.container(border=True):
            st.markdown(f"**{source_run.source_name}**")
            st.write(
                f"type={source_run.source_type} | payloads={source_run.payload_seen_count} | "
                f"normalized={source_run.normalized_seen_count} | inserted={source_run.inserted_count} | "
                f"deduped={source_run.deduped_count} | invalid={source_run.invalid_payload_count}"
            )
            if source_run.failed:
                st.warning(source_run.error_message or "source failed")
            else:
                st.caption("This source completed successfully.")

    st.markdown("### Sample Comparison")
    if not overview.samples:
        st.info("当前还没有 QA 样本。")
    else:
        for sample in overview.samples:
            with st.container(border=True):
                st.markdown(f"**{sample.title}**")
                st.caption(f"{sample.source_name} | status={sample.analysis_status}")
                left, middle, right = st.columns(3, gap="large")
                with left:
                    st.markdown("**Raw News**")
                    st.json(sample.raw_news)
                with middle:
                    st.markdown("**ResourceCard**")
                    if sample.resource_card is None:
                        st.caption("尚未生成 ResourceCard。")
                    else:
                        st.json(sample.resource_card)
                with right:
                    st.markdown("**Current DB Status**")
                    st.write(f"news_item_id: {sample.news_item_id}")
                    st.write(f"analysis_status: {sample.analysis_status}")
                    if sample.resource_card is not None:
                        st.write(f"route_decision: {sample.resource_card.get('route_decision', 'n/a')}")
                        st.write(
                            f"analysis_readiness_score: "
                            f"{_format_confidence(float(sample.resource_card.get('analysis_readiness_score', 0.0)))}"
                        )

    st.markdown("### Exceptions")
    if overview.failures:
        for failure in overview.failures:
            st.error(f"{failure.source_name}: {failure.error_message}")
    else:
        st.caption("没有 source 级失败。")

    st.markdown("### Bad Payloads")
    if not overview.bad_payloads:
        st.caption("没有发现坏 payload。")
    else:
        for item in overview.bad_payloads:
            with st.container(border=True):
                st.markdown(f"**{item.source_name}**")
                st.write(item.reason)
                st.json(item.payload)


def _render_main_narrative_card(st: Any, card: MainNarrativeCard) -> None:
    with st.container(border=True):
        st.markdown(f"**{card.title}**")
        st.write(f"状态：{card.status}")
        st.write(card.headline)
        st.caption(
            f"strength {_format_confidence(card.strength)} | confidence {_format_confidence(card.confidence)} | "
            f"challenge branches {card.challenge_count}"
        )


def _render_news_detail(st: Any, detail: NewsDetailView) -> None:
    st.markdown("### News Detail")
    st.markdown(f"**{detail.news.title}**")
    st.caption(f"{detail.news.source_name} | {_format_datetime(detail.news.published_at)}")
    st.write(detail.news.summary)

    st.markdown("### Analysis")
    if detail.analysis is None:
        st.info("这条新闻还没有生成 Analyst 结论。")
    else:
        st.markdown(f"**结论摘要**\n\n{detail.analysis.thesis}")
        st.markdown(
            f"- 主线关系：{RELATION_LABELS.get(detail.analysis.mainline_relation, detail.analysis.mainline_relation)}\n"
            f"- 置信度：{_format_confidence(detail.analysis.confidence)}（{_confidence_bucket(detail.analysis.confidence)}）"
        )

    st.markdown("### Evidence")
    if not detail.evidence_items:
        st.info("这条新闻还没有生成 Evidence。")
    else:
        for evidence in detail.evidence_items:
            with st.container(border=True):
                st.markdown(f"**证据结论**\n\n{evidence.claim}")
                st.markdown(f"- 证据类型：{EVIDENCE_TYPE_LABELS.get(evidence.relation_type, evidence.relation_type)}")
                st.markdown(f"**为什么这么判断**\n\n{evidence.why}")
                st.markdown("**反证情况**")
                if evidence.counter_evidence:
                    for item in evidence.counter_evidence:
                        st.write(f"- {item}")
                else:
                    st.write("目前没有显式反证。")


def _render_list_section(st: Any, title: str, items: list[str], empty_message: str) -> None:
    st.markdown(f"### {title}")
    if not items:
        st.caption(empty_message)
        return
    for item in items:
        st.write(f"- {item}")


def _initialize_selection(st: Any, news_items: list[NewsListItem]) -> None:
    current_ids = [item.news_item_id for item in news_items]
    if "selected_news_id" not in st.session_state or st.session_state["selected_news_id"] not in current_ids:
        st.session_state["selected_news_id"] = news_items[0].news_item_id


def _format_datetime(value: str | None) -> str:
    if not value:
        return "unknown time"
    normalized = value.replace("T", " ")
    return normalized[:16]


def _format_confidence(value: float) -> str:
    return f"{round(value * 100)}%"


def _confidence_bucket(value: float) -> str:
    if value >= 0.8:
        return "高"
    if value >= 0.55:
        return "中等"
    return "较低"


if __name__ == "__main__":  # pragma: no cover
    main()
