# V1.3 Harness Architecture（Macro Narrative AI）

> **实施状态（2026-05-30）**：本文为设计文档。Phase 1-3 + Direction A（连续运行闭环）+ 加固已全部完成并落在 `harness/`；V1.4 在此之上加了 LLM 集成（`llm/`）。
> 注意：第 9 节的 `cost_budget_usd` 尚未实现（`BudgetConfig` 目前只有 `time_budget_seconds` + `token_budget`）；运行/测试步骤见 `docs/RUNNING_AND_TESTING.md`。

## 1. 目标定位

V1.3 的目标是把当前 `macro_agents` 从「能跑通链路」升级为「可持续运行、可控、可评估」的宏观叙事系统。

核心方向：

1. 采用 **Hermes 风格模块化内核**（Loop / Tool Runtime / Memory / Session / Event）
2. 引入 **Claude 风格运行时护栏**（权限、并发控制、预算、重试、中断、远程控制）
3. 不推翻 V1.1/V1.2 已有数据模型和 pipeline，只做可增量接入

---

## 2. 非目标（本轮明确不做）

1. 不直接接入真实交易下单
2. 不一次性重写全部 agent
3. 不先做复杂前端平台
4. 不引入重型分布式编排基础设施

---

## 3. 设计原则

1. Evidence-first：叙事更新只能由 `Evidence` 驱动
2. Guardrail-first：任何高风险动作必须先过策略门控
3. Replayable：每次叙事结论都能在历史窗口复现
4. Bounded-loop：每个回合有 token/时间/成本上限
5. Progressive rollout：按阶段替换，不做大爆炸迁移

---

## 4. 总体架构（推荐混合方案）

### 4.1 控制平面（Control Plane）

- `HarnessCoordinator`：任务入口、回合生命周期、预算追踪、状态推进
- `PolicyEngine`：权限策略与风险分级（read / write / external side effect）
- `EvalScheduler`：离线回放与指标计算入口

### 4.2 执行平面（Execution Plane）

- `NarrativeLoopEngine`：思考 -> 工具调用 -> 观察 -> 叙事更新 -> 结束判断
- `ToolRuntime`：统一的工具注册、schema 校验、执行与结果标准化
- `ConcurrencyController`：并发安全工具可并行，写操作串行

### 4.3 数据平面（Data Plane）

- 现有 `storage/` 继续保留为权威落盘层
- 新增 `harness_sessions`、`harness_events`、`harness_eval_runs`（先 SQLite）
- Narrative 状态仍由现有 `main_narrative_state` / `branch_narrative_state` 维护

### 4.4 记忆与上下文层（Memory & Context）

- `SessionMemory`：单次任务上下文（回合内）
- `NarrativeMemory`：跨任务叙事记忆（主线、分支、挑战历史）
- `CompactionService`：长会话压缩为「叙事摘要 + 证据索引」，不是简单截断

### 4.5 可观测性层（Observability）

- `EventBus`：统一记录 tool_call、tool_result、loop_transition、policy_decision
- `TraceStore`：支持按任务回放完整决策链

---

## 5. 与现有代码目录的映射

在不破坏当前结构的前提下新增：

1. `macro_agents/harness/`
2. `macro_agents/harness/loop.py`
3. `macro_agents/harness/runtime.py`
4. `macro_agents/harness/policy.py`
5. `macro_agents/harness/budget.py`
6. `macro_agents/harness/events.py`
7. `macro_agents/harness/session_store.py`
8. `macro_agents/harness/eval.py`

复用已有模块：

1. `agents/analyst.py`、`agents/narrative_manager.py`
2. `pipelines/evidence_extract.py`、`pipelines/narrative_update.py`
3. `repositories/news_repository.py`
4. `schemas/*.py`

---

## 6. Loop 状态机（核心）

状态：

1. `INIT`
2. `PLAN`
3. `TOOL_EXEC`
4. `OBSERVE`
5. `UPDATE_NARRATIVE`
6. `CHECK_BUDGET_AND_STOP`
7. `DONE`
8. `FAILED`

关键转移：

1. `INIT -> PLAN`：创建任务上下文
2. `PLAN -> TOOL_EXEC`：产出工具调用计划
3. `TOOL_EXEC -> OBSERVE`：收集结构化结果
4. `OBSERVE -> UPDATE_NARRATIVE`：生成/更新 Evidence
5. `UPDATE_NARRATIVE -> CHECK_BUDGET_AND_STOP`：写入叙事状态
6. `CHECK_BUDGET_AND_STOP -> PLAN`：若仍需追问或补证据
7. `CHECK_BUDGET_AND_STOP -> DONE`：达到停止条件

停止条件：

1. 已得到高置信主结论且挑战分支稳定
2. 达到 token/时间/成本上限
3. 风险门控拒绝继续执行高风险动作

---

## 7. Tool Runtime 规范

统一工具接口建议：

1. `name`
2. `input_schema`
3. `is_concurrency_safe(input) -> bool`
4. `risk_level`（low/medium/high/critical）
5. `execute(input, context) -> ToolResult`

工具分类：

1. Read-only：读新闻、读历史状态、读外部宏观数据（可并行）
2. Transform：抽取证据、打分、归因（可并行）
3. Write-state：写 narrative state / commit（串行）
4. External-side-effect：发送告警、触发 webhook（需审批）

---

## 8. 权限与风险门控（Policy Engine）

决策类型：

1. `allow`
2. `deny`
3. `ask_for_approval`

最小策略矩阵：

1. Low risk read：默认 allow
2. Medium risk write-local：默认 allow + 记录审计
3. High risk external call：ask_for_approval
4. Critical（影响交易动作或外部系统写入）：deny（除非显式 override）

审批记录必须落盘到 `harness_events`，便于复盘「为什么允许/拒绝」。

---

## 9. 预算治理（Budget Guard）

每个任务设置三类预算：

1. `token_budget`
2. `time_budget_seconds`
3. `cost_budget_usd`

运行规则：

1. 每回合结束后统一核算
2. 超限时优先做一次 `Compaction + Final Summary`
3. 若仍超限，进入 `DONE` 并返回带原因的 result

---

## 10. 评估 Harness（离线回放）

目标：评估叙事系统是否在真实时间推进中“稳定且有增量价值”。

建议回放输入：

1. `news_items` 历史窗口（按时间顺序）
2. 当时可见的宏观数据快照
3. 当时已存在的 narrative state

核心指标：

1. Narrative Stability：主线在相邻窗口的漂移程度
2. Evidence Precision：被后续事实支持的证据比例
3. Challenge Hit Rate：分支预警命中率
4. Latency：单任务处理时间
5. Cost：单任务 token 与美元成本

---

## 11. 分阶段落地计划

### Phase 1（1 周）：最小 Harness 骨架

1. 建立 `harness/` 目录与状态机
2. 将 `analyst + narrative_update` 接入 Loop
3. 加入 token/time 两类预算

验收：

1. 可从 DB 拉取新闻并通过 Harness 完成一次叙事更新
2. 任务日志可回放

### Phase 2（1-2 周）：Policy + 并发控制

1. 实现 ToolRuntime 分类执行（并发安全 vs 串行）
2. 引入 PolicyEngine 风险门控
3. 审批记录落盘

验收：

1. 高风险工具会触发审批分支
2. 并发策略可配置并可测试

### Phase 3（1 周）：Compaction + Eval Harness

1. 长会话压缩机制
2. 每日/每周离线回放任务
3. 输出评估报告（JSON + 可视化摘要）

验收：

1. 长会话不失控
2. 可产出稳定的回放指标

---

## 12. 对当前项目的直接收益

1. 从“脚本链路”升级到“可持续运行系统”
2. 决策路径可解释（证据、权限、预算、停止原因）
3. 新增数据源和 agent 时不再线性增加复杂度
4. 为未来接入自动告警、研究助手 UI、甚至交易前信号过滤提供统一底座

---

## 13. 下一步实施建议（紧接本设计）

1. 先实现 `Phase 1`，不要并行开 `Phase 2/3`
2. 在 `tests/` 增加 Harness 状态机和预算超限测试
3. 先把回放评估做成离线 CLI，再考虑挂到 Streamlit

