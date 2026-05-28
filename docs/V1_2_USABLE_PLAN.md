# V1.2 Usable Plan

## 目标定位

V1.2 的目标不是先升级成完整研究平台，而是把 V1.1 从“本地样例可跑”推进到“我可以开始试用”的版本。

本轮只围绕以下最小闭环实现：

1. 新闻抓取 agent 能持续抓取一种最简单来源的新闻
2. 新闻落入轻量数据库，优先使用 SQLite
3. Analyst agent 能从数据库读取待处理新闻并生成 analysis / evidence
4. 预留一个最小 Web UI 方向，优先 Streamlit

## 明确约束

- 不重构现有核心逻辑
- 不推翻 V1.1 的 JSON demo 和现有 agent/pipeline 结构
- 不优先做 ResearchBook / ApprovalRequest / Web Console
- 第一版只支持一种最简单新闻来源
- 数据库存储优先 SQLite，但表结构要为未来迁移到 PostgreSQL 留出空间

## 现状判断

V1.1 已经具备以下能力：

- 原始 JSON 输入经过 `NewsSorterAgent` 生成 `ResourceCard`
- `AnalystAgent` 生成 `AnalysisCard` 和 `Evidence`
- `NarrativeManagerAgent` 消费 `Evidence` 更新叙事状态
- 整条链路可以通过 `demo_runner.py` 跑通

V1.2 可试用版应当在 V1.1 的基础上增加“持续输入 + 数据库存储 + DB 驱动消费”，而不是先改写核心 agent 语义。

## 1. 新闻抓取最小方案

### 选择

第一版使用公开 `RSS/Atom` 作为唯一新闻输入来源。

原因：

- 不依赖 API key，启动成本最低
- 适合先验证“持续抓取 -> 去重 -> 入库 -> 分析消费”
- 可以在接口层预留未来扩展更多新闻源的能力

### 最小实现方式

- 增加一个轻量 `NewsSourceAdapter` 抽象
- 第一版只实现 `RssFeedAdapter`
- 轮询脚本定期拉取 feed，解析为统一的 `RawNewsItem`
- 通过 `dedupe_key` 做幂等写入 SQLite

### 统一输入字段

`RawNewsItem` 最小字段：

- `source_type`
- `source_name`
- `external_id`
- `url`
- `title`
- `summary`
- `published_at`
- `fetched_at`
- `raw_payload`

### 对未来多来源的扩展接口

V1.2 不实现多源调度，但接口要允许后续新增：

- `DailyNewsApiAdapter`
- `TradingEconomicsAdapter`
- `ManualUploadAdapter`
- `ScraperAdapter`

也就是说，未来扩展点放在 adapter 层，而不是先引入大而全的 ingestion platform。

## 2. SQLite 表设计

### `news_items`

用于保存抓取后的原始新闻和处理状态。

建议字段：

- `id` INTEGER PRIMARY KEY
- `source_type` TEXT NOT NULL
- `source_name` TEXT NOT NULL
- `external_id` TEXT
- `url` TEXT NOT NULL
- `title` TEXT NOT NULL
- `summary` TEXT NOT NULL
- `published_at` TEXT
- `fetched_at` TEXT NOT NULL
- `dedupe_key` TEXT NOT NULL UNIQUE
- `raw_payload_json` TEXT NOT NULL
- `resource_card_json` TEXT
- `analysis_status` TEXT NOT NULL
- `last_error` TEXT

建议最小状态：

- `pending_sort`
- `pending_analysis`
- `analyzed`
- `skipped`
- `error`

### `analysis_cards`

保存 Analyst 输出结果，便于 UI 查看和审计。

建议字段：

- `id` TEXT PRIMARY KEY
- `news_item_id` INTEGER NOT NULL
- `analysis_card_json` TEXT NOT NULL
- `mainline_relation` TEXT NOT NULL
- `confidence` REAL NOT NULL
- `created_at` TEXT NOT NULL

### `evidence_records`

保存 Evidence，供后续 narrative 或 UI 消费。

建议字段：

- `id` TEXT PRIMARY KEY
- `news_item_id` INTEGER NOT NULL
- `analysis_card_id` TEXT NOT NULL
- `evidence_json` TEXT NOT NULL
- `relation_type` TEXT NOT NULL
- `target_main_narrative_id` TEXT
- `target_branch_id` TEXT
- `created_at` TEXT NOT NULL

### 为什么这样设计

- 先用 JSON 列快速保存现有对象，不强迫重构 schema
- 同时把少量高频过滤字段拆出来，便于后续 UI 和查询
- 将来迁移 PostgreSQL 时可以直接沿用三表边界

## 3. Analyst 如何从数据库消费新闻

### 最小消费流程

1. 从 `news_items` 中读取 `analysis_status = 'pending_sort'` 或 `pending_analysis` 的记录
2. 若记录还没有 `resource_card_json`，先复用 `NewsSorterAgent` 转成 `ResourceCard`
3. 如果 `route_to_analysis = false`，状态改为 `skipped`
4. 如果需要分析，复用现有 `AnalystAgent` 和 `extract_evidence_from_analysis`
5. 将 `AnalysisCard` 写入 `analysis_cards`
6. 将 `Evidence` 写入 `evidence_records`
7. 将 `news_items.analysis_status` 更新为 `analyzed`
8. 如果异常，写入 `last_error` 并标记为 `error`

### 设计原则

- 尽量直接复用现有 agent 和 pipeline
- 不先引入任务编排器、审批流或复杂状态机
- 先把“数据库中有待处理新闻 -> 可以被 Analyst 消费”做通

## 4. Streamlit 最小页面应显示什么

第一版页面只做只读监控页，不做审批、编辑或控制台。

建议显示：

### 顶部统计

- `pending_sort`
- `pending_analysis`
- `analyzed`
- `skipped`
- `error`

### 新闻列表

展示最近抓到的新闻：

- 时间
- 来源
- 标题
- 当前状态

### 详情区

展示选中新闻对应的：

- 标题与摘要
- `ResourceCard` 关键信息
- `AnalysisCard.thesis`
- `mainline_relation`
- `Evidence.claim`
- `Evidence.why`

### 最小交互

- 自动刷新或手动刷新
- 只读查看

## 5. 明确留到后续版本的内容

以下内容明确不在本轮实现：

- ResearchBook
- ApprovalRequest
- Web Console
- 多新闻源调度与优先级治理
- 云部署 / PostgreSQL 正式迁移
- 向量检索 / RAG
- 审批流
- 多 analyst 并发治理
- 完整的 narrative 数据库化改造

## 本轮建议落地顺序

1. 新增 SQLite repository 与表初始化
2. 新增 RSS adapter 与最小抓取脚本
3. 新增 DB 驱动的 analyst consumer
4. 增加最小测试
5. 追加一个只读 Streamlit 页面骨架

## 验收标准

满足以下条件即可认为 V1.2 可试用版第一步成立：

- 运行抓取入口后，SQLite 中出现新闻记录
- 再运行 analyst consumer 后，生成 `analysis_cards` 和 `evidence_records`
- 现有 V1.1 测试不回归
- Streamlit 页至少能看到新闻状态和分析摘要
