# Macro Agents

一个围绕宏观研究流程构建的多 Agent 系统：把连续的宏观新闻输入逐步沉淀成可更新、可追溯的「叙事状态」。

- `News Sorter Agent` / `Analyst Agent` / `Narrative Manager Agent`

## 版本进展

| 版本 | 能力 |
|------|------|
| **V1.1** | 三 Agent 规则链路，Evidence 驱动叙事更新，JSON 落盘，demo |
| **V1.2** | SQLite + RSS/Finnhub 抓取 + DB consumer + Streamlit UI + Ingestion QA |
| **V1.3** | **Harness**：Loop 状态机 / PolicyEngine 风险门控 / BudgetGuard 预算 / ToolRuntime / SessionStore（事件可回放）/ Compaction / Eval 回放（`harness/`，设计见 `docs/V1_3_HARNESS_ARCHITECTURE.md`） |
| **V1.4** | **LLM 集成 + 持续运行**：provider 无关 LLM 层（`llm/`，OpenAI 兼容 / Claude / MiniMax）；AnalystAgent + NarrativeManager 改为 **LLM 优先 + 规则兜底**；**三层独立配置的 LLM**（triage 便宜筛选 / analysis 分析 / narrative 叙事）；常驻 **`run_loop.py`**（抓取→筛选→分析→60min 整合）+ Streamlit「⚡立即跑全链路」按钮；token 预算 enforcement，`.env` 配置 |
| **V1.5** | **叙事审计员 AuditPanel**：0–3 个可配置审计席位（各自独立 key）批判叙事管理员判断；cross（交叉验证）/ p2p（点对点）两种讨论模式 |
| **V1.6** | **叙事驱动图（世界树）**：单主线+累加强度 → **资产/驱动有向图**。节点=资产(41)+因子(受控词表),边="谁驱动谁"(结构性符号 + 证据衰减权重)。最强入边=主导驱动,变了=**驱动切换**(自动预警,区分🔁方向反转/🔀同向换驱动)。强度去累加(14天半衰期),0证据不建边,主题节点21天无证据休眠。UI:今日叙事 top-N + 配置立场速览 / 世界树 graphviz 图 / 分歧预警 / 系统页候选边人工确认。设计见 `docs/superpowers/specs/2026-06-01-v1.6-narrative-graph-design.md` |

> **不配 API key 时，全系统自动退回 V1.3 规则版**，行为与纯规则一致。
>
> **跑通 / 测试 / 配 key / 排错的完整步骤见 [`docs/RUNNING_AND_TESTING.md`](docs/RUNNING_AND_TESTING.md)。**

## 架构分层（V1.3+）

```
编排层    run_loop.py（常驻分层定时:ingest→triage→analysis→consolidation）/ pipelines/stages.py
入口脚本  run_loop.py / run_harness.py / demo_runner.py / run_live_ingest.py / streamlit_app.py
控制平面  harness/coordinator.py  →  HarnessCoordinator
执行平面  harness/loop.py（状态机）+ harness/runtime.py（工具）+ harness/policy.py + harness/budget.py
智能层    agents/（规则 + triage）+ llm/（三层 LLM 客户端,注入 agent,带兜底）
数据平面  repositories/（SQLite）+ storage/（叙事状态 JSON + run_state.json）+ harness/session_store.py
```

## 项目目标

这个项目的目标不是做一次性新闻摘要，而是把宏观输入逐步沉淀成可更新的叙事状态：

- 原始输入先被清洗成 `ResourceCard`
- 高信号事件被提升为 `AnalysisCard`
- 分析再被收敛成可程序消费的 `Evidence`
- `Narrative Manager` 只通过 `Evidence` 更新主线 / 分支状态
- 结果以本地 JSON 形式归档，便于复盘和继续迭代

## 三个 Agent 的职责

- `News Sorter Agent`
  负责原始输入清洗、标准化、打分、路由，输出 `ResourceCard`
- `Analyst Agent`
  负责高信号事件分析与 `Evidence` 提炼，输出 `AnalysisCard` 和 `Evidence`
- `Narrative Manager Agent`
  负责消费 `Evidence` 更新 `MainNarrative`、`BranchNarrative`、`NarrativeCommit`、`ScenarioSplit`、`ChallengeAlert`

## 关键数据对象

- `ResourceCard`
  标准化后的原始事件卡片
- `AnalysisCard`
  事件分析结果，供审计、解释和补充上下文使用
- `Evidence`
  Narrative 层的最小更新单元，包含 `claim / relation_type / why / counter_evidence`
- `MainNarrative`
  当前主线状态
- `BranchNarrative`
  对主线构成挑战或替代可能的分支状态
- `NarrativeCommit`
  一次叙事更新的可追溯记录

## V1.1 已完成范围

- 原始新闻输入转 `ResourceCard`
- 高信号事件转 `AnalysisCard`
- 从分析中提炼 `Evidence`
- 使用 `Evidence` 更新叙事状态
- 将结果持久化为本地 JSON 文件
- 最小 Knowledge Layer 接线：`always load / by_task load`
- 最小 demo：从 `examples/sample_news.json` 跑完整条链路
- 基于 `relation_type` 的最小 Narrative 分流

## 关键约束

- `Narrative Manager` 以 `Evidence` 为主输入
- `AnalysisCard` 仅用于审计和补充上下文
- 第一轮仅使用本地 JSON 文件存储
- 不实现 `Meta Narrative Manager`
- 不实现完整 Git 语义

## 当前 relation_type 行为

- `supports`
  走 `main-only` 路径，更新主线的 `supporting_evidence / strength / confidence`，记录 main commit
- `raises_probability_of`
  当前阶段默认也走 `main-only`，做小幅主线强化；这只是 V1.1 的最小治理策略，不代表长期最终语义
- `complicates`
  走 `main-only`，更新主线的 `fragility / watch_items`，记录 main commit，不默认创建 branch
- `conflicts_with`
  走 branch 路径，创建或更新 branch，更新 `supporting_evidence / branch_strength / challenge_probability`，记录 branch commit
- `lowers_probability_of`
  当前走 branch 路径，和 `conflicts_with` 一样优先表现为对主线形成压力的分支更新

## 如何运行 Demo

使用现有 `macro` 环境：

```bash
cd /Users/luyi/Projets/Macro_analyst/macro_agents
python demo_runner.py
```

默认输入：

- `examples/sample_news.json`

默认输出目录(demo 是**离线沙箱**,写到 `storage/demo/`,不碰生产数据 —— 见 `docs/DATA_FLOW.md`):

- `storage/demo/resource_cards/`
- `storage/demo/analysis_archive/`
- `storage/demo/evidence/`
- `storage/demo/main_narrative_state/`
- `storage/demo/branch_narrative_state/`
- `storage/demo/narrative_commits/`
- `storage/demo/scenarios/`
- `storage/demo/alerts/`

> 给 UI / 时间线供数的是 **`run_harness.py`**(累积、不清空),不是 demo。数据契约见 `docs/DATA_FLOW.md`。

## 如何运行 Tests

```bash
cd /Users/luyi/Projets/Macro_analyst/macro_agents
python -m pytest
```

## 常驻抓取服务

这一轮新增了可长期运行的抓取服务，职责只覆盖：

- 多源轮询抓取
- 统一归一化为 `RawNewsItem`
- 复用 `SQLiteNewsRepository` 入库
- 单源失败隔离
- 最小重试 / 退避
- `SIGINT` / `SIGTERM` 优雅退出

### 支持的 source type

- `rss`
- `finnhub`

### 配置文件

默认配置在：

- `config/sources.yaml`

配置结构示例：

```yaml
service:
  db_path: ../storage/macro_agents.sqlite3
  default_poll_interval_seconds: 300
  retry:
    max_attempts: 2
    backoff_seconds: 2

sources:
  - type: rss
    name: fed_rss
    enabled: false
    url: https://www.federalreserve.gov/feeds/press_all.xml

  - type: rss
    name: bls_latest_rss
    enabled: false
    url: https://www.bls.gov/feed/bls_latest.rss

  - type: finnhub
    name: finnhub_general
    enabled: true
    endpoint: https://finnhub.io/api/v1/news
    api_key_env: FINNHUB_API_KEY
    category: general
    limit: 20
```

### Finnhub 配置

默认配置已经切到 `Finnhub general news`，启动前先设置环境变量：

```bash
export FINNHUB_API_KEY=your_token_here
```

默认的 `config/sources.yaml` 现在只启用：

- `finnhub_general`

默认不启用：

- `fed_rss`
- `bls_latest_rss`
- `bis_press_rss`
- `finnhub_symbols`

如果启用了 `finnhub` source 但没有设置 `FINNHUB_API_KEY`，服务会在启动阶段直接报出明确错误，而不是等到轮询时才失败。

支持的最小配置字段包括：

- `type`
- `name`
- `enabled`
- `poll_interval_seconds`
- `url` / `endpoint`
- `api_key_env`
- `symbols` / `tickers`
- `category`
- `limit`
- `lookback_days`
- `params`

### 可信来源目录

`config/sources.yaml` 还包含顶层 `trusted_sources`，用于维护可信信息来源白名单。它不会自动启动抓取，也不会绕过 adapter 注册；只有 `sources` 里的条目才会被 live ingest 轮询。

目录里的 `reliability_tier` 约定：

- `primary`: 官方数据、官方数据库、监管或央行原始发布
- `secondary`: 通讯社、严肃财经媒体、研究数据库或方法论透明的研究机构

已经加入的默认目录覆盖：

- 中美官方宏观与政策来源
- IMF、World Bank、OECD、BIS、FRED 等国际数据库
- Reuters、AP、Bloomberg、FT 等事件流和财经媒体
- Our World in Data、Pew Research Center 等研究型来源

### 启动命令

```bash
cd /Users/luyi/Projets/Macro_analyst/macro_agents
python run_live_ingest.py --config config/sources.yaml
```

预期第一轮日志里会看到：

- `service_started`
- `source_poll_succeeded`

或：

```bash
cd /Users/luyi/Projets/Macro_analyst/macro_agents
python -m pipelines.live_ingest --config config/sources.yaml
```

兼容说明：

- 旧路径 `configs/feeds.yaml` 在新文件存在时仍会被 loader 识别为兼容别名
- 日常维护请只编辑 `config/sources.yaml`

### 扩展一个新新闻源

后续新增 source 时，理想路径是：

1. 在 `sources/` 下新增一个 adapter
2. 让它输出统一的 `RawNewsItem`
3. 在 `sources/factory.py` 里注册新 type
4. 在 `config/sources.yaml` 增加对应配置

主轮询服务本身不需要改。

### 配置整理原则

- 所有非敏感、人工可编辑配置统一放在 `config/`
- `config/sources.yaml` 是抓取服务的主配置入口
- `config/README.md` 说明哪些字段适合日常修改
- API keys 等敏感信息继续走环境变量，不写进 YAML

## Ingestion QA

为了验证第一段链路“抓新闻 -> 洗新闻 -> 存新闻”，现在提供了一个固定 fixture 的 QA 入口。

### 运行命令

```bash
cd /Users/luyi/Projets/Macro_analyst/macro_agents
python -m pipelines.ingestion_qa
```

或：

```bash
cd /Users/luyi/Projets/Macro_analyst/macro_agents
python run_ingestion_qa.py
```

### QA 会做什么

- 用固定 fixture source 模拟抓取
- 验证重复新闻不会重复入库
- 验证坏 payload 不会拖垮整批有效新闻
- 跑一轮 `db_consumer`，让 `ResourceCard` 和状态变化可见
- 生成简明文本报告
- 写出一份 UI 可读的 JSON 报告

### 报告位置

- `storage/qa/ingestion_qa.sqlite3`
- `storage/qa/ingestion_report.json`

### 在 UI 看什么

运行 QA 后，打开 Streamlit 的 `Ingestion QA` Tab，可以看到：

- source 级抓取统计
- 去重与坏 payload 统计
- 当前状态计数
- 清洗 route 分布
- 原始新闻 / ResourceCard / 当前状态的样本对照
- source 失败和坏 payload 明细

## V1.1 未完成范围 / 后续方向

- `raises_probability_of` 未来可能需要区分“强化 main”与“强化 branch”
- 还没有显式的 target-aware branch 治理机制
- 还没有 `promote / replace / merge / revert` 之类更复杂的叙事生命周期
- 还没有多 branch 协调逻辑
- 还没有更丰富的 manual note / 多样本输入治理
- 还没有生产级调度、数据库、检索和前端

## 目录

- `agents/`: 三个核心 agent（规则逻辑，可注入 LLM）
- `llm/`: provider 无关 LLM 层（接口 / 配置 / OpenAI 兼容 / Claude / 工厂 / 计量）
- `harness/`: 运行时内核（Loop 状态机 / 工具运行时 / 策略 / 预算 / 会话 / 评估 / 压缩）
- `pipelines/`: 处理链路（ingest / clean / analyze / evidence / narrative_update / live_ingest / db_consumer / QA）
- `sources/`: 新闻源 adapter（RSS / Finnhub）+ 配置加载
- `repositories/`: SQLite 数据访问
- `schemas/`: 稳定数据边界（Pydantic）
- `presenters/` + `view_models/`: Streamlit UI 的展示层与 DTO
- `knowledge/`: 领域知识（master prompt / rubric / protocol）—— 当前供审计，尚未喂入 LLM 提示词
- `utils/`: 时钟 / ID / 打分 / IO / .env 加载 / knowledge_loader
- `config/`: 非敏感可编辑配置（`sources.yaml`）
- `storage/`: 叙事状态 JSON + SQLite 落盘
- `tests/`: 测试（190 用例）
- `docs/`: 版本边界、架构设计、运行手册
