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
