# 跑通 & 测试实用手册（macro_agents）

面向：拿到这个仓库后，想**跑通测试**、**配置 API**、**端到端运行系统**的人。
命令默认在项目根目录 `macro_agents/` 下执行。

---

## 0. 一次性环境准备

```bash
# 建议用 conda env（项目用的是 macro）
conda activate macro            # 或你自己的 venv

# 安装依赖（含 pyyaml —— 不装它会有 7 个测试在收集阶段报错）
pip install -r requirements.txt
```

依赖清单（`requirements.txt`）：`pydantic>=2.7`、`pyyaml>=6.0`、`python-dateutil>=2.9`、`pytest>=8.0`、`streamlit>=1.40`。
LLM 调用**不需要**额外 SDK（用的是 stdlib `urllib`）。

> 项目根有 `conftest.py`，会把项目根目录加进 `sys.path`，所以直接 `pytest` 就能 import `harness`/`llm`/`agents` 等包，**无需手动设 `PYTHONPATH`**。

---

## 1. 跑测试

### 跑全部
```bash
pytest -q
```
- 装了 `pyyaml` → 全绿。
- **没装 `pyyaml`** → 会看到 7 个文件 `ModuleNotFoundError: No module named 'yaml'`（finnhub/rss/source_config/ingestion_qa/knowledge_loader/live_ingest/demo_runner）。这是依赖没装，不是代码坏。装上即可。

### 只跑某一块
```bash
pytest tests/test_harness_*.py -v        # Harness（loop/policy/budget/eval/session_store/coordinator…）
pytest tests/test_llm_*.py -v            # LLM 层（config/客户端/factory/metering）
pytest tests/test_analyst*.py -v         # AnalystAgent（规则 + LLM）
pytest tests/test_narrative_manager*.py -v   # NarrativeManager（规则 + LLM）
pytest tests/test_dotenv.py -v           # .env 加载器
```

### 跑单个测试
```bash
pytest tests/test_harness_loop.py::test_successful_run_returns_done -v
```

### 关键点
- 所有测试都是**离线**的——LLM 调用走 `FakeLLMClient` 或 mock transport，**不联网、不烧 token、不需要 API key**。
- CI 安全：没配 key 时，系统自动走规则兜底路径，测试照样绿。

---

## 2. 配置 API Key（LLM + Finnhub）

所有 key 统一放一个文件：项目根的 **`.env`**（已被 `.gitignore` 忽略，永不进版本库）。

```bash
cp .env.example .env      # 第一次：从模板生成
# 然后编辑 .env
```

`.env` 里和 API 相关的字段：

```bash
# --- LLM ---
LLM_PROVIDER=openai                 # openai | minimax | anthropic
LLM_MODEL=gpt-4o-mini               # 改成你的端点支持的模型名
# LLM_BASE_URL=https://api.openai.com/v1   # 用代理/MiniMax/自建端点时改这里
OPENAI_API_KEY=                     # 填你的 LLM key（openai 协议）
# MINIMAX_API_KEY=                  # 用 minimax 时填这个
# ANTHROPIC_API_KEY=               # 用 claude 时填这个
# LLM_API_KEY_ENV=MY_CUSTOM_KEY    # 想用自定义变量名时指向它
# LLM_TIMEOUT_SECONDS=30
# LLM_TOKEN_BUDGET=0               # 每个任务的 token 上限，0=不限；>0 超限会停 loop

# --- Finnhub（实时抓取用）---
FINNHUB_API_KEY=your_finnhub_api_key
```

### ⚠️ 两个必须知道的坑

1. **shell 已 export 的变量优先于 `.env`。**
   加载器（`utils/dotenv.py`）**不会覆盖**已经存在于环境里的变量。如果你之前在 `~/.zshrc` 里 `export FINNHUB_API_KEY=...`，那 `.env` 里写的 Finnhub 值会被忽略。
   - 想让 `.env` 统一管理：`unset FINNHUB_API_KEY`（或从 `.zshrc` 删掉那行）。
   - 想继续用 shell 那份：`.env` 里的 Finnhub 留空即可，别写两个不同的值。
   查当前 shell 里有没有：`echo $FINNHUB_API_KEY`、`echo $OPENAI_API_KEY`。

2. **MiniMax / 其它 OpenAI 兼容端点**：把 `LLM_PROVIDER=minimax`（或 `openai`）+ `LLM_BASE_URL=<端点>` + 对应 key 即可，不用改代码。

### `.env` 会被谁加载？
入口脚本启动时会调用 `load_dotenv()` 自动读 `.env`：`run_harness.py` / `demo_runner.py` / `run_live_ingest.py` / `run_ingestion_qa.py` / `streamlit_app.py`。
> 注意：直接 `pytest` 不加载 `.env`（测试本就不该依赖真实 key）。

---

## 3. 端到端运行系统

### 3.1 离线 demo（最快验证全链路，不碰 DB/网络）
```bash
python demo_runner.py
```
读 `examples/sample_news.json` → 跑完整管道 → 把叙事状态写到 `storage/`，并打印 ResourceCards / AnalysisCards / Evidence / Branches / Commits 数量。

### 3.2 Harness 处理 DB 里的待办新闻（生产路径，会用 LLM）
```bash
python run_harness.py                     # 默认 batch=20, 把 pending 新闻全部消费完
python run_harness.py --batch-size 10 --max-batches 5
python run_harness.py --db storage/macro_agents.sqlite3 --storage-root storage
```
流程：从 DB 拉 `pending` 新闻 → 经 Harness（sort+analyze → 写回 DB 并标记 → 叙事增量更新）→ 打印处理批次/状态统计。
- **配了 LLM key** → analyze / 叙事挑战判断走 Claude/OpenAI；**没配** → 走规则兜底。
- 配了 `LLM_TOKEN_BUDGET>0` → 超预算时该任务以 `stop_reason=token_exceeded` 停下。

### 3.3 实时抓取新闻入库（Finnhub / RSS）
```bash
python run_live_ingest.py                 # 需要 FINNHUB_API_KEY；按 config/sources.yaml 抓取
```
抓到的新闻写进 SQLite，状态为 `pending_sort`，等 `run_harness.py` 来消费。

### 3.4 离线评估回放（Phase 3 eval harness）

`eval_cli` 的默认 `--db` 已和 `run_harness.py` 对齐到 `storage/macro_agents.sqlite3`，所以直接跑即可：

```bash
python -m harness.eval_cli --window-days 7                 # 文本报告
python -m harness.eval_cli --window-days 30 --format json  # JSON
```
输出 5 个指标：narrative_stability / evidence_precision / challenge_hit_rate / latency_seconds / tokens_used。
> 只有当你跑 `run_harness.py` 时用 `--db` 指定了别的库，这里才需要传同一个值。

### 3.5 Streamlit 监控 UI
```bash
streamlit run streamlit_app.py
```
看 DB 里的新闻仓库、叙事主线/分支、ingestion QA 等。

---

## 4. 典型工作流（实时数据 → 持续叙事）

```bash
# 1) 抓新闻入库
python run_live_ingest.py
# 2) 让 Harness 消费、更新叙事（可反复跑；已处理的不会重复处理）
python run_harness.py
# 3) 看结果
streamlit run streamlit_app.py
# 4) 周期性评估叙事质量
python -m harness.eval_cli --window-days 7
```

---

## 5. 验证 LLM 真的接上了（不泄露 key）

跑一次 harness 后，看最近 session 的事件里有没有 LLM 痕迹 / token 计数：
```bash
python -m harness.eval_cli --window-days 1 --format json
# tokens_used > 0 说明 LLM 真的被调用了；=0 说明走的是规则兜底（没配 key 或调用失败回退）
```
想确认 coordinator 是否建了带计量的客户端，可在 Python 里：
```python
from harness.coordinator import HarnessCoordinator
c = HarnessCoordinator(db_path="storage/macro_agents.sqlite3")
print(type(c._analyst._llm_client).__name__)   # MeteredLLMClient = 已接 LLM；NoneType = 规则兜底
```

---

## 6. 故障排查

| 现象 | 原因 / 解决 |
|------|------------|
| `ModuleNotFoundError: No module named 'yaml'`（7 个测试收集失败）| 没装依赖 → `pip install -r requirements.txt` |
| `import harness/llm 失败` | 不在项目根跑，或 `conftest.py` 没生效 → 回到 `macro_agents/` 根目录跑 |
| 填了 `.env` 但 LLM 没生效 | shell 里已 export 了同名变量盖过 `.env`（见 §2 坑1）；或 key 为空 → 退回规则 |
| `tokens_used` 一直是 0 | 没配 key（走规则），或 LLM 调用失败被兜底吞掉；检查 `LLM_BASE_URL`/`LLM_MODEL`/key |
| Finnhub 报 `requires env var 'FINNHUB_API_KEY'` | `.env` 或 shell 里没设 Finnhub key |
| run_harness 跑完 0 pending | DB 里没有 `pending` 新闻 → 先 `run_live_ingest.py` 或 `demo_runner.py` 灌数据 |
| eval_cli 报告 session_count=0 | 该时间窗内没有 completed session；或 `run_harness` 跑时用了自定义 `--db`，eval 也要传同一个 |
| LLM 返回坏 JSON / 超时 | 系统会**自动回退规则**，不会崩；想排查就看 `LLM_BASE_URL` 是否可达 |

---

## 7. 一句话速记

- **测试**：`pip install -r requirements.txt` → `pytest -q`（离线，不需 key）
- **配 key**：都进 `.env`（注意 shell export 会盖过它）
- **跑系统**：`demo_runner.py`（离线全链路）/ `run_harness.py`（消费 DB + LLM）/ `run_live_ingest.py`（抓数据）/ `eval_cli`（评估）/ `streamlit`（看板）
- **没配 key 也能跑**：自动退回 V1.3 规则版
