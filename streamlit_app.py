from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from presenters.data_presenter import build_debug_payload, build_news_detail_view, build_news_list_items
from presenters.graph_presenter import build_graph_view, graph_to_dot, node_shift_history
from presenters.ingestion_presenter import build_ingestion_qa_overview
from presenters.operations_presenter import build_operations_overview
from presenters.committee_presenter import build_committee_view, estimate_calls
from presenters.today_presenter import build_allocation_overview, build_shifts_view, build_today_view
from repositories.committee_repository import CommitteeRepository
from repositories.graph_repository import GraphRepository
from repositories.news_repository import SQLiteNewsRepository
from view_models.ingestion_qa import IngestionQAOverview
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
    graph_repo = GraphRepository(storage_root=STORAGE_ROOT, config_dir=str(APP_ROOT / "config"))
    committee_repo = CommitteeRepository(storage_root=STORAGE_ROOT, config_dir=str(APP_ROOT / "config"))
    today = build_today_view(graph_repo, committee_repo=committee_repo)
    shifts = build_shifts_view(graph_repo)
    operations = build_operations_overview(repository, STORAGE_ROOT)
    ingestion_qa = build_ingestion_qa_overview(DEFAULT_INGESTION_QA_REPORT)
    data_rows = repository.list_news_items(limit=50)
    news_items = build_news_list_items(data_rows)

    st.set_page_config(page_title="Macro Agents Workbench", layout="wide")
    st.title("Macro Agents Research Workbench")
    st.caption("叙事驱动图 (v1.6)：每个资产是一条由驱动因子组成的叙事;最强入边=主导驱动,变了=驱动切换。")

    today_tab, tree_tab, shifts_tab, committee_tab, workbench_tab, system_tab = st.tabs(
        ["今日叙事", "世界树", "分歧预警", "叙事委员会", "新闻工作台", "系统"]
    )

    with today_tab:
        _render_today_view(st, today)
        st.divider()
        _render_allocation_overview(st, build_allocation_overview(graph_repo))

    with tree_tab:
        _render_world_tree(st, graph_repo)

    with shifts_tab:
        pending_n = len(committee_repo.list_pending())
        if pending_n:
            st.info(f"🏛 有 {pending_n} 个待委员会召开 —— 去「叙事委员会」页查看并召开圆桌。")
        _render_shifts_view(st, shifts)

    with committee_tab:
        _render_committee_view(st, committee_repo, graph_repo, db_path)

    with workbench_tab:
        _render_data_view(st, repository, news_items, data_rows)

    with system_tab:
        st.caption("系统运行视图：给开发/运维看，不是产品价值面。")
        _render_candidate_panel(st, graph_repo)
        st.divider()
        if st.button("⚡ 立即跑全链路 (Run now)", type="primary"):
            from run_loop import build_run_loop
            st.caption("只处理最近 15 分钟的新闻、最新优先(避免啃旧积压);逐阶段显示进度。")
            loop = build_run_loop(db_path=str(db_path), storage_root=str(STORAGE_ROOT), run_now=True)
            stage_labels = {"ingest": "① 抓取", "triage": "② 筛选 (flash)",
                            "analysis": "③ 分析 (推理)", "consolidation": "④ 整合叙事 (推理)"}
            for stage in loop.stages:
                label = stage_labels.get(stage.name, stage.name)
                with st.status(f"{label} 运行中…", expanded=False) as status:
                    try:
                        result = stage.run_fn()
                        status.update(label=f"✅ {label}: {result}", state="complete")
                    except Exception as exc:
                        status.update(label=f"❌ {label}: {exc}", state="error")
            st.success("全链路跑完一轮。切到「今日叙事/世界树/分歧预警」查看更新(可能需刷新)。")
        health_tab, qa_tab = st.tabs(["运行健康", "抓取自检 (fixture)"])
        with health_tab:
            _render_operations_view(st, operations)
        with qa_tab:
            _render_ingestion_qa_view(st, ingestion_qa)


_LEAN_BADGE = {"偏多": "🟢 偏多", "偏空": "🔴 偏空", "中性": "⚪ 中性"}


def _render_today_view(st: Any, t: Any) -> None:
    st.subheader("今日叙事 · Top Narratives")
    st.caption("从所有资产里排出最值得看的几条:正在驱动切换 > 逼近切换 > 证据多 > 方向性强。")
    if not t.available:
        st.info("世界树还没有数据。到「系统」页点「立即跑全链路」处理新闻后,这里就有内容了。")
        return
    st.caption(f"共 {t.total_assets} 条活跃资产叙事,展示最值得看的 {len(t.cards)} 条。")
    for c in t.cards:
        with st.container(border=True):
            head = f"**{c.name}**　{_LEAN_BADGE.get(c.lean, c.lean)}（强度 {round(c.strength*100)}% · 信心 {c.conviction}）"
            if c.is_shifting:
                head += "　🔀 已切换"
            if c.committee_badge:
                head += f"　🏛 {c.committee_badge}"
            st.markdown(head)
            # 当前状态(叙事 LLM 读数) vs 挑战(确定性推导),分行标清
            st.markdown(f"📖 **当前**：主导 `{c.dominant_driver or '—'}`" + (f" — {c.read_line}" if c.read_line else ""))
            if c.challenger:
                badge = "🔁 方向反转风险" if c.switch_kind == "方向反转风险" else "🔀 同向换驱动"
                st.markdown(f"⚠️ **挑战**：`{c.challenger}` 正逼近 — {badge}")
                if c.flip_note:
                    st.caption(c.flip_note)
            tag = f"regime: {c.tags_regime}" if c.tags_regime else "regime: —"
            st.caption(f"{tag}　·　证据 {c.evidence_count} 条")


def _render_allocation_overview(st: Any, a: Any) -> None:
    st.markdown("### 📊 资产配置速览（按 regime · 方向倾向）")
    st.caption("以下立场由**图谱状态确定性推导**(方向←强度、信心←置信、反转开关←逼近的异号驱动),非 LLM 意见;仅供研究,不构成投资建议。")
    if not a.available:
        st.info("还没有带 regime 标签的活跃资产。跑过整合后,这里按 risk-on/off、再通胀等聚类。")
        return
    for c in a.clusters:
        with st.container(border=True):
            st.markdown(f"**{c.regime}**")
            if c.long_names:
                st.markdown(f"🟢 偏多：{', '.join(c.long_names)}")
            if c.short_names:
                st.markdown(f"🔴 偏空：{', '.join(c.short_names)}")


def _render_world_tree(st: Any, graph_repo: Any) -> None:
    st.subheader("世界树 · Driver Graph")
    st.caption("节点=资产/因子(按层分色),边=谁驱动谁(绿+红−,粗细=权重,加粗=主导驱动),红框=正在切换。")
    layer_opts = {"全部": None, "宏观锚": "anchor", "大类资产": "asset_class", "主题": "theme", "因子": "factor"}
    asset_ids = ["（不聚焦）"] + sorted(n.id for n in graph_repo.list_nodes() if n.kind == "asset")
    c1, c2, c3 = st.columns([1, 1.4, 1])
    layer_label = c1.selectbox("按层过滤", list(layer_opts.keys()), index=0)
    focus_label = c2.selectbox("聚焦某资产(看它的入边)", asset_ids, index=0)
    show_dormant = c3.toggle("显示休眠主题", value=False)
    focus = None if focus_label == "（不聚焦）" else focus_label
    view = build_graph_view(graph_repo, layer=layer_opts[layer_label], focus=focus, include_dormant=show_dormant)
    if not view.nodes:
        st.info("当前过滤条件下没有可显示的节点。")
        return
    st.graphviz_chart(graph_to_dot(view), use_container_width=True)

    if focus:
        node = graph_repo.get_node(focus)
        if node is not None:
            st.markdown(f"### {node.name}　`{node.id}`")
            if node.read_line:
                st.info(node.read_line)
            st.write(f"主导驱动：**{node.dominant_driver or '—'}** · 方向性强度 {round(node.strength*100)}% · "
                     f"regime {node.tags_regime or '—'} · 国家 {', '.join(node.tags_countries) or '—'}")
            incoming = sorted(graph_repo.incoming_edges(focus), key=lambda e: e.weight, reverse=True)
            nature = graph_repo.factor_nature()
            st.markdown("**候选驱动(入边,按权重;性质=结构性最扎实/情绪事件最脆弱)**")
            for e in incoming:
                nat = f"·{nature[e.driver_label]}" if e.driver_label in nature else ""
                st.caption(f"{'🟢+' if e.sign > 0 else '🔴−'} {e.driver_label}{nat}　w={round(e.weight,2)}　← {e.src}　(证据 {len(e.supporting_evidence)})")
            hist = node_shift_history(graph_repo, focus)
            if hist:
                st.markdown("**驱动切换史**")
                for h in hist:
                    st.caption(f"`{_format_datetime(h['at'])}`　{h['from_driver']} → {h['to_driver']}")


def _render_shifts_view(st: Any, v: Any) -> None:
    st.subheader("分歧预警 · Driver Shifts")
    st.caption("哪些资产的主导逻辑切换了、或正在被另一驱动逼近 —— 共识何时可能裂开。")
    if not v.available:
        st.info("当前没有驱动切换或逼近切换。出现足够证据让某资产的次强驱动逼近主导时,这里会报警。")
        return
    st.markdown("### 🔀 已切换")
    if not v.shifts:
        st.caption("当前没有已确认的驱动切换。")
    for s in v.shifts:
        kind = "🔁 方向反转" if s.is_reversal else "🔀 同向换驱动"
        post = "切换后方向反转" if s.is_reversal else "切换后方向不变"
        st.error(
            f"**{s.name}**　当前 **{s.current_lean}**　{kind}　·　`{_format_datetime(s.at)}`\n\n"
            f"主导驱动：`{s.from_driver}`（{s.from_dir}）→ `{s.to_driver}`（{s.to_dir}）—— {post}\n\n"
            f"{s.implication}")
    st.markdown("### ⚠️ 逼近切换(竞争驱动)")
    if not v.contested:
        st.caption("当前没有逼近切换的资产。")
    for c in v.contested:
        kind = "🔁 方向反转风险" if c.is_reversal else "🔀 同向换驱动"
        post = "若切换→方向或反转" if c.is_reversal else "若切换→方向不变"
        st.warning(
            f"**{c.name}**　当前 **{c.current_lean}**　{kind}\n\n"
            f"领先 `{c.leader}`（{c.from_dir}）　逼近 `{c.runner_up}`（{c.to_dir}）　差 {c.gap} —— {post}\n\n"
            f"{c.implication}")


def _render_committee_view(st: Any, committee_repo: Any, graph_repo: Any, db_path: Any) -> None:
    from dataclasses import replace

    from agents.committee import NarrativeCommittee
    from committee.staffing import auto_staff
    from llm.config import load_llm_config
    from llm.factory import build_llm_client
    from schemas.committee import CommitteeSeat

    def _committee_client(tier: str):
        # 委员会用推理模型时,默认 30s 超时不够(主席综合一大段发言会超时);提到 ≥180s。
        cfg = load_llm_config(tier=tier)
        cfg = replace(cfg, timeout_seconds=max(cfg.timeout_seconds, 180.0))
        return build_llm_client(cfg)

    st.subheader("叙事委员会 · Roundtable")
    st.caption("在驱动逼近切换的关键时刻人工召开圆桌:可配置委员人格/专长/LLM/skill;主席综合机构 memo 级结论。不改图,只做咨询。")
    view = build_committee_view(committee_repo)
    skill_ids = [s.id for s in view.skill_library]
    skill_desc = {s.id: s.description for s in view.skill_library}
    skill_name = {s.id: s.name for s in view.skill_library}

    # ---- session 内的工作席位(从配置 default_seats 初始化)----
    if "committee_seats" not in st.session_state:
        st.session_state["committee_seats"] = [s.model_dump() for s in view.default_seats]
        st.session_state["committee_rounds"] = view.default_rounds
        st.session_state["committee_mode"] = view.default_mode

    cfg_tab, pend_tab, hist_tab = st.tabs(["⚙️ 配置席位", f"⚑ 待召开 ({len(view.pending)})", f"📜 历史 ({len(view.sessions)})"])

    with cfg_tab:
        tmpl_names = ["（不套用）"] + [t.name for t in view.templates]
        pick = st.selectbox("套用预设阵容", tmpl_names, index=0)
        if pick != "（不套用）" and st.button("应用此模板"):
            t = next(t for t in view.templates if t.name == pick)
            st.session_state["committee_seats"] = [s.model_dump() for s in t.seats]
            st.session_state["committee_rounds"] = t.rounds
            st.session_state["committee_mode"] = t.mode
            st.rerun()

        seats = st.session_state["committee_seats"]
        st.markdown(f"**当前 {len(seats)} 个席位**(上限 5)")
        for i, seat in enumerate(seats):
            with st.expander(f"席位 {i+1}:{seat.get('name','')}", expanded=False):
                seat["name"] = st.text_input("名称", seat.get("name", ""), key=f"cm_name_{i}")
                seat["persona"] = st.selectbox("人格", view.personas,
                    index=view.personas.index(seat["persona"]) if seat.get("persona") in view.personas else 0, key=f"cm_per_{i}")
                seat["expertise"] = [x.strip() for x in st.text_input("专长(逗号分隔)", ",".join(seat.get("expertise", [])), key=f"cm_exp_{i}").split(",") if x.strip()]
                tiers = ["triage", "analysis", "narrative",
                         "auditor_1", "auditor_2", "auditor_3", "auditor_4", "auditor_5"]
                seat["llm_tier"] = st.selectbox("LLM tier", tiers,
                    index=tiers.index(seat["llm_tier"]) if seat.get("llm_tier") in tiers else 0, key=f"cm_tier_{i}")
                seat["skills"] = st.multiselect("skills", skill_ids, default=[s for s in seat.get("skills", []) if s in skill_ids],
                    format_func=lambda s: skill_name.get(s, s), key=f"cm_sk_{i}")
                if st.button("删除此席位", key=f"cm_del_{i}"):
                    seats.pop(i); st.rerun()
        c1, c2 = st.columns(2)
        if c1.button("➕ 加一个席位") and len(seats) < 5:
            seats.append({"name": "新席位", "persona": view.personas[0], "expertise": [], "llm_tier": "auditor_1", "skills": []})
            st.rerun()
        st.session_state["committee_rounds"] = st.number_input("轮次 rounds", 1, 3, st.session_state["committee_rounds"])
        st.session_state["committee_mode"] = st.selectbox("模式 mode", ["cross", "p2p"],
            index=0 if st.session_state["committee_mode"] == "cross" else 1)
        if c2.button("💾 保存为默认配置"):
            committee_repo.save_committee_config([CommitteeSeat(**s) for s in seats],
                st.session_state["committee_rounds"], st.session_state["committee_mode"])
            st.success("已写回 config/committee.yaml")
        with st.expander("skill 库一览"):
            for s in view.skill_library:
                st.caption(f"**{s.name}** (`{s.id}`) — {s.description}")

    with pend_tab:
        if not view.pending:
            st.caption("当前没有待召开。驱动逼近切换(邻近 0.60/0.75/0.90 或加速)时,整合阶段会在这里标记。")
        for p in view.pending:
            with st.container(border=True):
                tag = f"📊 邻近 {p.level:.0%}" if p.trigger == "proximity" else f"⚡ 加速 +{p.velocity_delta}"
                rv = "🔁反转" if p.is_reversal else "🔀同向"
                st.markdown(f"**{p.asset_name}** {tag} {rv}　逼近度 {p.ratio:.0%}　领先 `{p.leader}` ← 逼近 `{p.runner_up}`")
                seats = st.session_state["committee_seats"]
                if st.button("🤖 自动组阵", key=f"auto_{p.asset_id}_{p.trigger}_{p.level}"):
                    drivers = [e.driver_label for e in graph_repo.incoming_edges(p.asset_id)]
                    auto = auto_staff(drivers, [s.model_dump() for s in view.skill_library], view.personas, max_seats=5)
                    st.session_state["committee_seats"] = [s.model_dump() for s in auto]
                    st.rerun()
                rounds = st.session_state["committee_rounds"]
                st.caption(f"预估 LLM 调用 ≈ {estimate_calls(len(seats), rounds)} 次(席位 {len(seats)} × 轮次 {rounds} + 主席)")
                if st.button("🏛 召开圆桌", key=f"conv_{p.asset_id}_{p.trigger}_{p.level}", type="primary"):
                    with st.status("圆桌讨论中…", expanded=False) as status:
                        try:
                            seat_objs = [CommitteeSeat(**s) for s in seats]
                            pairs = [(so, _committee_client(so.llm_tier)) for so in seat_objs]
                            missing = [so.name for so, cl in pairs if cl is None]
                            if missing:
                                st.warning(f"以下席位的 LLM tier 没配 key,已跳过:{', '.join(missing)}（去 .env 填 LLM_<TIER>_API_KEY,或把席位改到已配置的 tier 如 triage/narrative)")
                            chair = _committee_client("narrative")
                            cm = NarrativeCommittee(seats=pairs, chair_client=chair, rounds=rounds,
                                                    mode=st.session_state["committee_mode"], skill_desc=skill_desc)
                            ctx = _committee_context(graph_repo, p)
                            session = cm.convene(pending=p, context=ctx)
                            committee_repo.save_session(session)
                            committee_repo.clear_pending(p.asset_id)
                            status.update(label=f"✅ {p.asset_name} 圆桌完成", state="complete")
                        except Exception as exc:
                            status.update(label=f"❌ {exc}", state="error")
                    st.rerun()

    with hist_tab:
        if not view.sessions:
            st.caption("还没有圆桌记录。")
        for sess in view.sessions:
            v = sess.verdict
            with st.container(border=True):
                st.markdown(f"### {sess.asset_name}　{v.switch_likelihood}·{v.direction}·信心{v.conviction}　`{_format_datetime(sess.created_at)}`")
                st.info(f"**结论(BLUF)**:{v.bottom_line}")
                st.write(f"**在变什么**:{v.whats_changing}")
                st.write(f"**时间窗**:{v.time_horizon}　·　**信心** {round(v.confidence*100)}%")
                if v.catalysts_to_watch:
                    st.write("**盯这些催化剂**:" + "、".join(v.catalysts_to_watch))
                st.write(f"**证伪/止损**:{v.invalidation}")
                st.write(f"**仓位表达**:{v.positioning}")
                if v.key_disagreements:
                    st.write("**委员分歧**:" + "；".join(v.key_disagreements))
                if v.evidence_basis:
                    st.caption("证据基础:" + "、".join(v.evidence_basis))
                with st.expander(f"各委员发言({len(sess.remarks)})"):
                    for r in sess.remarks:
                        st.caption(f"[第{r.round}轮] {r.seat_name}({r.persona}):{r.critique}")


def _committee_context(graph_repo: Any, pending: Any) -> str:
    node = graph_repo.get_node(pending.asset_id)
    edges = sorted(graph_repo.incoming_edges(pending.asset_id), key=lambda e: e.weight, reverse=True)
    lines = [f"资产:{pending.asset_name}({pending.asset_id})",
             f"当前主导驱动:{node.dominant_driver if node else '—'} · 方向性强度 {round((node.strength if node else 0.5)*100)}%",
             f"逼近:领先 {pending.leader} 被 {pending.runner_up} 逼近(逼近度 {pending.ratio:.0%},{'方向反转' if pending.is_reversal else '同向'})",
             "入边(驱动/符号/权重/证据数):"]
    for e in edges[:6]:
        lines.append(f"  {e.driver_label} {'+' if e.sign>0 else '-'} w={round(e.weight,2)} 证据{len(e.supporting_evidence)}")
    return "\n".join(lines)


def _render_candidate_panel(st: Any, graph_repo: Any) -> None:
    candidates = graph_repo.list_candidates()
    st.markdown(f"### 候选主干待确认（{len(candidates)}）")
    st.caption("LLM 从新闻里提名的新驱动边。批准 → 进图并永久写入 config/approved_edges.yaml;拒绝 → 丢弃。")
    if not candidates:
        st.caption("当前没有待确认的候选边。")
        return
    for cand in candidates:
        with st.container(border=True):
            st.markdown(f"`{cand.src}` —({'+' if cand.sign > 0 else '−'})→ `{cand.dst}`　驱动：**{cand.driver_label}**")
            a, b = st.columns(2)
            if a.button("✅ 批准", key=f"approve-{cand.id}"):
                promoted = graph_repo.promote_candidate(cand.id)
                if promoted is not None:
                    graph_repo.append_approved_edge(promoted)
                st.rerun()
            if b.button("❌ 拒绝", key=f"reject-{cand.id}"):
                graph_repo.reject_candidate(cand.id)
                st.rerun()



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
        st.caption("按发布时间倒序排列（非入库序号）。状态：🟢已分析 · 🟡待处理 · ⚪已跳过 · 🔴出错")
        status_badge = {
            "analyzed": "🟢 已分析", "pending_sort": "🟡 待筛选", "pending_analysis": "🟡 待分析",
            "skipped": "⚪ 已跳过", "error": "🔴 出错",
        }
        for item in news_items:
            with st.container(border=True):
                title_col, action_col = st.columns([5, 1])
                with title_col:
                    st.markdown(f"**{item.title}**")
                    badge = status_badge.get(item.analysis_status, item.analysis_status)
                    st.caption(f"{badge} · {item.source_name} · {_format_datetime(item.published_at)} · 入库#{item.news_item_id}")
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
        # Default to the first item that already has analysis, so the detail pane shows
        # real analysis/evidence instead of "还没生成". Fall back to the newest item.
        analyzed = next((i for i in news_items if i.analysis_status == "analyzed"), None)
        st.session_state["selected_news_id"] = (analyzed or news_items[0]).news_item_id


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
