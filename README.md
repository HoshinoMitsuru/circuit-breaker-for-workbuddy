# workbuddy-points-circuit-breaker

面向 WorkBuddy 的积分熔断工具：自动检测某一工作空间下设单一任务、或某一工作空间总的积分消耗，达到软熔断线（默认 90%）提示收尾、达到硬熔断线（默认 100%）停止任务。

数据源为 **Windows UIAutomation 读取 WorkBuddy 界面每条 AI 回复页脚「共消耗 X Hy3」**，辅以 OCR 兜底。默认**不设上限**（`budget <= 0` 即置空，仅监控不熔断），可按需为全局 / 工作空间 / 单任务设置正整数上限。

## 功能特性

| 能力 | 说明 |
|---|---|
| 两级熔断 | WARN（≥90%）软熔断：状态文件 + Windows 通知；TRIP（≥100%）硬熔断：停止生成 + 关闭任务会话 |
| 三级预算 | 全局默认 → 工作空间 → 单任务，逐级继承；`budget <= 0` 视为无上限 |
| 页脚指纹累计 | 按页脚文本去重，每条新 AI 回复把其单轮消耗累加进总额，不重复计、不暴涨 |
| 双读取器 | UIA 优先（`uiautomation`），OCR 兜底可选（`pytesseract`） |
| 只读定位 | `discover` 子命令扫描界面元素，输出/写入 reader 与关闭控件 locator |
| 安全红线 | 硬熔断绝不关 WorkBuddy 主窗口；排除标题栏系统关闭；多候选不开盲盒 |

## 环境要求

- Windows + Python >= 3.10
- 依赖：`uiautomation>=2.0.29`、`comtypes>=1.2.1`；OCR 兜底可选 `pytesseract` + `pillow`（另需本机安装 tesseract）
- **WorkBuddy 必须带无障碍 flags 启动**，否则界面无障碍树为空壳（`E-UIA-002`）。完全退出后用：

```
WorkBuddy.exe --force-renderer-accessibility ^
  --disable-features=CalculateNativeWinOcclusion ^
  --disable-backgrounding-occluded-windows ^
  --disable-renderer-backgrounding ^
  --disable-background-timer-throttling
```

并保持主窗口**可见、不要最小化**（最小化会被 renderer 节流，读到空壳/陈旧树）。

## 安装

```
# 方式一：可编辑安装（带 CLI 入口 circuit-breaker）
pip install -e .
pip install -e .[ocr]     # 含 OCR 兜底（可选）

# 方式二：直接以模块运行（无需安装）
python -m circuit_breaker.cli <subcommand>
```

## 快速开始

```
# 1. 只读定位积分元素与关闭控件，写入配置
python -m circuit_breaker.cli discover --apply

# 2. 查看配置（确认预算 / 阈值 / reader）
python -m circuit_breaker.cli config --show

# 3. 单次只读检测（不触发任何熔断动作）
python -m circuit_breaker.cli check --workspace myws --task t1 --no-act

# 4. 守护：每 5 秒检测 myws 下任务 t1，触发即熔断
python -m circuit_breaker.cli watch --workspace myws --task t1

# （可选）为某工作空间/任务设上限；0 = 无上限
python -m circuit_breaker.cli config --set-task-budget myws t1 300
```

## 命令参考

子命令由 `circuit_breaker/cli.py::build_parser` 定义。

| 命令 | 作用 | 关键参数 |
|---|---|---|
| `check` | 单次检测并打印 verdict（agent 可每轮调用） | `--workspace`(必填) `--task` `--no-act`(只检测不触发动作) |
| `watch` | 守护轮询（自动检测 + 熔断） | `--workspace`(必填) `--task` `--interval`(秒) `--once`(跑一轮就退) |
| `discover` | 只读定位积分元素 + 关闭控件，输出建议 locator | `--apply`(写入 config.json) |
| `config` | 查看/修改配置 | `--show` `--set-default-budget` `--set-workspace-budget` `--set-task-budget` `--set-thresholds` `--set-keyword` `--set-reader-field` |
| `status` | 查看状态文件 | `--workspace` `--task` |
| `reset` | 清空累计/状态文件（消除陈旧高总额导致的误断） | `--all` / `--workspace` `--task` |

## 配置说明

运行时配置位于 `<数据目录>/data/config.json`，路径由 `circuit_breaker/config.py::resolve_home` 解析（环境变量 `CB_HOME` 优先，其次源码/exe 旁 `data/`，不可写时回退 `%LOCALAPPDATA%`）。

| 键 | 默认 | 说明 |
|---|---|---|
| `default_budget` | `0` | 全局默认预算；`<=0` 无上限，正整数=积分上限 |
| `thresholds.warn` / `trip` | `0.9` / `1.0` | 软/硬熔断阈值（占预算比例） |
| `workspaces.<ws>.budget` | 继承默认 | 工作空间预算（`config.py::Config.workspace_budget`） |
| `workspaces.<ws>.tasks.<id>.budget` | 继承工作空间 | 单任务预算（`config.py::Config.task_budget`） |
| `reader.mode` | `uia` | `uia` / `ocr` / `auto`（auto=UIA 失败 OCR 兜底） |
| `reader.keyword` / `value_regex` | `共消耗` / `共消耗\s*(\d[\d,]*)` | 页脚定位与数值提取 |
| `reader.cumulative` | `false` | `false`=页脚为单轮消耗；`true`=页脚为会话累计 |
| `soft.*` | — | 软熔断送达：状态文件 / 通知 / 可选注入消息 |
| `hard.close_task_window` | `true` | 硬熔断是否关闭任务会话 |
| `hard.close_locator` | `{"name_contains":"关闭"}` | 任务会话关闭控件定位 |
| `poll_interval` | `5` | 守护轮询间隔（秒） |

> **无上限语义**：`budget <= 0` 一律视为无上限，状态机恒 NORMAL、永不触发熔断（`circuit_breaker/breaker.py::Breaker.evaluate`）；正整数才是真实上限。

## 技术结构

```
workbuddy-points-circuit-breaker/
├── circuit_breaker/
│   ├── breaker.py          # 熔断状态机
│   ├── config.py           # 配置 / 路径解析 / 三级预算
│   ├── ui.py               # 窗口查找与无障碍树遍历基础
│   ├── monitor.py          # 守护轮询，串联读取→累计→判定→动作
│   ├── discover.py         # 只读定位积分元素与关闭控件
│   ├── errors.py           # 错误码目录（一码一根因）
│   ├── cli.py              # CLI 入口（6 个子命令）
│   ├── reader/
│   │   ├── uia_reader.py   # UIA 读取器
│   │   └── ocr_reader.py   # OCR 兜底读取器
│   └── actions/
│       ├── soft.py         # 软熔断动作
│       ├── hard.py         # 硬熔断动作
│       └── notify.py       # Windows 通知（MessageBoxTimeoutW）
├── data/
│   └── config.json         # 运行时配置（含已发现 reader locator）
└── pyproject.toml
```

| 模块 | 职责 | 关键实现 |
|---|---|---|
| `breaker.py` | NORMAL→WARN→TRIP 状态机 | `BreakerState`、`Verdict`、`Breaker.evaluate`；`budget<=0` 短路返回 NORMAL |
| `config.py` | 配置与三级预算 | `resolve_home`（路径单一事实来源）、`Config.workspace_budget` / `task_budget` |
| `ui.py` | 窗口与树遍历 | `find_workbuddy_window`（返回 ok/no_process/not_visible）、`dfs_walk`（文档序 DFS）、`parse_int` |
| `reader/uia_reader.py` | 读页脚数值 | `UIAReader.read_latest`：keyword+regex 命中所有页脚，取文档序最后一条（最新回复） |
| `reader/ocr_reader.py` | OCR 兜底 | `OCRReader.read_latest`（截图+pytesseract，接口与 UIA 一致） |
| `monitor.py` | 守护与串联 | `check_once` / `run`、`_accumulate`（页脚指纹去重累计）、同码错误 60s 抑制 |
| `discover.py` | 只读定位 | `discover(config, apply)`：扫描候选文本，优先锁定「共消耗」页脚，`--apply` 写配置 |
| `actions/soft.py` | 软熔断 | `soft_fuse`：写状态文件 + 通知 +（可选）`_inject` 注入聊天提示 |
| `actions/hard.py` | 硬熔断 | `hard_fuse`：写状态 + 通知 + `_stop_generating` + `_close_task`；`_is_system_close` 排除系统关闭 |
| `actions/notify.py` | 通知 | `notify`：daemon 线程内 `MessageBoxTimeoutW`，置顶、8 秒自动关闭、不阻塞主循环 |
| `errors.py` | 错误码目录 | `CATALOG`、`emit`：一码一根因，fixes 给可执行动作 |
| `cli.py` | CLI 入口 | `build_parser` / `main` |

**数据流**：`UIAReader.read_latest` 读最新页脚 `(value, text)` → `monitor._accumulate` 按页脚指纹去重累加（单任务 `.cb_task_<ws>_<task>.json`、工作空间 `.cb_ws_<ws>.json`）→ `Breaker.evaluate` 判定 NORMAL/WARN/TRIP → `soft_fuse` / `hard_fuse` 执行动作。

## 安全设计

- `actions/hard.py::_is_system_close`：判断「关闭」按钮是否位于标题栏（与最小化/最大化同排），是则一律跳过——**绝不关整个应用**。
- `actions/hard.py::_close_task`：只匹配非系统「关闭」候选；候选为 0 → 报 `E-ACT-006` 仅停止生成+通知；候选 > 1 → 不开盲盒，抛错请人工确认。
- `close_locator` 未配置时硬熔断只停止生成 + 通知，不关窗口（保守默认）。
- 本工具**不联网、不采集数据**；所有状态仅落本地 `data/` 目录。

## 错误码判别表

目录 `circuit_breaker/errors.py::CATALOG`，统一输出 `errors.py::emit`。一个码只对应一个根因。

| 码 | 含义 | 典型根因 | 怎么办 |
|---|---|---|---|
| `E-WIN-001` | 找不到 WorkBuddy 窗口 | WB 未启动 / 仅缩在托盘 / exe 名不匹配 | 确认 WB 已启动可见；或改 `reader.exe`/`title` |
| `E-UIA-002` | 无障碍树为空壳 | 启动未带 `--force-renderer-accessibility`；或窗口最小化被节流 | 带 flags 重启并保持窗口可见 |
| `E-READ-003` | 读不到积分数值 | keyword/value_regex 与界面不符；或积分是图片需 OCR | 跑 `discover` 重新定位；或开 OCR 兜底 |
| `E-READ-004` | 数值无法解析为非负整数 | 文本混入非数字；捕获组取空 | 检查 `value_regex` 只捕获数字；核对 `field` |
| `E-CFG-005` | 配置写入失败（目录不可写） | 装在只读目录；`CB_HOME` 指向只读 | 用 `CB_HOME` 指向可写目录 |
| `E-ACT-006` | 硬熔断关闭任务窗口未配置 locator | `close_locator` 为空 / 多候选不确定 | 跑 `discover --apply`；或临时 `close_task_window=false` |
| `E-GEN-012` | 未分类异常 | 未知运行时错误 | 看详情里的异常类型/消息 |

## 已知限制

- WorkBuddy 无积分 API/hooks，只能 UIA 读界面，强依赖 flags 与可见窗口。
- 页脚数值可能显示为 0（部分会话实测），此时靠真实消耗自然触发不了熔断；验证动作链路可临时把阈值调 0 强制触发。
- 工作空间「总」消耗为本地近似：WB 界面不显示总量，`.cb_ws_<ws>.json` 由本工具本地累计；单任务口径精确。
- 若出现无故反复熔断，多为陈旧累计状态文件所致，先 `reset --all` 再 `check --no-act` 确认起点为 0/NORMAL。
