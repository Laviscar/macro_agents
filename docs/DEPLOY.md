# 部署到服务器常驻运行(零基础版)

假设:一台 **Ubuntu Linux 服务器**(22.04/24.04),你能用 `ssh` 登录。其他系统见末尾备注。

## ⚠️ 部署前两个关键前提
1. **网络可达性**:服务器要能访问你用的 API。
   - DeepSeek(`api.deepseek.com`)国内外服务器一般都能直连。
   - **Finnhub / FRED / NYT / ECB 是境外站**——如果服务器在**中国大陆**,可能慢或不通(deepseek 没问题)。海外服务器全都没问题。
   - 本地那条 `NO_PROXY=api.deepseek.com` 是为你 mac 上的 Clash 代理设的;**干净服务器没挂代理就不用设**(设了也无害)。
2. **仓库是否私有**:如果 GitHub 上 `Laviscar/macro_agents` 是私有仓库,`git clone` 需要认证(PAT 或 SSH key,见 step 2)。公开仓库则直接 clone。

---

## Step 0 — 登录服务器
```bash
ssh 你的用户名@服务器IP
```

## Step 1 — 装基础环境
```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
python3 --version      # 需要 ≥ 3.11;若低于,装 deadsnakes:
# sudo add-apt-repository ppa:deadsnakes/ppa -y && sudo apt install -y python3.12 python3.12-venv
```

## Step 2 — 拉代码
**公开仓库**:
```bash
cd ~
git clone https://github.com/Laviscar/macro_agents.git
cd macro_agents
```
**私有仓库**(二选一):
- 用 PAT:`git clone https://<你的GitHub用户名>:<你的PAT>@github.com/Laviscar/macro_agents.git`
- 或先在服务器生成 SSH key(`ssh-keygen -t ed25519`)→ 把 `~/.ssh/id_ed25519.pub` 加到 GitHub 的 Deploy Keys → `git clone git@github.com:Laviscar/macro_agents.git`

## Step 3 — 建虚拟环境 + 装依赖
```bash
cd ~/macro_agents
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## Step 4 — 配 `.env`(密钥,手动建,**不进 git**)
`.env` 不会随代码上传(已 gitignore)。两种方式:

**A. 从本地安全拷过去**(推荐,免得重填):在你 **mac 本地**跑:
```bash
scp .env 你的用户名@服务器IP:~/macro_agents/.env
```
**B. 在服务器上新建**:
```bash
cp .env.example .env
nano .env     # 填:LLM_*_API_KEY(三层)/ FINNHUB_API_KEY / FRED_API_KEY
```
确保有这几行(没代理就别加 NO_PROXY):
```
RUN_LOOP_NEWEST_FIRST=true
# 省钱档(按需调):
RUN_LOOP_ANALYSIS_SECONDS=1800
RUN_LOOP_ANALYSIS_BATCH=6
```

## Step 5 — 冒烟验证(确认环境通)
```bash
source .venv/bin/activate
python -m pytest -q              # 可选,~3min,全绿说明环境 OK
python run_loop.py --once        # 跑一轮:看有没有抓到新闻、有没有报错
```
看到 `source_poll_succeeded`(抓取成功)+ 没有 traceback 就 OK。Ctrl-C 可中断。

## Step 6 — 常驻运行(systemd,自动重启 + 开机自启)
建服务文件(把 `你的用户名` 换成实际用户名,如 `ubuntu`):
```bash
sudo nano /etc/systemd/system/macro-agents.service
```
粘贴(注意改两处路径里的用户名):
```ini
[Unit]
Description=Macro Agents run_loop
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=你的用户名
WorkingDirectory=/home/你的用户名/macro_agents
ExecStart=/home/你的用户名/macro_agents/.venv/bin/python run_loop.py
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```
> 不用配 EnvironmentFile —— 程序启动时自己从 WorkingDirectory 的 `.env` 读密钥。
启动:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now macro-agents
sudo systemctl status macro-agents          # 看是否 active (running)
journalctl -u macro-agents -f               # 实时日志;找 "freshness" 事件看时效
```

## Step 7 —(可选)看 Streamlit 界面:SSH 隧道最安全
在服务器跑(tmux 里或第二个 systemd):
```bash
cd ~/macro_agents && source .venv/bin/activate
streamlit run streamlit_app.py --server.address 127.0.0.1 --server.headless true
```
在你 **本地 mac** 开隧道,然后本地浏览器访问 `http://localhost:8501`:
```bash
ssh -L 8501:localhost:8501 你的用户名@服务器IP
```
> 直接开公网端口要加密码/防火墙,先用隧道最省心。

## 日常运维
```bash
journalctl -u macro-agents -f               # 看日志(含 freshness 摘要:数据多新、积压多少)
sudo systemctl restart macro-agents         # 改了 .env 后重启生效
cd ~/macro_agents && git pull && sudo systemctl restart macro-agents   # 更新代码
```
- **成本**:主要在分析(推理模型)。盯 DeepSeek 用量;贵就调大 `RUN_LOOP_ANALYSIS_SECONDS` / 调小 `RUN_LOOP_ANALYSIS_BATCH`。
- **别同时**在服务器跑 `run_harness.py`(会和 run_loop 重复消费)。
- 委员会**人工召开**,常驻期间不自动烧 LLM。

## 其他系统
- **Windows 服务器**:用 WSL2(里面就是 Ubuntu,照上面做)或 NSSM 把 `python run_loop.py` 注册成 Windows 服务。
- **还没买服务器**:挑个 1–2GB 内存的小 VPS 即可(本项目本地计算很轻,瓶颈是 API 调用)。海外节点对 Finnhub/FRED 更友好。
