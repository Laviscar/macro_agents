# V1.1 Status

## 当前版本定位

这是一个可运行、可测试、可复盘的最小宏观多 Agent MVP。

它已经具备：

- 从 `sample_news.json` 跑通完整 demo
- `Evidence` 驱动的 Narrative 更新
- 基于 `relation_type` 的最小 main / branch 分流
- 本地 JSON 持久化
- 最小 Knowledge Layer 接线

## 当前边界

- `supports` 和 `complicates` 走 `main-only`
- `conflicts_with` 和 `lowers_probability_of` 走 branch 路径
- `raises_probability_of` 当前阶段暂时按 `main-only` 处理

## 暂不做

- promote / replace
- 多 branch 协调
- 数据库迁移
- 向量检索 / RAG
- 新 agent
- 前端或调度系统
