# Macro Agents v1.1

一个围绕宏观研究流程构建的最小多 Agent MVP：

- `News Sorter Agent`
- `Analyst Agent`
- `Narrative Manager Agent`

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
/Users/luyi/tools/miniconda3/envs/macro/bin/python demo_runner.py
```

默认输入：

- `examples/sample_news.json`

默认输出目录：

- `storage/resource_cards/`
- `storage/analysis_archive/`
- `storage/evidence/`
- `storage/main_narrative_state/`
- `storage/branch_narrative_state/`
- `storage/narrative_commits/`
- `storage/scenarios/`
- `storage/alerts/`

## 如何运行 Tests

```bash
cd /Users/luyi/Projets/Macro_analyst/macro_agents
/Users/luyi/tools/miniconda3/envs/macro/bin/python -m pytest
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
/Users/luyi/tools/miniconda3/envs/macro/bin/python run_live_ingest.py --config config/sources.yaml
```

预期第一轮日志里会看到：

- `service_started`
- `source_poll_succeeded`

或：

```bash
cd /Users/luyi/Projets/Macro_analyst/macro_agents
/Users/luyi/tools/miniconda3/envs/macro/bin/python -m pipelines.live_ingest --config config/sources.yaml
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
/Users/luyi/tools/miniconda3/envs/macro/bin/python -m pipelines.ingestion_qa
```

或：

```bash
cd /Users/luyi/Projets/Macro_analyst/macro_agents
/Users/luyi/tools/miniconda3/envs/macro/bin/python run_ingestion_qa.py
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

- `agents/`: 三个核心 agent
- `schemas/`: 稳定数据边界
- `pipelines/`: 最小处理链路
- `storage/`: JSON 落盘目录
- `knowledge/`: 最小知识层占位
- `tests/`: 第一轮测试
- `docs/`: 版本边界与交接说明
