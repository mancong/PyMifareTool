# PyMifareTool 再度审阅 + MifareClassicTool 功能合并可行性评估与分阶段实施指导书

> 审阅对象 A（被审阅/被改造方）：`D:\Workspace\Works\Other\PyMifareTool`（Python 3.12 + PyQt6 桌面上位机）
> 审阅对象 B（供体方）：`D:\Workspace\Works\Github\MifareClassicTool`（Mifare Classic Tool，简称 MCT，Android/Java，v4.3.1，GPLv3）
> 审阅方式：全量源码只读直读 + 仓库自带样例文件二进制实证 + 本机实测运行测试套件。所有结论均带 `文件:行号` 或实测命令证据。
> 本文件是**指导书**，不是变更已经执行的结果报告；文中标记的「现状」均为本次实测事实。

---

## 0. 摘要与最终结论（TL;DR）

### 0.1 四个直接答复

| 问题 | 答复 |
|---|---|
| MCT 的功能能否合并进 PyMifareTool？ | **能，但不能"搬运式"合并。** MCT 约 80% 的功能是纯逻辑（文件格式、Key Map、Access Condition、Value Block、BCC、Dump 校验/差分/编辑），可移植为 Python；约 20% 依赖 Android `MifareClassic`/`NfcA` API，必须用桌面端读写器适配层重写。 |
| 最大的两个拦路石是什么？ | **① 许可证**：MCT 是 **GPLv3**（`LICENSE.txt:1`），PyMifareTool 当前**无任何许可证文件**（实测 `Test-Path LICENSE` = False）。一旦移植 MCT 代码，PyMifareTool 成为衍生作品，必须以 GPLv3 分发并公开源码。**② 硬件**：当前板载读卡器是**单向 UID 广播器**，物理上不响应任何下行读写/认证指令（`core/card_service.py:229-238`、`README.md:25`）。MCT 的核心价值（Key Map 破解、整卡读写、魔术卡改 UID、Value Block 运算）**没有双向读写器就无法实现**。 |
| 建议怎么走？ | **双轨制**：Track A（**立即启动，不依赖任何新硬件**）交付"文件格式 + 密钥体系 + 分析编辑"完整对标件；Track B（**硬件到位后**）交付真机读写与攻击。许可证在 Phase 0 一次性定案（推荐：接受 GPLv3 并合规化，而不是冒险 clean-room）。 |
| 本轮最该立刻修的是什么？ | **不是缺功能，而是已有的危险代码**：① 写卡时**未读取的块会被当作 `00…00` 写入真卡**（静默毁卡，`core/card_service.py:284-285` 从不检查 `BlockState`）；② **扇区尾块被无条件写入**，非法控制字可永久锁卡；③ **测试会向生产库 `cards.db` 写入真实刷卡记录**（`tests/run_tests.py:379-403`）。这三项都在 Phase 0 处理（见 §2.5）。 |

### 0.2 合并后的能力画像（目标态）

```
                    ┌───────────────────────────────────────────────┐
                    │  PyMifareTool v2  (统一上位机)                 │
                    └───────────────────────────────────────────────┘
   Tier 0 离线层     │ .mct/.eml/.mfd/.bin/.json/.keys/keys.bin 全格式 │
  (现在就能做)       │ Key Map 模型 · Dump 校验/纠错 · Diff · AC 工具 │
                    │ Value Block 工具 · Tag Info · 发卡流水(已有)   │
                    ├───────────────────────────────────────────────┤
   Tier 1 广播层     │ 当前硬件：只上报 UID → Hero 看板/流水/建档    │
  (现在就能做)       │ 能力探测 + 明确降级提示（已有雏形）           │
                    ├───────────────────────────────────────────────┤
   Tier 2 双向层     │ 新增读写器（PC/SC·nfcpy-PN532·libnfc CLI）    │
  (需要硬件)         │ 整卡读/写 · Key Map 破解 · 魔术卡 UID · 攻击   │
                    └───────────────────────────────────────────────┘
```

### 0.3 本轮审阅发现的严重问题（按优先级）

| 编号 | 级别 | 问题 | 证据 |
|---|---|---|---|
| N-1 | **P0** | 2K 卡（2048 字节）Dump 被静默截断成 1K，丢一半数据 | `core/dump_model.py:375-388`：`>=1024` 即按 1K 处理并 `content[:1024]` |
| N-2 | **P0** | 无许可证 + 上游 GPLv3 + 无 git 仓库 → 法务与版本失控双风险 | 实测无 `LICENSE`；`MifareClassicTool/LICENSE.txt:1`；`git log` 报 not a repository |
| N-3 | **P1** | `core/adapters/` 三个适配器是**死代码**，全项目无任何引用 | 全仓 grep `Adapter` 仅命中 `core/adapters/*` 自身 |
| N-4 | **P1** | 4K 卡（S70）在硬件路径彻底错位：扇区 32–39 应为 16 块，代码硬编码 4 块 | `core/card_service.py:126,180,202,265,277` |
| N-5 | **P1** | `.mct` 写出时把"未读取"扇区写成全 0，且不输出 MCT 的 `NO_DATA`/`*` 语义行 → 往返污染数据语义 | `core/dump_model.py:348-354`（对比 `MCReader.java:51,55`、`ReadTag.java:132-138`） |
| N-6 | **P1** | `.mct` 载入按行序累加块号，某扇区缺行会**整体错位**，无扇区块数校验 | `core/dump_model.py:283-322`（对比 `Common.java:1443-1489`） |
| N-7 | **P1** | `LibnfcCliAdapter.authenticate()` 无条件 `return True` → 假成功 | `core/adapters/libnfc_adapter.py:71-73` |
| N-8 | **P1** | Diff 工具硬编码 64 块、`block_idx//4` 推扇区 → 4K/2K/Mini 全错 | `ui/dump_diff.py:123,128`；且文件过滤器漏了 `*.mct`（`:94`） |
| N-9 | **P2** | 密钥字典存在**两份互不同步**的硬编码副本，且 UI 字典页只读、无法喂给破解引擎 | `core/card_service.py:20-37` vs `ui/dictionary_tools.py:16-33`；`ui/dictionary_tools.py:326-343` |
| N-10 | **P2** | `requirements.txt`/`AGENTS.md`/README 与实测状态不一致（AGENTS 称 15 项测试，实测 27 项） | `AGENTS.md:111-114`；实测 `Ran 27 tests ... OK (skipped=1)` |
| N-11 | **P2** | 工程卫生：`cards.db`(28KB 运行库)入库、`.venv` 非隔离、`matplotlib-e___mire` 损坏目录（访问被拒） | 实测顶层目录清单 |
| N-12 | **P2** | `.txt` 回退解析路径仍按文件行序重新编号块；无 BCC/Block0 合法性校验（MCT 有 `isValidBlock0`） | `core/dump_model.py:423-433`；`Common.java:1620-1624` |
| N-13 | **P0** | **写卡会把"未读取/读取失败"的块当作 `00…00` 写进真卡** → 部分读取的 dump + 一键写卡 = 静默清零实体卡 | `core/card_service.py:284-285` 从不检查 `BlockState`；UI 仅一句"确定要写入吗"（`ui/sector_table.py:452-465`） |
| N-14 | **P0** | **扇区尾块（Key A/AC/Key B）被无条件写入**，写前不强制校验控制字合法性 → 可永久锁卡 | `core/card_service.py:277-290`；MCT 侧有 `isWritableOnPositions` + 问题清单二次确认（`WriteTag.java:1023-1245`） |
| N-15 | **P0** | **测试污染生产数据库**：`MainWindow` 用相对路径 `cards.db`，GUI 测试真实调用 `record_swipe` | `tests/run_tests.py:379-403` → `ui/main_window.py:201` → `core/card_db.py:12`（实测跑完生成 20KB `cards.db`） |
| N-16 | **P1** | **取消操作后 UI 永久卡死**：内层循环 `return` 不发射 `sig_finished` | `core/card_service.py:130-131,140-142,185-186`；`ui/sector_table.py:444-447` 的进度面板/「正在中止」永不消失 |
| N-17 | **P1** | **破解结果无法到达 UI**：`sig_sector_cracked` 无任何连接点，`_on_worker_finished` 丢弃非 `MifareDump` 结果 → 字典破解按钮只产出日志文本 | `core/card_service.py:51,154`；`ui/sector_table.py:432-441` |
| N-18 | **P1** | `BroadcastSerialAdapter.scan_card()` 恒返回 `None`（`last_card_info` 从未被赋值）→ 适配器即使接线也"永远找不到卡" | `core/adapters/broadcast_adapter.py:14,33-35` |
| N-19 | **P1** | 写卡路径中 `authenticated` 计算后从未使用 → 认证失败仍继续写块 | `core/card_service.py:268-275` |
| N-20 | **P2** | 固件探测的指令标签与实际 CMD 不符（把 `0xF0` 标成 `0x10`、`0x61` 标成 `0x06` 且只发 1 字节）→ 自检结论不可信 | `core/card_service.py:308,311`；`core/protocol.py:34,126-130` |
| N-21 | **P2** | 导出菜单"导出 MCT 格式 (\*.mct)"与 txt 共用回调，默认文件名 `card_dump.txt` → 不手改后缀就导成 `.txt` | `ui/sector_table.py:72-73,533-539` |
| N-22 | **P2** | `cards.db` 含 **3 张真实卡 UID + 83 条刷卡流水**（含原始报文）随仓库分发；`scratch/v2/user_card_from_mct.mct` 为真实卡 dump | 实测 SQL 查询 `cards.db` |
| N-23 | **P2** | DB schema 漂移且无迁移机制：实测库 `swipe_count INTEGER DEFAULT 0` vs 代码 `DEFAULT 1`；无 `user_version`/ALTER | `core/card_db.py:23-45`；实测 `sqlite_master` |
| N-24 | **P2** | `REVIEW_REPORT.md` 的 SHA256 基线**全部失效**（12 个文件无一相符）——因为无 git，改动无法追溯 | 实测重算；`REVIEW_REPORT.md:11-20` |
| N-25 | **P3** | 死代码：`protocol.py` 的 10 个 `build_*`、`send_command`、`sig_response`、`delete_single_log`（`docs/change/README.md:171` 却声称已支持单条删除） | `core/protocol.py:64-130`、`core/serial_worker.py:72-75,22,167`、`core/card_db.py:173-181` |

**上一轮 `REVIEW_REPORT.md` 提出的 P0/P1 整改，经核验基本属实**（详见 §2.2），但整改后引入了新的**结构性缺陷**（N-3/N-4 属于"加了抽象层却没接线"、"加了 4K 模型却没接硬件路径"），这就是本轮审阅的主要新增价值。

---

## 1. 审阅范围、方法与证据等级

### 1.1 实读清单（第一手）

PyMifareTool：`core/protocol.py`、`core/serial_worker.py`、`core/dump_model.py`、`core/card_db.py`、`core/card_service.py`、`core/attack_runner.py`、`core/adapters/*`、`ui/main_window.py`、`ui/sector_table.py`、`ui/dump_diff.py`、`ui/dictionary_tools.py`、`tests/run_tests.py`、`main.py`、`README.md`、`AGENTS.md`、`requirements.txt`、`REVIEW_REPORT.md`、`MIFAREONETOOL_FEATURE_INVENTORY.md`、`docs/*`。

MCT：`LICENSE.txt`、`CHANGELOG.txt`、`MCReader.java`、`Common.java`、`ImportExportTool.java`、`ReadTag.java`、`WriteTag.java`、`app/src/main/res/menu/*.xml`、`app/src/main/assets/key-files/*.keys`、`tools/dump-file-converter/eml2mct.py`、`tools/example-files/example-dump-file.txt`、`tools/example-files/example-dump-file.raw`、`tools/example-files/example-key-dump.txt`、`app/build.gradle` 等。

### 1.2 证据等级

| 等级 | 含义 | 本文中的用法 |
|---|---|---|
| **E1 实测** | 本机执行命令/读源码得到的可复现事实 | `实测` 前缀，附命令或行号 |
| **E2 源码** | 直接读到的上游实现 | 附 `文件:行号` |
| **E3 推断** | 由 E1/E2 推导，未直接验证 | 标 `推断` |
| **E4 未确认** | 无法在本次只读审阅中确认 | 明确写 `未确认`，禁止当作事实使用 |

### 1.3 本机实测基线

```text
Python 3.12.10 | PyQt6 6.11.0 | PyQt6-Qt6 6.11.2 | pyserial 3.5
QT_QPA_PLATFORM=offscreen python tests/run_tests.py
  → Ran 27 tests ... OK (skipped=1)   exit=0
  → 跳过项：物理 COM3 未插入（tests/run_tests.py:527）
  → 系统当前检测到的串口: []（无硬件在场）
pip download nfcpy --no-deps  → 可解析到 nfcpy-1.0.4（PyPI 可达）
```

> 结论：**当前环境可跑通全套测试，但没有任何真实读卡器在场**，因此所有"真机"结论都不能在本轮验证，只能给出验证方案。

---

## 2. PyMifareTool 再度审阅

### 2.1 现状快照（模块级）

| 模块 | 文件 | 实际职责 | 完成度 |
|---|---|---|---|
| 协议层 | `core/protocol.py` (436 行) | AA BB 帧构建/解析、9 种 CMD、4/7/10 字节 UID 换算、`AccessBitsEncoder`/`AccessBitsDecoder`（8 种数据块 + 8 种尾块权限表） | **可用**，是本项目最扎实的部分（`tests/run_tests.py:38-127` 覆盖） |
| 串口层 | `core/serial_worker.py` (183 行) | `QThread` 异步收发、DTR/RTS=False 红线、`send_and_wait` 请求-响应、帧分发 | **可用**（仅针对广播帧+假想双向固件） |
| 数据模型 | `core/dump_model.py` (476 行) | 1K/4K 内存模型、三态块状态、BCC/AC 校验与纠错、`.mct` 读写、`.dump/.mfd/.bin/.txt` 读写 | **半成品**：缺 Mini/2K；`.mct` 语义不完整 |
| 业务线程 | `core/card_service.py` (384 行) | 字典破解、整卡读、整卡写、固件探测 | **结构和信号齐全，但错误处理与 4K 寻址有缺陷**；且**未使用适配层** |
| 攻击执行 | `core/attack_runner.py` (113 行) | `QProcess` 调用 `mfoc.exe`/`mfcuk.exe`/`mfdetect.exe` | **桩**：`nfc-bin/` 目录在仓内不存在 |
| 适配层 | `core/adapters/*` (240 行) | 抽象基类 + 广播适配器 + libnfc CLI 适配器 | **死代码**（N-3） |
| 数据库 | `core/card_db.py` (184 行) | `cards` + `swipe_logs` 两表、流水增删、CSV 导出支撑 | **可用**，是上游 MCT 没有的增量 |
| UI | `ui/*.py` (~2050 行) | 左看板 + 4 Tab（扇区矩阵/Dump 对比/发卡管理/字典工具）+ 原生报文日志 | **可用**，暗黑 QSS 一致、无头可测 |
| 测试 | `tests/run_tests.py` (23.6KB) | 27 项，6 个测试类 | **真实有效**（无空 assert、无 `pass` 假测试） |

### 2.2 上一轮整改（`docs/change/README.md`）核验

| 上轮声称 | 核验结论 | 证据 |
|---|---|---|
| 【P0】底层协议与服务层契约错配已修 | **属实** | `core/protocol.py:207-227` 统一产出 `ok/status/status_code`；`core/card_service.py:353-384` 消费同一契约 |
| 【P0】`.txt` 导入静默篡改数据已修 | **属实但有残余** | 现在优先走 MCT 结构解析（`core/dump_model.py:397-399`），并要求 `>=64` 块（`:434`）；但纯 hexdump 回退路径仍按行序重编号（`:428,431`），若文件缺行仍会错位（N-12） |
| 【P1】硬件型号去虚化 | **属实** | `README.md:25` 自述"单向广播发卡器"；`core/card_service.py:229-238` 给出明确的降级话术 |
| 【P1】元数据键名/Wiegand34/多字节 UID | **属实** | `core/protocol.py:239-297` 完整实现 4/7/10 字节换算与 `card_type` 兼容键 |
| 【P1】串口线程竞态消除 | **属实** | `core/serial_worker.py:30-31,157-160` 用两把锁分隔 TX 与请求-响应 |
| 【P1】Access Bits 公式校准 | **属实** | `core/protocol.py:410-421` 位序与 NXP 一致，测试 `tests/run_tests.py:92-110` 断言出厂/只读控制字 |
| 【P2】离线能力对标 MifareOneTool | **部分**：有了 `.mct` 与纠错，但没有 `.eml/.json/.keys`，也没有 Key Map | 见 §4.2 |
| 【P2】硬件与攻击层拓展 | **仅骨架**：`attack_runner.py` 与 `libnfc_adapter.py` 均无可用后端 | `core/adapters/libnfc_adapter.py:20`（`bin_dir="nfc-bin"`，仓内无此目录） |

### 2.3 结构性问题详解（本轮新增）

#### N-3 适配层未接线（最关键的架构债）

`core/adapters/__init__.py` 导出了三个类，但全仓检索 `Adapter` 只命中适配层自身文件。也就是说：

- `CardOperationWorker.__init__(self, worker: SerialWorker, ...)`（`core/card_service.py:55-64`）**直接依赖 `SerialWorker` 具体类型**；
- `BroadcastSerialAdapter`（`core/adapters/broadcast_adapter.py`）、`LibnfcCliAdapter`（`core/adapters/libnfc_adapter.py`）**从未被 import**；
- 因此"接入 PN532/ACR122U"这件事在代码上**等于从未开始**。

**影响**：MCT 功能合并的第一前置条件（一个能读写扇区的抽象读卡器接口）目前不存在可用实现。

#### N-4 4K 寻址硬编码

`core/card_service.py` 三处关键循环仍假设"每扇区 4 块、尾块 = sector*4+3"：

```python
126:            trailer_block = sector * 4 + 3          # 破解
180:            trailer_block = sector * 4 + 3          # 读卡
202:            for b in range(4):                      # 读块
265:            trailer_block = sector * 4 + 3          # 写卡
277:            for b in range(4):                      # 写块
```

而 `core/dump_model.py:83-94` 已经正确实现了 4K 的 `get_sector_first_block/get_sector_block_count`。**模型对了，硬件路径没跟上**——只要对 S70 卡执行一次"一键读卡"，扇区 32 之后的全部读写都会打到错误块号上。

#### N-5/N-6 `.mct` 语义与 MCT 不互操作

MCT 用两个哨兵表达"读不到"：`NO_KEY = "------------"`（12 连字符）、`NO_DATA = "--------------------------------"`（32 连字符，`MCReader.java:51,55`），整扇区失败时写 `*No keys found or dead sector`（`ReadTag.java:137`）。且 MCT 对 dump 有**严格结构校验** `isValidDump`（`Common.java:1434-1489`，错误码 1–6）与 `isValidKeyFile`（`Common.java:1505-1544`）。

PyMifareTool 的 `save_mct`（`core/dump_model.py:345-358`）**无条件把所有块写成 16 字节 hex**，未读取的块会输出 `00000000000000000000000000000000`；`load_mct`（`:270-342`）见到 `----` 就把**整扇区**标为失败，且不感知 `*` 行、不校验每扇区块数。

**后果**：用 PyMifareTool 导出的 `.mct` 在 MCT 里打开后，"没读到的扇区"会变成"全零的真实数据"，用户可能据此写卡 → 破坏目标卡数据。这是**安全事故级**的互操作缺陷，必须最优先修。

#### N-1 2K 静默截断

```python
375: if len(content) >= self.S70_TOTAL_BYTES:   # >=4096 → 4K
380: elif len(content) >= self.S50_TOTAL_BYTES: # >=1024 → 1K，且 content[:1024]
```

2048 字节的 2K dump（MCT 明确支持 20/64/128/256 块，`ImportExportTool.java:575-581`）会命中 `elif`，被当成 1K 并**丢掉后 1024 字节**，全程无任何提示。`tests/run_tests.py` 只测 1K/4K，因此测试全绿也发现不了。

### 2.4 工程质量与卫生问题

| 项 | 现状 | 风险 |
|---|---|---|
| 版本控制 | **不是 git 仓库**（`git log` → `fatal: not a git repository`） | 无法回滚、无法 diff、无法协作；本次改造必须从 `git init` 开始 |
| 许可证 | 无 `LICENSE` 文件 | 默认保留全部权利，与 GPLv3 上游存在直接冲突风险（N-2） |
| `.gitignore` | 无 | `cards.db`、`.venv/`、`__pycache__/`、`scratch/` 会污染仓库 |
| 依赖声明 | `requirements.txt` = `pyserial>=3.5` / `PyQt6>=6.6.0`，**无版本上界、无锁定** | PyQt6 大版本升级可能破坏 QSS/枚举路径（本项目用了 `Qt.AlignmentFlag.*` 等新式枚举，尚安全） |
| 虚拟环境 | `.venv/` 存在但 `PyQt6` 实际解析到全局 `D:\Workspace\Development\Python\python_v3.12.10\...` | 环境不可复现 |
| 垃圾目录 | `matplotlib-e___mire/`（访问被拒，疑似 pip 中断残留） | 干扰 `Get-ChildItem -Recurse` 等一切工具链 |
| 文档漂移 | `AGENTS.md:111-114` 称 15 项测试；实际 27 项。目录树也未列 `core/adapters/`、`docs/change/`、`REVIEW_REPORT.md` | 后续 AI Agent 会依据错误上下文作业 |
| 隐私数据入仓 | `cards.db` 含 3 张真实卡 UID + 83 条流水（含原始报文）；`scratch/v2/user_card_from_mct.mct` 为真实卡 dump | 报名/合规风险；Phase 0 必须清库并改默认路径 |
| 编码污染 | `.idea/vcs.xml` 内为 GBK 二次编码残留（`鎺ㄩ€佽嚦鍙椾繚鎶ゅ垎鏀?`） | 违反 `AGENTS.md:119` 的 UTF-8 纯净约束 |
| 基线失效 | `REVIEW_REPORT.md:11-20` 的 12 个 SHA256 基线**无一相符**（实测重算） | 无 git → 任何改动不可追溯 |

### 2.5 最高风险：写卡安全（本轮最重要的发现）

> 这一组问题比"格式不互操作"严重得多：**它们会真实损坏用户的实体卡**，而且现有测试完全覆盖不到。

**(1) 未读取的块会被写成 `00…00`（N-13）**

```python
# core/card_service.py:277-290
for b in range(4):
    block_idx = sector * 4 + b
    if block_idx == 0 and not self.allow_block0_write:
        continue
    block_data = self.dump_to_write.get_block(block_idx)   # ← 从不检查 BlockState！
    success = self._write_single_block(block_idx, block_data)
```

`MifareDump` **已经实现了三态**（`BlockState.UNREAD / READ_OK / READ_FAILED`，`core/dump_model.py:13-16`），UI **也已经把三态渲染出来了**（`ui/sector_table.py:277-326`），但写卡路径**完全不读状态**。只要用户导入一个"部分扇区没读出来的 dump"再点"一键写卡"，那些块就会以 `00` 写入真卡——**这是静默的数据毁坏**。

MCT 的对应防线（三处，本项目一处都没有）：
* 写 dump 前用 `isValidDump(dump, false)`，含 `*`（死扇区）行的 dump **直接拒绝写入**（`WriteTag.java:758`）；
* 含 `-` 占位符的块在构建写入列表时**被丢弃**（`WriteTag.java:915,928`）；
* `isWritableOnPositions()` 逐块预检写权限码 0–6，并弹出 **Skip/Cancel 问题清单**（`WriteTag.java:1023-1245`）。

**(2) 扇区尾块被无条件写入（N-14）**

同循环对每个扇区的 block 3 照写不误。尾块同时承载 Key A / Access Bits(3B) / GPB / Key B，一旦写入非法控制字，卡片可被**永久锁死**（8 种 ACL 组合中 `111` 是"永不"）。项目把合法性检查做成了**用户手动点"纠错修复"**（`ui/sector_table.py:491-498`），而非**写前强制门禁**。

**(3) 认证失败不阻断写入（N-19）**

```python
# core/card_service.py:268-275
authenticated = False
for k_bytes in keys_bytes:
    if self._authenticate_sector(trailer_block, "A", k_bytes) is True:
        authenticated = True; break
    if self._authenticate_sector(trailer_block, "B", k_bytes) is True:
        authenticated = True; break
# ← authenticated 之后再未被使用
```

**合并/重构时的硬性要求**：写卡必须走"预检 → 展示问题清单 → 用户确认 → 分块写入 → 回读校验"五步，`BlockState != READ_OK` 的块默认跳过且计入报告。

### 2.6 扩展接缝清单（Phase 3/4 改动面的精确坐标）

| 接缝 | 精确位置 | 现状与用法 |
|---|---|---|
| 适配器抽象基类 | `core/adapters/base_adapter.py:11`（抽象方法 `:16,21,26,31,36,41,46,51,56`；钩子 `:60,64`） | 现成契约，可直接派生 `Pn532Adapter` / `PcscAdapter` |
| 适配器注册点 | `core/adapters/__init__.py:2-6` | 唯一注册处；**无工厂/注册表**，Phase 0.9 需新增 |
| 工作线程注入点 | `core/card_service.py:55-72`（`worker` 参数） | 鸭子类型；真实契约 = `is_connected()` + `send_and_wait(cmd,data,timeout)`（`ui/sector_table.py:402-408` 注入；`tests/run_tests.py:473-495` 的 `MockWorker` 即该契约） |
| 任务分发点 | `core/card_service.py:43-46`（OP_* 常量）→ `run():78-92` | 新任务 = 加常量 + 加 elif + 加 `_do_*` |
| **底层传输替换点（最关键）** | `core/card_service.py:353-364 _authenticate_sector`、`:366-373 _read_single_block`、`:375-384 _write_single_block` | 三处集中了全部硬件访问 → 换成适配器对象的最小改动面 |
| 帧协议扩展点 | `core/protocol.py:17-34`（CMD）、`:64-130`（build_*）、`parse_frame:171-236` | 新指令需三处同时登记 |
| 模型/格式扩展点 | `core/dump_model.py:270-342`（load_mct）、`:345-358`（save_mct）、`:363-449`（load_from_file，后缀判定 `:368,371,390,393`）、`:451-476`（save_to_file，`:452,454,458,460`） | Phase 1 要拆成 `core/dump_codec.py` |
| 写卡安全闸门（当前空缺） | `core/card_service.py:277-290` | 预检 + 块状态检查 + 尾块确认应挂在这里 |
| 攻击工具链接缝 | `core/attack_runner.py:21`（`bin_dir`）、`:29/45/56`（三个 run_*）、`:65`（QProcess）、信号 `:17-19` | 需补 HardNested（`cropto1_bs`/`collect` 采集与计算）并接 UI |
| UI Tab 注册点 | `ui/main_window.py:365-381`（构造 + addTab + tooltip）、`_init_signals:420-427` | 新页签在此登记 |
| 扇区矩阵扩展开关 | `ui/sector_table.py:389-413`（唯一 Worker 创建点，**从不传 `target_sectors`/`custom_keys`**）、`:432-441`（丢弃非 `MifareDump` 结果）、`:419-430` | 接破解结果可视化/密钥回灌必须改这三处 |
| 测试注册点 | `tests/run_tests.py:532-546 run_all_tests()`（六行 `addTests`） | 另注意硬编码绝对路径 `:30` 与 COM3 自检 `:519-529` |
| 无头测试范式 | `tests/run_tests.py:473-495 MockWorker` + `:470-516 Test05` | 已验证可行，可直接复制用于适配器/PN532 帧测试 |

> 依赖注入的两个既存"接缝契约"值得保留：`CardOperationWorker` 只要求鸭子类型（`is_connected` + `send_and_wait`），`Test05` 的 `MockWorker` 就是这个契约的最小实现。**Phase 3 把它升级为 `BaseReaderAdapter` 契约即可，不需要推倒重来。**

---

## 3. MifareClassicTool（MCT）解读

> **先纠正四处常见误解**（均经全仓 grep + 逐行实读确认，直接决定移植的工作量估算）：
>
> | 常见说法 | 代码事实 |
> |---|---|
> | MCT 支持 Gen1a/Gen2 魔术卡后门 | ❌ **只实现 Gen2（CUID）直写**（`CloneUidTool.java:272` → `writeBlock(0,0)`）。**Gen1a（`0x40`/`0x43` 后门）全仓无实现**；Gen3 APDU `90 F0 CC CC 10` 存在但被注释禁用（源码自述会让 4K 卡扇区 0–31 brick） |
> | Key Map 破解结果是 `-`/`1`/`2`/`3` 字符矩阵 | ❌ 4.3.1 **不存在任何字符矩阵**。真实语义：dump 里 `*`=死扇区、`-`=NO_KEY/NO_DATA；可写性用 `isWritableOnPositions` 的**整数码 0–6** |
> | BCC 支持 4/7/10 字节 UID | ❌ `calcBcc` **只接受 4 字节**（否则抛异常）；7/10 字节的 BCC1/BCC2 **上游没有实现**，由用户自带 |
> | `.eml` 是带 `0x1B` 头的二进制 | ❌ `.eml` 是**纯 ASCII 文本**（每行 32 hex 字符、无头无 magic） |
> | `MCReader.writeSector()` / `isKeyA()` | ❌ 不存在。对应物是 `useAsKeyB` 布尔参数 + `writeBlock(sector, block, data, key, useAsKeyB)` |

### 3.1 工程与构建

| 项 | 值 | 证据 |
|---|---|---|
| 名称/版本 | MifareClassicTool v4.3.1 | `CHANGELOG.txt:1-3` |
| 平台 | Android（Java，Gradle），Target SDK 35 | `CHANGELOG.txt:3`；`app/build.gradle` |
| 许可证 | **GNU GPL v3** | `LICENSE.txt:1` |
| 代码规模 | 24 个 Activity + 4 个核心类（`MCReader` 1273 行、`Common` 2284 行、`MCDiffUtils`、`package-info`） | 目录扫描 |
| 资源 | `assets/key-files/{std,extended-std,hotel-std}.keys`、`assets/help/help.html`、8 种语言 `values-*/strings.xml` | 目录扫描 |
| 配套工具 | `tools/dump-file-converter/{eml2mct,mct2eml,mfd2eml,eml2mfd}.py`、`tools/key-file-diff/`、`tools/mct-dump2prox-emulator/`、`tools/key-file-converter/` | 目录扫描 |

### 3.2 架构分层（这是理解"能不能搬"的关键）

```text
Activity 层 (UI / Android 生命周期 / Intent 跳转)
  ReadTag · WriteTag · DumpEditor · KeyEditor · KeyMapCreator · UidLogTool
  DiffTool · TagInfoTool · CloneUidTool · AccessCondition{,Decoder} · BccTool
  ValueBlock{,sToInt} · DataConversionTool · HexToAscii · ImportExportTool
  FileChooser · Preferences · BasicActivity(基类)
        │  ← 这一层 100% 依赖 Android（NfcAdapter、Intent、Toast、RecyclerView）
        ▼
核心逻辑层 (纯 Java，几乎不依赖 Android 之外的东西)
  MCReader      整卡/扇区/块 读写、Key Map 构建与合并、NO_KEY/NO_DATA 语义
  Common        键文件/dump 校验、hex 工具、Value Block 判定、Block0 合法性、差分
  MCDiffUtils   两 dump 差分
        │  ← 这一层是移植标的，但入口签名带 MifareClassic/Tag
        ▼
Android NFC 系统 API
  android.nfc.tech.MifareClassic / NfcA / Tag / Parcelable
        │  ← 这一层【不可移植】，必须替换为桌面端适配器
        ▼
读卡器硬件
```

**结论**：`MCReader` 的**算法**可移植，`MCReader` 的**对象生命周期与异常语义**不可移植；`Common` 里与 `Toast`/`Context` 耦合的校验函数需要"去 UI 化"后移植（错误码而非弹窗）。

### 3.3 文件格式规格（实证）

这是本次合并的最高价值区。以下全部来自 MCT 源码与仓库样例文件的**直接比对**。

#### （1）`.mct` —— 文本 dump，带扇区头

```
+Sector: 0
00000000000000000000000000000000
00000000000000000000000000000000
00000000000000000000000000000000
FFFFFFFFFFFFFF078069FFFFFFFFFFFF
+Sector: 1
...
```
* 证据：`tools/example-files/example-dump-file.txt:1-14`（实读原文）
* 扇区头正则：`^\Sector: [0-9]{1,2}$`（**必须有 `+`、必须一个空格、必须是 1–2 位数字**），扇区范围 `0..39`（`Common.java:1446-1461`）
* 块行：**恰好 32 个 `[0-9A-Fa-f-]` 字符**；整扇区不可读时用 `*No keys found or dead sector`（`Common.java:1473-1487`、`ReadTag.java:132-138`）
* 每扇区块数：`sector < 32 → 4`，`sector >= 32 → 16`（`Common.java:1443-1444`）
* **扇区号不得重复**（错误码 5）——这正是"把两段 dump 拼接追加"会被判非法的原因（`Common.java:1462-1467`）
* **4/16 个块之后必须紧跟新的扇区头**（错误码 1）（`Common.java:1443-1449`）
* **不校验**扇区是否连续/齐全、扇区号与文件顺序是否一致 → **部分扇区 dump 合法、乱序扇区也合法**
* `*` 行的容忍度**取决于调用场景**：编辑器打开与导入转换用 `isValidDump(lines, true)`（允许 `*`），**写卡用 `isValidDump(dump, false)`（含 `*` 即拒绝写入）**（`DumpEditor.java:547`、`ImportExportTool.java:551`、`WriteTag.java:758`）
* `#` 注释与空行在**打开时即被剥离**（`readFileLineByLine(file, false)`，`Common.java:406-418`）；行首尾统一 `trim`；编辑器保存时**强制大写**（`DumpEditor.java:517`）；写入用平台行分隔符且**末尾不加空行**（`Common.java:580-588`）
* 未读块/扇区哨兵：`NO_DATA = 32 个 '-'`（`MCReader.java:55`）；密钥未知哨兵：`NO_KEY = 12 个 '-'`（`MCReader.java:51`）
* 尾块的**字符偏移切分**（这是移植时必须精确复刻的一点，`DumpEditor.java:1056-1064`、`WriteTag.java:921-923`）：

  | hex 字符偏移 | 0–11 | 12–17 | 18–19 | 20–31 |
  |---|---|---|---|---|
  | 字节偏移 | 0–5 | 6–8 | 9 | 10–15 |
  | 含义 | **Key A** | **Access Bits（3 字节）** | **GPB / 用户字节** | **Key B** |

  ⚠️ **AC 只有 3 字节（字节 6/7/8），第 9 字节是 GPB**。PyMifareTool 当前把 `trailer[6:10]` 整体当 AC 并用 `FF 07 80 69` 覆盖（`core/dump_model.py:139,236`），**会连带改掉 GPB**，与 MCT 的"静态 AC 只覆盖 `[12,18)`、保留 GPB"行为不一致（`WriteTag.java:921-924`）。
* 出厂态尾块 = `FFFFFFFFFFFFFF078069FFFFFFFFFFFF`（`tools/example-files/example-dump-file.txt:5`）；**最后一个扇区的 GPB 是 `0xBC` 而非 `0x69`** → `FFFFFFFFFFFFFF0780BCFFFFFFFFFFFF`（`example-dump-file.txt:80`；实证：与 `example-dump-file.raw` 末 16 字节逐字节一致）。
* `NO_KEY`（12 个 `-`）用于替换读不到的 6 字节密钥段；`NO_DATA`（32 个 `-`）用于整块读不到（`MCReader.java:273-287`）。**这是 `.mct` 唯一的"未读"表达方式。**

#### （2）`.eml` —— 无扇区头的纯块序列（Proxmark3 风格）

* 每行 32 个 hex 字符，**无任何头/注释/空行**；块按绝对序号 0..N−1 连续排列
* 合法行数：`20 / 64 / 128 / 256`（对应 Mini/1K/2K/4K）（`ImportExportTool.java:593-611`）
* 空行即判定文件不完整（`ImportExportTool.java:602-607`）
* **尾块不是特殊行**，就是普通 32-hex 行，内容同样是 `KeyA(6B)+AC(3B)+GPB(1B)+KeyB(6B)`
* 大小写：MCT 导出倾向大写，Proxmark 原生输出为小写（`mfd2eml.py:39`、`mct2eml.py:55`）→ **解析必须大小写不敏感**
* `eml2mct.py:36-43` 正是"按 4/16 块插入 `+Sector: N`"的转换器 → 反向印证符号规则

#### （3）`.bin` / `.mfd` / `.raw` / `.dump` —— 原始二进制

* 合法长度：**精确** `320 / 1024 / 2048 / 4096` 字节（`ImportExportTool.java:575-581`），不符合即拒绝
* 就是 16×N 字节顺序拼接，**无文件头、无对齐填充**；MCT **不按扩展名判格式**（由用户在下拉菜单里选）
* **尾块包含在内**（占第 3/7/…/15 块），因此二进制格式**本来就携带 Key A / AC / GPB / Key B**
* 实证：`tools/example-files/example-dump-file.raw` = 1024 B，前 48 B 全 `00`，字节 48–63 = `FF×6 FF 07 80 69 FF×6`，末 16 B = `FF×6 FF 07 80 BC FF×6`，与同名 `.txt` 逐行一一对应

#### （4）`.json` —— MCT 的 dump 中间表示（也是所有转换的中转格式）

```json
{
  "Created": "MifareClassicTool",
  "FileType": "mfcard",
  "blocks": {
    "0": "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF",
    "1": "FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"
  }
}
```
* 块键为**十进制绝对块号字符串** `0..255`（`ImportExportTool.java:556-571`）
* 头部 3 行缩进 2 空格、块行缩进 4 空格、**最后一块无尾逗号**（`ImportExportTool.java:613-619`）
* 反向导入时 `blocks.length()` 必须 ∈ {20,64,128,256} 且**必须包含 `0..n-1` 全部键**，跳号即报错（`ImportExportTool.java:675-676,686-692,707-708`）

#### （5）`.keys` —— 密钥文件（文本）

* 规则（`Common.java:1505-1544`）：`#` 起整行或行内注释；`trim`；非空行必须是**纯 hex 且恰好 12 字符**；至少 1 把有效密钥；空文件/无密钥 → 错误码 1，非 hex → 2，长度不符 → 3
* 样例：`tools/example-files/example-key-dump.txt`（**这是"密钥映射表"人读格式**，`|sec|key A|res|key B|res|`，不是 `.keys` 本体）
* MCT 内置三档字典：`std.keys`、`extended-std.keys`、`hotel-std.keys`

#### （6）`.bin`（密钥） —— 6 字节原始密钥串联

* `len % 6 == 0`，按每 6 字节切分转 hex（`ImportExportTool.java:760-778`）

#### （7）备份

* `backupDumpsAndKeys()` 把 keys 目录 + dumps 目录整体打包成 **ZIP**（`ImportExportTool.java:869-909`）
* 导入支持**一次多选多个文件**（`ImportExportTool.java:857-859`）

### 3.4 核心算法规格

| 算法 | 规格 | 证据 |
|---|---|---|
| **Key Map 模型** | `SparseArray<byte[][]>`：key = 扇区号，value = `[keyA, keyB]`，任一可为 `null`（表示未知） | `MCReader.java:62,130-159` |
| **Key Map 构建** | 按扇区分片推进 `buildNextKeyMapPart()`，支持中途取消 `cancelCreateKeyMap()` | `MCReader.java:111-113,182-186` |
| **整卡读** | `readAsMuchAsPossible(keyMap)`：对每扇区分别用 A、B 各读一次，再 `mergeSectorData()` 合并两侧结果 | `MCReader.java:130-159` |
| **扇区读** | 认证 → 顺序读 4（或 ≥32 扇区时 16）块；单块失败写 `NO_DATA` 并**重新认证**；全块 `NO_DATA` 则整扇区返回 `null`；成功时把使用的 key 合并进尾块（KeyA 落在字节 0–11，KeyB 落在字节 20–31），对侧若不可读则填 `NO_KEY` | `MCReader.java:204-290` |
| **NXP 细节** | 若 Key B 在尾块中可读，则**不能**用 Key B 认证读数据（认证成功但读到 0）——代码据此判定 `noData` 并丢弃结果 | `MCReader.java:263-282`（注释明确引用 NXP） |
| **Value Block 判定** | `b0==b8 && b0^0xFF==b4`、`b1==b9 && b1^0xFF==b5`、`b2==b10 && b2^0xFF==b6`、`b3==b11 && b3^0xFF==b7`、`b12==b14 && b13==b15 && b12^0xFF==b13` | `Common.java:1398-1414` |
| **Value Block 布局** | 0–3 值、4–7 值取反、8–11 值、12 地址、13 地址取反、14 地址、15 地址取反（小端有符号 32 位） | `Common.java:1403-1411` + `ValueBlockTool` |
| **Block 0 合法性** | 校验 UID0/UID3/BCC/ATQA/SAK，依据 NXP **AN10927 / AN10833 / AN10834**；可跳过 BCC 检查 | `Common.java:1608-1624` |
| **Access Condition** | `AccessConditionDecoder` 把 8 种数据块组合 + 8 种尾块组合翻译为中文/英文权限描述，并检测非法组合 | `Activities/AccessConditionDecoder.java:103+` |
| **差分** | `MCDiffUtils.diffIndices` 做**逐 hex 字符（半字节）级**比较，不做字节对齐；返回 `Integer[0][0]`=仅 dump1 有该扇区、`Integer[1][0]`=仅 dump2 有、否则每块的差异字符下标数组；差异百分比**按字符数**统计。⚠️ 无长度/空值防御 | `MCDiffUtils.java:45-94`；`DiffTool.java:135-268` |
| **Key Map 攻击循环** | `buildNextKeyMapPart()` **外层遍历 key、内层 A→B 连续尝试**；「命中 key 前移 + 全 F 密钥提前 + 存在全 0 密钥时把 `FFFFFFFFFFFF` 提到最前」三条经验规则（对应上游 issue #66）；支持 `cancelCreateKeyMap()` 在每次认证前检查 | `MCReader.java:465-599`、`:890-927` |
| **写权限预检** | `isWritableOnPositions()` 返回逐块写权限码 `0=从不 / 1=KeyA / 2=KeyB / 3=KeyA|B / 4=KeyA可写但AC只读 / 5=KeyB可写但AC只读 / 6=KeyB可写但密钥只读 / -1=错误`；扇区死或 AC 非法时该扇区值为 `null`；认证失败整体返回 `null` | `MCReader.java:699-812`；消费方 `WriteTag.java:1121-1193` |
| **BCC** | `calcBcc` **只接受 4 字节 UID**（长度不符抛异常），逐字节 XOR；**7/10 字节 UID 的 BCC1/BCC2 在 MCT 中完全没有实现**（由用户自带），`isValidBlock0` 也仅在 `uidLen==4` 时校验 BCC | `Common.java:2254-2263`、`:1634-1639`、`CloneUidTool.java:195-210` |
| **值块写入** | `writeValueBlock()` 以及 4.3.0 新增的 `valueTransferRestore()`：用于"只有 decrement/transfer/restore 权限"的卡也能改值块——写暂存块 → `restore` → 认证目标块 → `transfer` → 还原暂存块；返回码 `0 成功 / 1 目标是尾块或厂商块 / 2 越界 / -1 认证或 IO 错误` | `MCReader.java:414-462`、`:958-1022` |
| **制造日期解码** | 取 Block 0 **最后 2 字节 BCD**（周 / 年）解码 | `DumpEditor.java:765-818` |
| **进制/编码换算全套** | `hex↔ascii`（<0x20 或 ==0x7F → `.`）、`hex↔bin`、`hex→decBE/decLE`、`decBE/decLE→hex`，含长度阈值与补零规则 | `Common.java:1756-1990`、`HexToAscii.java:41-73` |
| **魔术卡 UID** | ⚠️ **MCT 只实现 Gen2（CUID）直写**：认证扇区 0 → `writeBlock(0,0,block0,key)`，默认 key `FFFFFFFFFFFF`、默认 rest `080400475955D141103607`，可选自动算 SAK/ATQA；写入前用 `isValidBlock0` 校验，写后要求重新贴卡比对 UID。**Gen1a（`0x40`/`0x43` 后门）在全仓库完全没有实现**；Gen3 的 APDU 路径 `90 F0 CC CC 10` 存在但被注释禁用（源码自述会让 4K 卡扇区 0–31 brick） | `CloneUidTool.java:223-291`、`:300-343`；`MCReader.java:367-392`（禁用） |
| **无 Plus/Ultralight 分支** | `MCReader` 只通过 `MifareClassic.get(tag)` 判定；Plus SL1 因 SAK bit4=1 被当 MFC 读，SL2/Ultralight/DESFire 判为"不支持"。Ultralight 无块读写实现 | `Common.java:930-949`；`tag_type_list.xml` |

### 3.5 功能全集（菜单级权威清单）

**工具菜单（`app/src/main/res/menu/tools.xml`，9 项）**：Tag Info、Clone UID、Diff Tool、Access Condition Tool、Value Block Tool、BCC Tool、Data Conversion Tool、UID Log Tool、Import/Export Tool。

**Dump 编辑器（`dump_editor_functions.xml`，14 项）**：保存、以 ASCII 显示、解码 Access Condition、Value Block 转整数、解码制造日期、与另一 Dump 对比、写入卡片、保存密钥、打开 Value Block 工具、打开 AC 工具、打开 BCC 工具、分享、复制所有扇区、导出 Dump。

**密钥编辑器（`key_editor_functions.xml`，4 项）**：保存、分享、导出密钥、**去除重复密钥**。

**文件选择器（`file_chooser_functions.xml`，3 项）**：新建文件、删除文件、导入/导出文件。

**主菜单（`main_menu_functions.xml`）**：首选项、关于。

**Dump 文件类型（`dump_file_types.xml`）**：JSON / MFD·BIN / EML / MCT。
**密钥文件类型（`keys_file_types.xml`）**：BIN / KEYS。

**MCT 有而 PyMifareTool 完全没有的能力**（合并重点）：Key Map（扇区级 A/B 密钥矩阵）、整卡"尽力读取"、只读/可写性建模、Value Block 工具与写入、BCC 工具、制造日期解码、密钥文件体系与去重、JSON/EML 格式、ZIP 备份、魔术卡 UID 克隆、Tag Info（ATQA/SAK/容量）。

**PyMifareTool 有而 MCT 没有的增量**（合并时必须保住）：本地 SQLite 发卡档案与刷卡流水审计、CSV 导出、韦根 WG26/WG34 与 8H10D 换算、原生串口报文监视器、固件指令探测、暗黑主题一体化工作台。

### 3.5.1 写卡流程的可移植规格（安全相关，必须对齐）

MCT 的写卡链是一条**预检 → 问题清单 → 用户裁决 → 逐块写入**的安全流水线（`WriteTag.java`）：

| 环节 | 规格 | 出处 |
|---|---|---|
| 1 | 写 dump 前 `isValidDump(dump, false)` —— **含 `*` 死扇区行的 dump 直接拒绝** | `:758` |
| 2 | 构建写入列表时**丢弃含 `-` 占位符的块** | `:915,928` |
| 3 | 卡尺寸与 dump 尺寸必须一致 | `:1000-1007` |
| 4 | `isWritableOnPositions()` 逐块算写权限，产出问题清单 | `:1023-1024` |
| 5 | Block 0：**未勾选"写厂商块"时直接跳过不写**；勾选后 `isValidBlock0` 返回 2（BCC 无效）即**直接中止整个写入**，返回 3（SAK/ATQA 可疑）则入问题清单 | `:1077-1100` |
| 6 | 尾块 AC 检查（⚠️ 上游此处有 off-by-one：`sector < 31` 漏检扇区 31，疑似应为 `sector < 32`） | `:1104` |
| 7 | 用户裁决：**Skip（跳过问题块继续）/ Cancel（全部取消）**，不要求输入确认文本 | `:1232-1245` |
| 8 | 写入：`wi` 为 1 或 4 时用 Key A，为 2、5、6 时用 Key B；**每块最多重试 2 次**；**任一块失败即中止整次写入** | `:1325-1373` |
| 9 | ⚠️ MCT **写后不做回读校验**，也无逐扇区成败统计 | `:1325-1373` |

> **给 PyMifareTool 的取舍**：第 1/2/4/5/6 条**必须照搬**（安全底线）；第 7 条应做得比上游更好（本项目可给逐块问题表格 + 预览差异）；第 8 条的"一块失败即全停"可保留；第 9 条**建议超越上游**——加一次写后回读比对（本项目的 `core/dump_diff` 正好复用）。
>
> 另有两条上游行为值得注意：工厂格式化时**最后一个扇区 GPB = 0xBC**、**sector 0 的 block 0 不写**（`WriteTag.java:1483-1538`）；静态 AC 只覆盖 3 字节并**保留 GPB**（`:921-924`）。

### 3.5.2 其它可直接对齐的细节

| 项 | 规格 | 出处 |
|---|---|---|
| Dump 自动命名 | `UID_<UID大写HEX>_yyyy-MM-dd_HH-mm-ss.mct` | `DumpEditor.java:397-415` |
| 保存密钥文件 | 从各扇区尾块取 `[0,12)` 与 `[20,32)`，跳过 `NO_KEY`，去重；名 = `UID_<UID>` 或 dump 名 + `.keys` | `DumpEditor.java:988-1011` |
| 密钥编辑器 | 加载时**保留注释与空行**（与 dump 相反）；保存时统一大写但**保留注释尾部**；支持"去除重复"；**拒绝覆盖** `std.keys`/`extended-std.keys`/`hotel-std.keys` | `KeyEditor.java:104-105,364-382,443-445,350-355` |
| UID 日志 | 一行 = `yyyy-MM-dd_HH-mm-ss: <UIDHEX>`，追加写入，显示时倒序 | `Common.java:716-727`、`UidLogTool.java:101-141` |
| 首选项键名 | `auto_reconnect`、`auto_copy_uid`、`uid_format`(0=Hex/1=DecBE/2=DecLE)、`save_last_used_key_files`、`use_custom_sector_count`、`custom_sector_count`、`use_retry_authentication`、`retry_authentication_count`、`custom_app_language`、`custom_app_theme` | `Preferences.java:58-68` |
| 内置密钥字典规模 | `std.keys` 3 把 / `hotel-std.keys` 23 把 / `extended-std.keys` 2477 把（含 52 行注释） | 实测 assets |
| ⚠️ 不要照抄的坏行为 | `Common.saveFileAppend` 在 append dump 时会把 `isDump` 当 `comment` 传入，导致 `newLines[0]` 为 `null` 后写文件抛 NPE（静态阅读结论，未运行验证） | `Common.java:516,551-563,584-588` |

### 3.6 许可证与合规（**这是合并的决策前置项**）

* MCT 采用 **GPLv3**（`LICENSE.txt:1-3`）。GPLv3 具有**传染性**：把 MCT 代码并入 PyMifareTool 并分发，则整个 PyMifareTool 必须以 GPLv3 授权、附完整对应源码、保留版权与许可声明。
* PyMifareTool 目前**无许可证文件**（实测 `Test-Path LICENSE` → `False`），且 `README.md:4` 自述"参照/升级"了另一个 GPL 项目 MifareOneTool（也是 GPL 系）。
* 因此有两条合法路线，必须在动手写第一行移植代码前定案：

| 路线 | 做法 | 代价 | 适用 |
|---|---|---|---|
| **R1：接受 GPLv3（推荐）** | PyMifareTool 顺势改为 GPLv3；移植 MCT 代码时在文件头保留 `Copyright 2015 Gerhard Klostermeier` 与 GPLv3 声明、在 `NOTICE`/`LICENSE` 中说明来源 | 必须开源；不能再闭源分发 | 个人/开源定位；本轮目标是"功能合并"，R1 是唯一能真正复用 MCT 实现的路径 |
| **R2：Clean-room 重实现** | **不复制任何 MCT 代码/注释/常量名**，仅依据本文件 §3.3/§3.4 的**格式与算法规格**（格式本身是与实现分离的事实性信息）重新实现 | 工作量约 +40%；且因已阅读过 MCT 源码，"洁净室"在法律上并不洁净，风险仍在 | 有强闭源商业诉求时，需法务介入 |

> **明确建议**：选 **R1**。理由：①本项目已经公开对标 GPL 项目；②MCT 的价值集中在格式与算法规格，重写的法律收益远小于工程代价；③R1 只需在 Phase 0 做一次性合规（`LICENSE`、`NOTICE`、文件头、README 声明）。

#### 必须保留的署名与出处（删除或改写都会造成合规风险）

上游代码的出处标注做得很规范，移植时必须**原样保留**到派生文件的头部注释或 `NOTICE`：

| 出处 | 位置 |
|---|---|
| proxmark3（Gen3 后门 APDU 与 brick 警告） | `MCReader.java:352-356` |
| AOSP `MifareClassic.blockToSector` | `MCReader.java:1164-1178` |
| SLURP / proxmark3 密钥来源 | `Common.java:122-128` |
| NXP 应用笔记 **AN10927（UID/BCC）、AN10833（ATQA）、AN10834（SAK）、AN1305（AC）** | `Common.java:1612-1614` 等 |
| 共同署名（Slawomir Jasek 等） | `CloneUidTool.java:44` |
| 上游 issue 编号（#66 等经验规则来源） | `MCReader.java:568,920,1043` |

#### 美术资源不是 GPL（不要复制）

`README.md` 明确 Logo 采用 **CC BY-NC-SA 4.0**、Oxygen 图标 **LGPL**、RFID Tag 图 **CC 3.0**。这些**不受 GPLv3 覆盖**，移植时**不要复制 MCT 的 logo/图标/截图**，PyMifareTool 应自备视觉资产。同理，`app/src/main/assets/key-files/*.keys` 是**密钥汇编**（文件头注明汇集自 SLURP / proxmark3 / 公开搜索），带独立来源属性，建议**自行整理**或明确标注来源后再使用。

#### 已核实的现状（好消息）

全仓检索确认：PyMifareTool **目前没有任何直接拷贝的 MCT 代码**，对 MCT 只有文字提及（`docs/change/README.md:216`、`core/card_service.py:235`、`MIFAREONETOOL_FEATURE_INVENTORY.md:11`）。也就是说——**现在**做许可证决策，代价最低；一旦开始移植再补，边界就说不清了。

### 3.7 MCT 侧已知局限（合并时不要照搬其缺点）

* 存储为 Android 应用私有目录 + SAF `content://`，PyMifareTool 应直接用文件系统与 SQLite（已具备）。
* 无本地卡片档案/持卡人管理（PyMifareTool 已有，保留）。
* 无桌面端自动化测试（PyMifareTool 有 27 项，保留并扩展）。
* Key Map 只存内存不落盘（合并时可增量做"密钥地图导出"，作为差异化亮点）。

---

## 4. 合并可行性评估

### 4.1 两道硬闸门（必须先过，否则后面全是浪费）

#### 闸门 1：许可证（§3.6）——**决策项 D1**

* 默认选项：**R1，PyMifareTool 转为 GPLv3**，可自由移植 MCT 实现。
* 若选 R2（clean-room），则**禁止**把 MCT 的 Java 代码逐行翻译；只能依据本指导书 §3.3/§3.4 的规格重写，且需法务确认。
* **本指导书后续所有"移植"措辞，均默认已选定 R1。**

#### 闸门 2：硬件能力——**决策项 D2**

现有硬件只做一件事：贴卡时主动广播 `AA BB 06 01 [UID] [BCC]`。MCT 的功能按"是否需要下行指令"严格二分：

```text
不需要硬件（纯文件/纯算法）         需要双向硬件（认证/读写/攻击）
─────────────────────────────       ──────────────────────────────
.mct/.eml/.json/.bin 读写           整卡"尽力读取"（Key Map 驱动）
Key Map 数据模型与编辑              Key Map 破解（字典/Nested/Darkside/HardNested）
Access Condition 解码/编码          写块 / 写整卡（MCT 无 writeSector，按块写）
Value Block 解析与构造              Value Block 的 increment/decrement/restore/transfer
BCC 工具（4 字节 UID）              魔术卡 UID 克隆（Gen1a 需自研 / Gen2 直写）
Block 0 合法性校验                  Tag Info 的 ATQA/SAK/ATS 实测
写卡前预检 isWritableOnPositions     固件/读写器能力真机探测
Diff 工具                           固件/读写器能力真机探测
制造日期解码
密钥文件体系（.keys/.bin）
发卡档案 + 流水审计（已有强制项）
```

**结论**：**不接新硬件，就能拿到 MCT 约 60% 的功能价值**（格式互操作 + 密钥体系 + 分析编辑工具链），这部分**现在就能做且必须做**；剩下 40% 必须等硬件。

### 4.2 逐功能可行性矩阵

| # | MCT 功能 | PyMifareTool 现状 | 可移植性 | 依赖硬件 | 目标阶段 |
|---|---|---|---|---|---|
| 1 | `.mct` 读 | 有，但语义不符（N-5/N-6） | 【改写】 | 否 | P1 |
| 2 | `.mct` 写 | 有，把未读块写成零（N-5） | 【改写】 | 否 | P1 |
| 3 | `.eml` 读/写 | 无 | 【纯逻辑，直接移植】 | 否 | P1 |
| 4 | `.bin/.mfd` 读/写 | 有，但缺 Mini/2K 且 2K 静默截断（N-1） | 【修补】 | 否 | P0/P1 |
| 5 | `.json` 读/写 | 无 | 【纯逻辑，直接移植】 | 否 | P1 |
| 6 | `.keys` 读/写/校验/去重 | 无 | 【纯逻辑，直接移植】 | 否 | P3 |
| 7 | 密钥 `.bin` | 无 | 【纯逻辑，直接移植】 | 否 | P3 |
| 8 | Key Map 模型（扇区×A/B） | 无 | 【纯逻辑，直接移植】 | 否 | P3 |
| 9 | `NO_KEY`/`NO_DATA` 语义 | 无（只有块级三态） | 【纯逻辑，直接移植】 | 否 | P1 |
| 10 | Access Condition 工具 | 已有且更强（编码+解码+8×8 表） | 【对齐语义即可】 | 否 | P2 |
| 11 | Value Block 判定/转整数 | 无 | 【纯逻辑，直接移植】 | 否 | P2 |
| 12 | Value Block 写入（inc/dec/restore/transfer，含 4.3.0 的 `valueTransferRestore`） | 只有 CMD 常量，未实现 | 【需重写】+ 硬件 | **是** | P4 |
| 13 | BCC 工具 | 无（只有帧 BCC） | 【移植】**但 MCT 只算 4 字节 UID 的 BCC**；7/10 字节的 BCC1/BCC2 上游无实现，需按 ISO/IEC 14443-3 自行补 | 否 | P2 |
| 14 | Block 0 合法性校验（AN10927/10833/10834） | 无（只校验 UID 的 BCC） | 【纯逻辑，直接移植】 | 否 | P1 |
| 15 | 制造日期解码（Block 0 末 2 字节 BCD = 周/年） | 无 | 【纯逻辑，直接移植】 | 否 | P2 |
| 16 | UID 日志 | 已有（SQLite + 流水，优于 MCT 文本日志） | 【保留不动】 | 否 | — |
| 17 | Diff 工具 | 有，但只支持 64 块（N-8） | 【修补+对齐】 | 否 | P1 |
| 18 | Tag Info | 只有 UID/BCC | 【新写】+ 硬件 | 部分 | P2/P4 |
| 19 | 整卡"尽力读取" | 无（现有读卡硬编码 4 块/扇区，N-4） | 【移植算法 + 重写驱动】 | **是** | P3/P4 |
| 20 | Key Map 破解（字典） | 有骨架（`_do_crack_keys`），但无 Key Map 落点 | 【重写】 | **是** | P3/P4 |
| 21 | Key Map 破解（Nested/Darkside/HardNested） | 只调外部 exe，无可用二进制 | 【保留外壳 + 补后端】 | **是** | P4 |
| 22 | 写整卡（含 Block0 保护、写后校验） | 有骨架，4K 错位、无扇区感知 | 【重写】 | **是** | P4 |
| 23 | 魔术卡 UID 克隆 | `libnfc_adapter.set_magic_uid` 桩 | ⚠️ **MCT 只实现 Gen2（CUID）直写**；**Gen1a（`0x40`/`0x43` 后门）上游完全没有，必须从零写**；Gen3 APDU 上游已注释禁用（会 brick 4K 卡扇区 0–31） | **是** | P4 |
| 23b | **写权限预检 `isWritableOnPositions` + Skip/Cancel 问题清单** | 完全没有 | 【必须移植】安全关键，见 §2.5 | 否（算法）/ 显示需硬件 | P2/P4 |
| 23c | 写卡静态 AC / 写厂商块（Block 0）选项 | 只有 Block 0 一个布尔开关 | 【移植】静态 AC 只改 3 字节并保留 GPB | 部分 | P2 |
| 23d | Dump 自动命名 / Save Keys / 密钥去重 | 无（`.dic` 导出存在但会剔除 `000000000000`） | 【移植】MCT 保留全 0 密钥 | 否 | P1/P3 |
| 24 | Import/Export + ZIP 备份 | 无（只有单文件） | 【纯逻辑，直接移植】 | 否 | P5 |
| 25 | 首选项（默认密钥文件/写保护/ASCII 等） | 无（散落在 UI 状态里） | 【新写】 | 否 | P5 |
| 26 | 编辑器增强（复制所有扇区、粘贴、随机填充、ASCII 视图） | 只有单元格就地编辑 | 【纯逻辑，直接移植】 | 否 | P2 |
| 27 | 多语言 | 仅中文 | 【可选】 | 否 | P5 |
| 28 | 卡片档案/流水/CSV | 已有（MCT 无） | 【保留】 | 否 | — |
| 29 | 韦根/8H10D 换算 | 已有（MCT 无） | 【保留】 | 否 | — |
| 30 | 串口报文监视器/固件探测 | 已有（MCT 无） | 【保留】 | 否 | — |

**统计**：可直接/修补移植 **18 项**；需重写 **6 项**；需硬件 **8 项**；PyMifareTool 独有需保护 **3 类**。

### 4.3 结论

1. **可行，且收益明确**：MCT 的格式层 + 密钥层 + 分析工具链是"零硬件依赖的高确定性收益"，恰好补上 PyMifareTool 当前最大的空白（密钥体系与文件互操作）。
2. **不可行/不应做的部分**：直接复用 MCT 的 Activity 层（Android 全套），以及指望当前广播硬件承担读写——这两条路都是死路。
3. **合并的正确姿势不是"移植 MCT"，而是"以 MCT 的规格为验收标准，在 PyMifareTool 的分层架构里重铺一遍数据模型与适配层"**。这也正好顺带修掉 N-3/N-4 这两个结构债。

---

## 5. 目标架构（合并后的 PyMifareTool v2）

### 5.1 分层与新增模块

```text
PyMifareTool/
├── core/
│   ├── mifare_spec.py        【新】TagGeometry：Mini/1K/2K/4K 几何与块↔扇区换算（唯一真相源）
│   ├── protocol.py           【保留】AA BB 帧 + UID 换算 + AccessBits 编解码
│   ├── key_map.py            【新】NO_KEY/NO_DATA 常量、KeyMap（扇区×{A,B}）
│   ├── keys_file.py          【新】.keys / keys.bin 解析、校验、去重、导出（含 MCT 错误码语义）
│   ├── dump_model.py         【改造】MifareDump：接入 TagGeometry、键级/块级双状态、去掉格式解析
│   ├── dump_codec.py         【新】格式编解码层：mct / eml / bin / mfd / json（纯函数，可单测）
│   ├── mct_compat.py         【新】isValidDump / isValidKeyFile / isValidBlock0 / isValueBlock（规格对齐）
│   ├── value_block.py        【新】Value Block 判定、解析为 int、构造、增量/减量语义
│   ├── dump_diff.py          【新】容量无关的差分引擎（从 UI 抽离）
│   ├── serial_worker.py      【保留】广播链路（DTR/RTS=False 红线不动）
│   ├── card_db.py            【保留】SQLite 档案与流水
│   ├── card_service.py       【改造】基于适配器的任务引擎（读卡/写卡/破解/探测）
│   ├── attack_runner.py      【改造】外部攻击工具后端 + 结果解析成 KeyMap
│   └── adapters/
│       ├── base_adapter.py       【改造】能力声明 + 扇区级原语 + 默认算法
│       ├── broadcast_adapter.py  【改造】包装 SerialWorker，能力全 False
│       ├── mock_adapter.py       【新】内存虚拟卡，无硬件跑通全流程 & 测试用
│       ├── pcsc_adapter.py       【新】pyscard/PC-SC（ACR122U 类）
│       └── libnfc_adapter.py     【改造】CLI 后端（修 N-7 假成功）
├── ui/
│   ├── main_window.py        【改造】适配器工厂 + 能力分档灰化 + 新增 Tab
│   ├── sector_table.py       【保留/微调】块矩阵
│   ├── dump_diff.py          【改造】调用 core/dump_diff，支持四容量
│   ├── key_editor.py         【新】密钥文件编辑器（对标 MCT KeyEditor + FileChooser）
│   ├── key_map_view.py       【新】密钥地图矩阵（对标 MCT KeyMapCreator 结果）
│   ├── tag_tools.py          【新】Tag Info / BCC / Value Block / 制造日期 / 数据换算 五合一工具页
│   ├── import_export.py      【新】批量导入/导出 + ZIP 备份
│   ├── card_manage.py        【保留】
│   └── dictionary_tools.py   【改造】字典页接入 key_editor，删除硬编码副本（修 N-9）
├── tests/
│   ├── run_tests.py          【改造】注册新测试类
│   ├── interop/              【新】MCT 互操作预言机测试
│   └── hw/                   【新】硬件在环测试（默认不在 CI 跑）
└── docs/
    ├── PROTOCOL_SPECIFICATION.md  【更新】补 MCT 格式规格
    └── MCT_MERGE_AND_REVIEW_GUIDE.md 【本文件】
```

### 5.2 关键接口设计（先定契约，再写实现）

#### （A）`core/mifare_spec.py` —— 消灭所有 `sector*4+3` 与 `range(64)`

```python
from dataclasses import dataclass
from typing import Iterator, Optional

@dataclass(frozen=True)
class TagGeometry:
    name: str                 # "MIFARE Mini" / "MIFARE Classic 1K" / "2K" / "4K"
    total_bytes: int          # 320 / 1024 / 2048 / 4096
    block_count: int          # 20 / 64 / 128 / 256
    large_sectors_from: int   # 32（仅 4K 生效），否则等于 sector_count
    @property
    def sector_count(self) -> int: ...
    def blocks_in_sector(self, sector: int) -> int:      # 4 或 16
    def first_block(self, sector: int) -> int:           # 4K: 128+(s-32)*16
    def trailer_block(self, sector: int) -> int:
    def blocks(self, sector: int) -> Iterator[int]:
    def block_to_sector(self, block: int) -> int:
    def is_trailer(self, block: int) -> bool:

MINI = TagGeometry("MIFARE Mini", 320, 20, 5)
S50  = TagGeometry("MIFARE Classic 1K", 1024, 64, 16)
S70_2K = TagGeometry("MIFARE Classic 2K", 2048, 128, 32)
S70_4K = TagGeometry("MIFARE Classic 4K", 4096, 256, 40)
BY_BYTES = {g.total_bytes: g for g in (MINI, S50, S70_2K, S70_4K)}
BY_BLOCKS = {g.block_count: g for g in (MINI, S50, S70_2K, S70_4K)}
def from_bytes(n: int) -> Optional[TagGeometry]
def from_block_lines(n: int) -> Optional[TagGeometry]
```

> 验收：新代码中**不允许**出现字面量 `4 + 1`、`sector * 4`、`range(64)`、`block_idx // 4` 之类几何硬编码（用 grep 守门）。

#### （B）`core/key_map.py` —— MCT 语义模型

```python
NO_KEY  = "------------"                    # 12 个 '-'
NO_DATA = "--------------------------------" # 32 个 '-'
DEFAULT_KEY = "FFFFFFFFFFFF"

KeyType = Literal["A", "B"]

class KeyMap:
    """扇区 → (KeyA, KeyB)，任一可为 None。对标 MCReader.mKeyMap。"""
    def set(self, sector: int, key: bytes, key_type: KeyType) -> None: ...
    def get(self, sector: int) -> tuple[Optional[bytes], Optional[bytes]]: ...
    def sectors(self) -> list[int]: ...
    def __iter__(self) -> Iterator[tuple[int, Optional[bytes], Optional[bytes]]]: ...
    @classmethod
    def from_key_list(cls, keys: Iterable[bytes], sectors: Iterable[int]) -> "KeyMap": ...
    @classmethod
    def from_dump(cls, dump) -> "KeyMap": ...       # 从尾块提取已知密钥（写卡提速用）
    def merge(self, other: "KeyMap") -> None: ...
    def to_keys_file(self, path: str) -> int: ...   # 导出找到的密钥（去重）
```

#### （C）`core/adapters/base_adapter.py` —— 能力分档 + 扇区级默认算法

```python
@dataclass(frozen=True)
class ReaderCaps:
    read_block: bool = False
    write_block: bool = False
    authenticate: bool = False
    value_block_ops: bool = False
    magic_uid_gen1a: bool = False
    magic_uid_gen2: bool = False
    attacks: bool = False
    uid_broadcast_only: bool = False

@dataclass
class TagInfo:
    uid: bytes
    uid_len: int
    sak: Optional[int] = None
    atqa: Optional[bytes] = None
    ats: Optional[bytes] = None
    geometry: Optional[TagGeometry] = None

class BaseReaderAdapter(ABC):
    @property @abstractmethod
    def adapter_name(self) -> str: ...
    @property @abstractmethod
    def caps(self) -> ReaderCaps: ...
    @abstractmethod
    def open(self) -> bool: ...
    @abstractmethod
    def close(self) -> None: ...
    @abstractmethod
    def scan(self) -> Optional[TagInfo]: ...
    @abstractmethod
    def authenticate(self, sector: int, key: bytes, key_type: KeyType) -> bool: ...
    @abstractmethod
    def read_block(self, block: int) -> Optional[bytes]: ...
    @abstractmethod
    def write_block(self, block: int, data: bytes) -> bool: ...

    # ---- 以下为基类提供的"免费"扇区级算法（移植 MCReader.readSector 语义）----
    def read_sector(self, sector: int, key: bytes, key_type: KeyType,
                    geometry: TagGeometry) -> Optional[list[Optional[str]]]:
        """认证成功则逐块读；失败块填 NO_DATA 并按需重认证；
        全块 NO_DATA → 返回 None；成功则把所用 key 合并进尾块，
        对侧不可读时填 NO_KEY（对标 MCReader.java:204-290）。"""

    def read_as_much_as_possible(self, key_map: KeyMap,
                                 geometry: TagGeometry) -> dict[int, list[Optional[str]]]:
        """A/B 各读一次再合并（对标 MCReader.java:130-159）。"""
```

#### （D）`core/dump_codec.py` —— 格式编解码与校验

```python
class DumpFormat(StrEnum):
    MCT = "mct"; EML = "eml"; BIN = "bin"; JSON = "json"

def detect_format(path: str, sample: bytes) -> Optional[DumpFormat]: ...
def load(path: str, fmt: DumpFormat | None = None) -> MifareDump: ...
def save(dump: MifareDump, path: str, fmt: DumpFormat) -> None: ...
def dumps_mct_lines(dump: MifareDump) -> list[str]: ...   # 未读块输出 NO_DATA / '*'，绝不输出零
def validate_dump_lines(lines: list[str], ignore_asterisk: bool = True) -> int   # 错误码 0..6
def validate_key_lines(lines: list[str]) -> int                                  # 错误码 0..3
```

#### （E）`core/card_service.py` 改造点

```python
class CardOperationWorker(QThread):
    def __init__(self, adapter: BaseReaderAdapter, op_type: str, *,
                 key_map: KeyMap | None = None,
                 target_sectors: list[int] | None = None,
                 geometry: TagGeometry | None = None,
                 dump_to_write: MifareDump | None = None,
                 allow_block0_write: bool = False, ...):
```
* 去掉对 `SerialWorker` 具体类型的依赖（改依赖抽象）；
* 所有块号推导改走 `TagGeometry`；
* 读卡走 `adapter.read_as_much_as_possible()`，产出 `MifareDump + KeyMap`；
* 写卡前置校验：`validate_dump_lines` + Block 0 保护 + 尾块二次确认。

#### （F）UI 能力分档

```python
caps = adapter.caps
btn_read.setEnabled(caps.authenticate and caps.read_block)
btn_write.setEnabled(caps.write_block)
btn_crack.setEnabled(caps.authenticate)
btn_probe.setEnabled(not caps.uid_broadcast_only)
```
广播适配器下：三个按钮灰化 + ToolTip 指向"载入 MCT Dump"的离线工作流（把 `core/card_service.py:229-238` 的现有话术升级为 UI 级引导）。

### 5.3 兼容性红线（改造期间不得破坏）

1. `ser.dtr = False` / `ser.rts = False` 必须保留（`core/serial_worker.py:121-123`）。
2. Block 0 写保护默认开启（`ui/sector_table.py:138-139`）。
3. 广播硬件下的刷卡→看板→流水→建档闭环不能退化。
4. 27 项现有测试必须持续全绿（只允许新增，不允许删改断言，除非断言本身错）。
5. UTF-8 without BOM；耗时操作不得进主线程。

---

## 6. 分阶段实施指导

> 阶段划分原则：**P0–P2 完全不依赖新硬件**，可立即开工并独立交付价值；**P3 引入硬件抽象但用 `MockReaderAdapter` 验收**；**P4 才需要真实双向读卡器**；**P5 收尾**。
> 每阶段结束必须打 git tag（`phase-0`…`phase-5`）并全量跑测试。

### Phase 0 —— 地基与止血（预计 3–4 人日）

**目标**：让项目变成"可版本化、可合规、无已知数据损坏"的安全基线。

| # | 任务 | 具体动作 | 验收 |
|---|---|---|---|
| 0.1 | **决策 D1（许可证）** | 二选一定案：R1 转 GPLv3（推荐）/ R2 clean-room。产出一行书面决策记录 | 决策写入 `docs/decisions/ADR-0001-license.md` |
| 0.2 | **仓库化** | `git init`；写 `.gitignore`（`.venv/ __pycache__/ *.pyc cards.db scratch/ .idea/ matplotlib-e*/`）；`git add` 现有代码并打 `v1.0-baseline` tag | `git log` 可用；`git status --short` 干净 |
| 0.3 | **清理垃圾** | 删除 `matplotlib-e___mire/`（删除前必须 `Test-Path` 解析绝对路径并确认），重建 `requirements.txt`（加 `pyserial>=3.5,<4`、`PyQt6>=6.6,<7`） | 目录列表干净；`pip install -r requirements.txt` 可解析 |
| 0.4 | **止血 N-1（2K 截断）** | `core/dump_model.py:371-388` 改为按 `MifareDump.BY_BYTES` 精确匹配 320/1024/2048/4096，尺寸不合法直接报错，**绝不截断** | 新增测试：2048 字节文件必须加载为 128 块；1500 字节必须报错 |
| 0.5 | **止血 N-7（假成功）** | `core/adapters/libnfc_adapter.py:71-73` 改为 `raise NotImplementedError` 或返回 `False` | 新增测试断言 authenticate 不返回 True |
| 0.6 | **止血 N-5（.mct 零污染）** | `save_mct` 对 `BlockState.UNREAD/READ_FAILED` 的块输出 `NO_DATA`（32 个 `-`），整扇区未读时输出 `*No keys found or dead sector`；`load_mct` 识别两种哨兵 | 新增互操作测试（见 0.7） |
| 0.7 | **建立互操作预言机** | `tests/interop/`：① 用 Python 复刻 `isValidDump`/`isValidKeyFile` 错误码（对齐 `Common.java:1434-1544`）；② 把 MCT 的 `tools/dump-file-converter/eml2mct.py` 当作**外部预言机**（纯标准库，可 subprocess 调用，R1 路线下合法） | 测试：PyMifareTool 导出的 `.mct` 必须 `validate_dump_lines() == 0`，且与 `eml2mct.py` 输出逐行一致 |
| 0.8 | **止血 N-10 文档漂移** | `AGENTS.md`：测试数 15→27、目录树补 `core/adapters/`、`docs/change/`、`REVIEW_REPORT.md`、本文件；`README.md` 补格式现状 | 文档与实测一致 |
| 0.9 | **止血 N-3 接线（最小步）** | 让 `main_window` 通过 `BroadcastSerialAdapter(worker)` 创建适配器并传入 UI（此时能力全 False），不改变行为 | 27+ 项测试全绿；新增测试断言 UI 在广播能力下灰化读写按钮 |
| 0.10 | **🔴 止血 N-15（测试污染生产库）** | `tests/run_tests.py` 改为在 `tempfile.TemporaryDirectory()` 内建 `MainWindow`/`CardDatabase`（或给 `CardDatabase` 加 `db_path` 参数）；同时删掉 `:30` 的硬编码绝对路径 | 跑完测试后项目根 `cards.db` 的 mtime/行数**不变**；测试可在任意目录运行 |
| 0.11 | **🔴 止血 N-13/N-14（写卡安全）** | `core/card_service.py:277-290`：跳过 `BlockState != READ_OK` 的块；写尾块前强制 AC 合法性校验；`authenticated` 为假时立即中止；`allow_block0_write` 语义保持 | 新增测试：含 UNREAD 块的 dump 写卡**不得**写出任何 `00` 块；非法 AC 的尾块被拒绝 |
| 0.12 | **止血 N-16（取消不发信号）** | `core/card_service.py:130-131,140-142,185-186` 的提前 `return` 全部改为 `break` + 统一发 `sig_finished(False, "已中止", None)` | GUI 测试断言：中止后进度面板隐藏 |
| 0.13 | **隐私与编码清理（N-22/N-23）** | `git rm --cached cards.db`（本地保留但不再入库，改默认路径为 `%APPDATA%` 或 `./data/cards.db`）；清理 `scratch/v2/user_card_from_mct.mct`；修 `.idea/vcs.xml` 的 GBK 残留；为 `card_db.py` 加 `PRAGMA user_version` 与最小迁移 | `git ls-files` 中无 `cards.db`/`scratch`；`tools/check_encoding.py` 全绿 |

**Phase 0 验收门**：`git` 可用、许可证定案、**无静默数据截断**、**写卡不再可能静默清零/锁卡**、**测试不再污染生产库**、`.mct` 零污染、互操作预言机可跑、测试 ≥ 40 项全绿。

**风险与回滚**：0.9 动了 UI 构造链 → 保留 `SerialWorker` 直连路径作为 `--legacy` 回退；0.13 改了 `cards.db` 路径 → 提供一次性迁移（把旧库复制到新路径）；任何一步失败用 `git checkout .` 回滚。

### Phase 1 —— 几何模型与文件格式内核（预计 4–6 人日）

**目标**：用 MCT 的格式规格把"文件层"做到 100% 互操作，并把几何真相收敛到一处。

| # | 任务 | 产物 | 验收 |
|---|---|---|---|
| 1.1 | 新增 `core/mifare_spec.py`（§5.2-A） | 几何唯一真相源 | 单测覆盖 Mini/1K/2K/4K 的 `first_block/trailer_block/block_to_sector` 往返一致性 |
| 1.2 | `core/dump_model.py` 改为持有 `geometry`（替换 `is_4k` 布尔），保留 `is_4k` 只读属性做兼容 | 模型改造 | 现有 27 项测试不改断言仍全绿 |
| 1.3 | 新增 `core/mifare_spec.py` 之外的 `core/mct_compat.py`：`validate_dump_lines` / `validate_key_lines` / `is_valid_block0` / `is_value_block` | 规格对齐层 | 用 MCT 样例文件 + 构造的 6 类非法 dump 覆盖错误码 1–6 |
| 1.4 | 新增 `core/dump_codec.py`，从 `MifareDump` 剥离全部格式解析；实现 mct/eml/bin/mfd/json 五种读写 | 编解码层 | **每种格式 × 四种容量 round-trip 全等**（共 20 组用例） |
| 1.5 | `.eml` 支持：**纯 ASCII 32hex 行、无 magic/无头**；行数必须 ∈ {20,64,128,256}；空行即报错；大小写不敏感；尾块是普通行（内含 KeyA/AC/GPB/KeyB） | EML | 用上游 `mfd2eml.py` 做外部预言机（**注意 `mct2eml.py` 有末尾扇区缺口，不要拿它当预言机**） |
| 1.6 | `.json` 支持：头部必须为 `{"Created": "MifareClassicTool", "FileType": "mfcard", "blocks": {...}}`，块键为**十进制绝对块号字符串** | JSON | 与 MCT 输出的缩进/键序/尾逗号形式一致；导入时拒绝跳号 blocks |
| 1.7 | `.keys` 支持：整行/行内 `#` 注释、trim、纯 hex、严格 12 字符、至少一把钥匙 | 密钥文件解析 | 错误码 1/2/3 全覆盖；`std.keys`/`extended-std.keys`/`hotel-std.keys` 三个上游文件**全部解析成功** |
| 1.8 | 块级双状态：`BlockState` 扩展为 `UNREAD / OK / FAILED / NO_DATA(整扇区无可读) / KEY_UNKNOWN`，并让尾块 key 段可单独标记 `NO_KEY` | 状态模型 | UI 三态渲染测试（`run_tests.py:443` 那条）需扩展到五态 |
| 1.9 | `save_mct` 输出严格符合 `Common.java:1446` 正则：`+Sector: N`（无前导零、单空格） | 格式严格性 | 正则断言 + MCT 预言机校验 |
| 1.10 | 几何硬编码守门 | CI 脚本 | `grep -nE "sector \* 4|block_idx // 4|range\(64\)" core/ ui/` 返回空（白名单注释除外） |

**Phase 1 验收门**：`python tests/run_tests.py` ≥ 55 项全绿；上游三个 `.keys` + 三份样例 dump 全部可读写；预言机通过。

### Phase 2 —— 分析编辑工具对齐（预计 4–6 人日）

**目标**：把 MCT 工具菜单的 9 个工具补齐到 PyQt6 工作台。

| # | 任务 | 文件 | 验收 |
|---|---|---|---|
| 2.1 | `core/value_block.py`：判定（严格按 `Common.java:1398-1414`）、解析为 int（小端有符号）、构造、地址校验 | 新增 | 黄金样例：`00..`/`FF..`/典型余额块全部判定与取值正确 |
| 2.2 | Value Block 工具页（对标 ValueBlockTool + ValueBlocksToInt） | `ui/tag_tools.py` | 输入 32hex → 输出值/地址/是否合法；可反向构造 |
| 2.3 | BCC 工具：**只有 4 字节 UID 的 BCC 可直接移植**（逐字节 XOR）；7/10 字节 UID 的 BCC1/BCC2 上游无实现，需按 ISO/IEC 14443-3 自行实现（CL2/CL3 cascade 规则），并明确标注与 MCT 的差异 | `ui/tag_tools.py` | 对 `D7 7E A0 DF` 得 `46`；7/10 字节按 cascade XOR 分组验证 |
| 2.4 | Tag Info 页（UID/SAK/ATQA/ATS/容量；广播链路下 SAK/ATQA 显示"不可得"并说明原因） | `ui/tag_tools.py` | 广播适配器下不得伪造 SAK/ATQA |
| 2.5 | 制造日期解码：取 **Block 0 最后 2 字节 BCD**，分别按周/年解码（`DumpEditor.java:765-818`；**U-1 已确认**） | `core/mct_compat.py` | 用 MCT 样例 Block 0 验证解码结果 |
| 2.6 | AC 工具对齐：补 GPB 字节语义、非法组合可视化、"能否写尾块"判定 | `ui/dictionary_tools.py` 或 `ui/tag_tools.py` | 8×8 表逐项与 `res/values/access_conditions.xml` 中文文案一致 |
| 2.7 | 编辑器增强：ASCII 视图切换、复制所有扇区、粘贴到扇区、随机填充、清空扇区 | `ui/sector_table.py` | 每项有 UI 无头测试 |
| 2.8 | Diff 引擎抽离 + 四容量（修 N-8） | `core/dump_diff.py` + `ui/dump_diff.py` | 4K 卡差分扇区号正确；文件过滤器补 `*.mct *.eml *.json` |
| 2.9 | Dump 写卡前校验（`validate_dump_lines` + Block0 合法性）并在 UI 给出阻断式提示 | `ui/sector_table.py` | 非法 dump 无法进入写卡流程 |

**Phase 2 验收门**：工具页 ≥ 5 个新页签全部可无头渲染；测试 ≥ 70 项。

### Phase 3 —— 密钥体系 + Key Map + 硬件抽象落地（预计 5–7 人日）

**目标**：这是"合并"的**核心阶段**。用 Mock 适配器把整条读卡链跑通，让真机接入只剩"写一个 adapter 类"。

| # | 任务 | 文件 | 验收 |
|---|---|---|---|
| 3.1 | `core/keys_file.py`：`.keys`/keys.bin 读写、去重（对标 KeyEditor 去重）、合并内置三档字典 | 新增 | 上游三档字典导入后去重计数正确 |
| 3.2 | `ui/key_editor.py`：密钥文件列表/编辑/校验/导入/导出/去重（对标 KeyEditor + FileChooser） | 新增 | 无头测试覆盖增删改与非法输入 |
| 3.3 | **删除 N-9 重复密钥源**：`core/card_service.py:20-37` 与 `ui/dictionary_tools.py:16-33` 统一为 `core/keys_file.py` 的内置字典；字典页改为可编辑并可直接喂给破解/读卡 | 改造 | grep 全仓只有一个内置密钥列表 |
| 3.4 | `core/key_map.py`（§5.2-B） | 新增 | 单测：构建/合并/从 dump 提取/导出 .keys |
| 3.5 | `core/adapters/base_adapter.py` 升级为 §5.2-C（能力 + 扇区级默认算法，把 `MCReader.readSector`/`readAsMuchAsPossible` 语义移植进基类） | 改造 | 单测：用 Mock 验证 NO_DATA/NO_KEY/Key B 可读时不可认证/全失败返回 None 四条 NXP 规则 |
| 3.6 | `core/adapters/mock_adapter.py`：内存虚拟卡（可配置容量、每扇区密钥、可写保护、魔术卡），支持注入故障（认证失败/块读失败/标签丢失） | 新增 | 可在无硬件下跑完"读整卡→得到 Dump+KeyMap→写整卡→校验一致"闭环 |
| 3.7 | `core/card_service.py` 改造为基于 `BaseReaderAdapter`（§5.2-E），块号全走 `TagGeometry`，修复 N-4 | 改造 | Mock 下 4K 卡（含 16 块大扇区）读/写/破解全部正确 |
| 3.8 | Key Map 破解（字典）重写：遍历 key 文件 × 目标扇区，产出 `KeyMap`，支持取消；**保留上游三条经验规则**（命中 key 前移、`FFFFFFFFFFFF` 提前、存在全 0 密钥时插到 index 1）；**可写性矩阵用整数码 0–6**（`isWritableOnPositions` 语义，见 U-2 结论） | 改造 | Mock 下命中率 100%；取消后 UI 必须收到 `sig_finished`（修 N-16） |
| 3.9 | `ui/key_map_view.py`：扇区 × (KeyA, KeyB) 矩阵，可编辑、可导出 `.keys` | 新增 | 无头测试 |
| 3.10 | `ui/main_window.py`：适配器工厂（选择广播/Mock/PCSC/libnfc）+ 能力分档灰化 | 改造 | 四种适配器切换不崩 |
| 3.11 | 写卡增强：**优先使用 dump 内密钥**（对标 MCT 4.3.0 的 "Use keys from dump when writing a dump first"）、写后回读校验、尾块写保护二次确认 | 改造 | Mock 下写入选错密钥的卡会明确报"密钥不匹配"而非静默失败 |

**Phase 3 验收门**：Mock 适配器下完整读/写/破解闭环可复现；测试 ≥ 100 项；真机接入只需新增一个 `adapter` 文件。

### Phase 4 —— 真机双向读写与攻击（预计 6–10 人日，依赖硬件到位）

**目标**：把 Tier 2 能力点亮。三条硬件路线，**建议按 4.1 → 4.2 → 4.3 的优先级实施**。

| 路线 | 依赖 | 能力 | 代价 | 建议 |
|---|---|---|---|---|
| 4.1 **nfcpy + PN532**（USB/TTL 直连） | `nfcpy>=1.0.4`（实测可装） | 认证/读块/写块/魔术卡 UID（`InCommunicateThru` 直发 MFC 0x40/0x41/0x42/0x43） | 需自写 PN532 帧层；无破解算法 | **首选**：纯 Python、无外部 EXE、可打包 |
| 4.2 **pyscard / PC-SC**（ACR122U 等） | `pyscard`（需装）；Windows 需 PC/SC 服务 | 认证/读块/写块（伪 APDU）| 不支持 Nested/Darkside 破解 | **次选**：兼容面广，但能力受限 |
| 4.3 **libnfc CLI**（`nfc-mfclassic.exe` 等） | 需自备 `nfc-bin/` 二进制（**仓内不存在**） | 整卡 dump/写 + `mfoc` 破解 | 发布体积大、二进制来源与许可证需审查 | **第三**：作为攻击后端保留（`attack_runner.py` 已有外壳） |

| # | 任务 | 验收 |
|---|---|---|
| 4.1 | 选定路线并实现 adapter；`caps` 如实声明能力 | `nfc-list` 等效扫描能拿到 UID/SAK/ATQA，并据此推断容量 |
| 4.2 | 真机 Key Map 破解（字典模式）联调，产出 KeyMap | 对一张已知密钥的测试卡 100% 命中；日志可复现 |
| 4.3 | 真机整卡读（`read_as_much_as_possible`） | 与手机 MCT 读出的 `.mct` 逐块比对一致（人工核对 + 差分工具） |
| 4.4 | 真机整卡写（含 Block0 保护开关、尾块二次确认、写后回读校验） | 写入后用 MCT 读出内容一致 |
| 4.5 | 魔术卡 UID 克隆：**MCT 只提供 Gen2（CUID）直写参考**（`writeBlock(0,0)`），Gen1a（`0x40`/`0x43` 后门）**上游没有实现，必须自行按 ISO/IEC 14443-3 与 proxmark3 资料新写**；Gen3 APDU（`90 F0 CC CC 10`）上游已禁用，默认不实现或仅在明确警告后开放 | 写入后读回 UID 与目标一致；非魔术卡明确拒绝并**不误写 Block 0** |
| 4.6 | Value Block 写入路径（increment/decrement/restore/transfer） | 在支持该权限的卡上完成一次充值/扣款并回读验证 |
| 4.7 | 攻击后端（`mfoc` 输出解析 → KeyMap；`mfcuk`/`mfdetect` 结果呈现） | 解析器单测用真实文本输出做夹具 |
| 4.8 | 硬件在环测试骨架 `tests/hw/`（默认 `skip`，用环境变量开关） | CI 不因无硬件失败 |

**Phase 4 验收门**：至少一条路线可完成"读卡 → 得到 Dump+KeyMap → 写另一张卡 → 回读一致"的端到端。

### Phase 5 —— 备份/首选项/收尾（预计 3–5 人日）

| # | 任务 | 文件 | 验收 |
|---|---|---|---|
| 5.1 | Import/Export 工具：批量导入、格式互转矩阵（mct↔eml↔bin↔json）、ZIP 备份（对标 `backupDumpsAndKeys`） | `ui/import_export.py` | 批量转换 4×4 矩阵全通过；ZIP 可还原 |
| 5.2 | 首选项（`QSettings`）：默认密钥文件、默认写保护、ASCII 显示、缓存目录、日志级别 | `ui/preferences.py` | 重启后生效 |
| 5.3 | AGENTS.md / README / PROTOCOL_SPECIFICATION 全面更新，新增本文件的实施进度表 | `docs/` | 文档与代码一致（用测试断言测试数量） |
| 5.4 | i18n（可选）：`QTranslator` 接入，先做 zh_CN + en | `i18n/` | 语言切换不崩 |
| 5.5 | 打包（可选）：PyInstaller one-folder + 图标；确认 DTR/RTS 与 COM 枚举在打包后正常 | `packaging/` | 干净机器可运行 |

**Phase 5 验收门**：交付物 = 可分发目录 + 完整文档 + ≥ 140 项测试全绿。

---

## 7. 验证与质量保障

### 7.1 三层预言机（这是"我们没有 Android 手机也能证明兼容"的关键手段）

| 层 | 预言机 | 用法 | 覆盖 |
|---|---|---|---|
| **L1 规格复刻校验** | `core/mct_compat.py::validate_dump_lines` / `validate_key_lines` / `is_valid_block0` / `is_value_block`（按 `Common.java:1398-1544,1620-1732` 的错误码语义复刻） | 作为**测试内的断言器**：本工具产出的任何 dump/key 文件都必须 `== 0` | 结构合法性、边界、错误码 |
| **L2 上游脚本交叉验证** | MCT 自带的**纯标准库** Python 转换器：`tools/dump-file-converter/{eml2mct,mct2eml,eml2mfd,mfd2eml}.py`、`tools/key-file-diff/key-file-diff.py` | 在测试中 `subprocess` 调用，把本工具的 `.eml`/`.mct` 与上游脚本的输出**逐行比对** | 格式字节级等价性（R1 路线下合法；R2 路线下**禁止**，只能用 L1） |
| **L3 真机对照** | 手机 MCT 读同一张卡 → 导出 `.mct` → 与本工具读出的 `.mct` 用 `core/dump_diff.py` 比对 | 手工 + 脚本化（`tests/hw/`） | 硬件路径正确性 |

**L2 的具体验收脚本骨架**（`tests/interop/test_format_oracle.py`）：

```python
MCT_TOOLS = Path(r"D:\Workspace\Works\Github\MifareClassicTool\tools")

def test_mct_export_matches_upstream(tmp_path):
    dump = build_reference_dump()            # 1K/2K/4K/Mini 参数化
    ours = tmp_path / "ours.eml"
    save(dump, ours, DumpFormat.EML)
    upstream = tmp_path / "upstream.mct"
    subprocess.run([sys.executable, str(MCT_TOOLS / "dump-file-converter" / "eml2mct.py"),
                    str(ours), str(upstream)], check=True)
    expected = "".join(l + "\n" for l in dumps_mct_lines(dump))
    assert upstream.read_text() == expected
    assert validate_dump_lines(upstream.read_text().splitlines()) == 0
```

> 注意：L2 是**可选依赖**——CI 中若 `MCT_TOOLS` 不存在则 `skipTest`，保证 PyMifareTool 可独立构建。

### 7.2 测试金字塔与新增用例清单

| 层 | 现有 | 计划新增 | 关键用例 |
|---|---|---|---|
| 单元（纯算法） | 8 项（`run_tests.py:38-127`） | +35 | 几何往返（4 容量 × 5 方法）；AC 字节↔矩阵往返 ×256 组合；权限表 8+8 行逐项；Value Block 判定/编解码边界（INT_MIN/MAX、非法 addr）；BCC 4 字节 + 7/10 字节 cascade；`validate_dump_lines` 错误码 1–6；`validate_key_lines` 错误码 1–3 |
| 集成（模型+编解码） | 9 项（`:128-313`） | +30 | 5 格式 × 4 容量 round-trip（20）；损坏输入拒绝（5）；NO_DATA/NO_KEY 保持不丢语义（4）；`is_valid_block0` 校验；**写卡安全回归：含 UNREAD 块的 dump 不得写出 `00`、非法 AC 尾块被拒、认证失败即中止、取消必发 `sig_finished`（+5）** |
| 适配器（Mock） | 0 | +15 | `read_as_much_as_possible` 合并；Key B 可读时不可用于认证；全块失败 → `None`；认证中途标签丢失；写块权限拒绝；魔术卡分支 |
| GUI（offscreen） | 4 项（`:370-469`） | +20 | 新 Tab 渲染；能力分档灰化；密钥编辑器增删改；Dump 编辑操作各一项 |
| 隔离与卫生 | 0 | +3 | 测试不得写项目 `cards.db`（跑前后对比行数/哈希）；测试可在任意 CWD 运行；全文件 UTF-8 无 BOM |
| 互操作 | 0 | +8 | 上游 `example-dump-file.txt` / `example-dump-file.raw` / 三档 `.keys` 全部可读；L2 交叉验证 |
| 硬件在环 | 1 项（跳过） | +6 | 真机读/写/破解/魔术卡，默认 skip |
| **合计** | **27** | **+117** | **≈144 项** |

**验收原则**：新增用例必须"能失败"——每个用例先故意破坏实现确认其转红（mutation check），再恢复。禁止新增只 `print` 不 `assert` 的伪用例。

### 7.3 代码守门（CI 静态规则）

```bash
# 1) 几何硬编码守门
grep -rnE "sector\s*\*\s*4|block_idx\s*//\s*4|range\(64\)|:\s*64\s*\]" core/ ui/ && exit 1
# 2) 密钥来源唯一性守门（N-9）
[ "$(grep -rln 'FFFFFFFFFFFF' core/ ui/ | wc -l)" -eq 1 ] || exit 1
# 3) DTR/RTS 红线守门
grep -rn "dtr = False" core/ && grep -rn "rts = False" core/
# 4) 编码守门：仓库内不得出现 BOM 或非 UTF-8 源文件
python tools/check_encoding.py
# 5) 测试全绿
QT_QPA_PLATFORM=offscreen python tests/run_tests.py
```

### 7.4 每次提交的 Definition of Done

1. 全量测试全绿（`tests/run_tests.py` 退出码 0）；
2. 新增/修改的功能有对应测试，且做过 mutation check；
3. `git` 提交信息含阶段号（如 `[P1] add eml/json codec`）；
4. 涉及硬件行为的改动必须在 `tests/hw/` 留一条可复现步骤（含卡型号、密钥、读卡器型号）；
5. 文档同步（`AGENTS.md` 测试数、`docs/PROTOCOL_SPECIFICATION.md` 格式章节）。

---

## 8. 风险登记册、决策点与待确认项

### 8.1 决策点（必须在对应阶段前定案）

| ID | 决策 | 截止 | 默认建议 |
|---|---|---|---|
| **D1** | 许可证路线：R1 接受 GPLv3 / R2 clean-room | Phase 0 开始前 | **R1** |
| **D2** | Tier 2 硬件路线：nfcpy+PN532 / PC-SC / libnfc CLI | Phase 3 结束前 | **nfcpy+PN532**（纯 Python、无外部 EXE；实测 nfcpy 可安装） |
| **D3** | 广播读卡器的产品定位：保留为"发卡/登记"通道，还是逐步淘汰 | Phase 3 前 | **保留**（它是当前唯一真实硬件，且刷卡流水闭环是独有价值） |
| **D4** | 是否把 Key Map 落盘（MCT 不落盘，本工具可做差异化） | Phase 3 内 | **做**：新增 `*.lmap.json` 密钥地图文件 |

### 8.2 风险登记册

| ID | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| R-1 | GPLv3 传染导致无法闭源分发 | 高（若 R1） | 高 | Phase 0 决策；商业诉求强则转 R2 并请法务 |
| R-2 | 广播硬件导致 60% 功能"看得见点不动"，用户体验反降 | 高 | 中 | **能力分档灰化 + 明确引导**（§5.2-F）；离线工作流做成第一等公民 |
| R-3 | 写了错误 UID/尾块导致实体卡报废 | 中 | **极高** | Block 0 默认保护；尾块写入二次确认 + 写前 `is_valid_block0` 校验；魔术卡非魔术卡严格区分；写后必回读比对 |
| R-4 | 外部攻击工具（mfoc 等）来源与许可证不明，随包分发有法律风险 | 中 | 中 | 不随包分发二进制，只做"用户自备路径 + 版本检测"（`attack_runner.py:26-27` 已有 `is_tool_available`） |
| R-5 | 2K/Mini 支持引入回归，破坏现有 1K/4K | 中 | 中 | 参数化 round-trip 测试 + 现有 27 项断言零改动 |
| R-6 | PID/VID 或 COM 口变化导致连接失败 | 中 | 低 | 保留现有端口枚举与手选（`ui/main_window.py:436-445`） |
| R-7 | `.venv` 非隔离导致"我这能跑" | 中 | 中 | Phase 0 重建 venv + `requirements.txt` 版本上界；文档写明 |
| R-8 | 上游 MCT 升级（如 4.4 引入 Gen1a）造成规格漂移 | 低 | 低 | 在 `docs/` 记录对标版本号 4.3.1，升级时走一次 §7.1 L2 回归 |

### 8.3 待确认项（禁止臆造，需实测/查证后才可写入代码）

| ID | 待确认 | 影响 | 确认方式 |
|---|---|---|---|
| **U-1** | ~~「解码制造日期」的算法~~ **已确认**：取 Block 0 **最后 2 字节 BCD**，按周/年解码（`DumpEditor.java:765-818`）。注意此"制造日期"来自**克隆卡自带的厂商数据段**，对原厂卡有意义、对写入过的卡无意义，UI 需加说明 | Phase 2.5 | 已完成 |
| **U-2** | ~~KeyMapCreator 结果矩阵字符 `-`/`1`/`2`/`3`~~ **已确认不存在于 4.3.1**（全仓无字符矩阵实现）。替代语义：`*`=死扇区、`-`=NO_KEY/NO_DATA、以及 `MCReader.isWritableOnPositions` 的整数码 **0–6** | Phase 3.8/3.9 | 已完成；实现改为"整数写权限码 + 可写性矩阵" |
| **U-3** | AOSP `MifareClassic.getSectorCount/getBlockCount/getSize` 由 SAK 推导的确切映射（本仓库只是转发平台调用，`MCReader.java:1127,1142,1150`） | 容量自动识别 | 查 AOSP `MifareClassic.java`；或直接用 SAK 表知识库（4B: 08→1K/2K、09→Mini、18→4K；7B: 38→1K/2K、39→Mini、3A→4K，**需再核**） |
| **U-4** | Java `US_ASCII` 对 ≥0x80 字节的解码替换行为（影响 hexdump ASCII 预览逐字节一致） | 文本预览 | 跑一段 Java 小样例确认，或明确声明"不保证与 MCT 逐字节一致" |
| **U-5** | 扇区尾块边界口径：`MCReader.java:754/826` 用 `sector<=31`，`WriteTag.java:1104` 用 `sector<31`（off-by-one 嫌疑） | 4K 写卡 | 以 `MCReader`（≤31）为准；真机上验证扇区 31/32 的尾块行为 |
| **U-6** | `MCReader.readAsMuchAsPossible()` 无参版本 `while` 边界依赖自重置逻辑（`MCReader.java:182-186`） | Key Map 遍历正确性 | 移植时**改写为显式区间循环**，不做等价复刻 |
| **U-7** | MCT dump `.bin/.mfd` 的 2K（2048B）在真机上的实际产出是否与 1K 拼接一致 | 格式互操作 | 用 2K 卡实测 |
| **U-8** | `.mct` 中 `*` 行在三方工具（如 proxmark3、MifareOneTool）中的兼容性 | 互操作 | 生成含 `*` 的文件做三方交叉测试 |
| **U-9** | `Common.saveFileAppend` 在 append dump 时是否真的抛 NPE（静态阅读推断：`newLines[0]` 为 `null`） | 提示不要照抄上游 Append | 用 Java 小样例复现，或直接在 Python 侧**不实现**该语义（推荐） |
| **U-10** | `help.html:344` 称出厂态 AC 为 `0xFF078000`，而代码与样例实证 GPB=`0x69`（末扇区 `0xBC`） | 文档一致性 | 以**代码与 `example-dump-file.raw` 实证**为准 |
| **U-11** | `.json` 输入含 `-` 占位符时 `hex2Bytes` 返回 `null` 在 MCT→JSON→BIN 之外分支的表现 | JSON 容错边界 | 构造含 `-` 的 JSON 在 MCT 侧实测 |
| **U-12** | Proxmark3 现代客户端 `.eml` 是否存在 4K 分段等其它变体 | EML 兼容性 | 用真实 Proxmark3 输出样本比对 |

### 8.4 反向风险（合并"吃掉"了 PyMifareTool 的优势）

| 风险 | 缓解 |
|---|---|
| 照抄 MCT 导致 UI 变成"Android 界面的桌面版"，丢失暗黑一体化工作台体验 | 只移植**能力**，不移植布局；所有新功能进现有 QSS 体系与 Tab 结构 |
| 破坏 SQLite 发卡档案 / 韦根换算 / 报文监视器等独有功能 | Phase 0.9 起每次改动跑全量回归；这三块列为"冻结区"，改动需单独评审 |
| 引入 `pyscard`/`nfcpy` 让打包变复杂 | 全部硬件后端做成**可选依赖**（`requirements-hardware.txt`），缺依赖时自动降级到 Mock/广播，不阻断启动 |

---

## 9. 立即可执行的第一周清单（可直接照做）

> 顺序即优先级；每完成一项打勾并跑一次 `QT_QPA_PLATFORM=offscreen python tests/run_tests.py`。

```text
第 1 天 —— 止血与合规（对应 Phase 0）
[ ] 1. 决策 D1，写 docs/decisions/ADR-0001-license.md（建议 R1：GPLv3）
[ ] 2. git init + .gitignore + 首次提交 + tag v1.0-baseline
         （.gitignore 必须含 cards.db / scratch/，不要把真实卡数据入库）
[ ] 3. 确认并删除 matplotlib-e___mire\（先 Test-Path 绝对路径核对）
[ ] 4. requirements.txt 加上界：pyserial>=3.5,<4 / PyQt6>=6.6,<7
[ ] 5. 修 core/dump_model.py:371-388 的 2K 截断（N-1），补 3 条测试
[ ] 6. 修 core/adapters/libnfc_adapter.py:71-73 的假成功（N-7）
[ ] 7. 🔴 修 tests/run_tests.py 的测试污染：改用 tempfile 临时库 + 去掉 :30 硬编码路径（N-15）
[ ] 8. 🔴 修 core/card_service.py:277-290 写卡安全：跳过非 READ_OK 块 + 尾块 AC 校验 +
        authenticated 为假即中止（N-13/N-14/N-19）
[ ] 9. 修 core/card_service.py:130-142,185-186 取消路径不发 sig_finished（N-16）

第 2 天 —— .mct 零污染（对应 Phase 0.6/0.7）
[ ] 7. save_mct 对 UNREAD/READ_FAILED 块输出 NO_DATA、整扇区输出 '*'
[ ] 8. load_mct 识别 '*' 与 '----'
[ ] 9. 新建 tests/interop/，写入 L1 校验器测试 + L2 上游 eml2mct 交叉验证
[ ] 10. 用 MCT 的 tools/example-files/example-dump-file.txt 做一次载入→导出→比对

第 3 天 —— 几何单一真相源（对应 Phase 1.1/1.2）
[ ] 11. 新建 core/mifare_spec.py（Mini/1K/2K/4K）
[ ] 12. core/dump_model.py 接入 geometry，保留 is_4k 兼容属性
[ ] 13. 回归：现有 27 项断言零改动全绿
[ ] 14. 加几何硬编码守门脚本

第 4-5 天 —— 格式内核（对应 Phase 1.4-1.7）
[ ] 15. 新建 core/dump_codec.py，迁移 .mct/.bin/.mfd/.txt 解析
[ ] 16. 实现 .eml（无头、行数 ∈{20,64,128,256}、空行报错）
[ ] 17. 实现 .json（{"blocks":{"0":"..."}}）
[ ] 18. 实现 .keys 解析（注释/trim/12 字符/至少一把）+ keys .bin
[ ] 19. 20 组（5 格式 × 4 容量）round-trip 测试

第 6 天 —— 文档与收口（对应 Phase 0.8/1.10）
[ ] 20. 更新 AGENTS.md（测试数、目录树、新增模块）+ README 格式矩阵
[ ] 21. 更新 docs/PROTOCOL_SPECIFICATION.md，补 MCT 格式规格（§附录 A）
[ ] 22. 全量测试 + git tag phase-0、phase-1
```

---

## 附录 A：MCT 文件格式速查表（可直接作为实现规格）

| 格式 | 类型 | 结构 | 合法尺寸 | 关键规则 | 证据 |
|---|---|---|---|---|---|
| `.mct` | 文本 | `+Sector: N` + 每块 32 hex 行 | 扇区 0–39 | 头正则 `^\+Sector: [0-9]{1,2}$`（**单空格、无前导零**）；`s<32`→4 块，`s>=32`→16 块；4/16 块后必须紧跟新头；**扇区号不得重复**；死扇区 `*No keys found or dead sector`（写卡时拒绝含 `*` 的 dump） | `Common.java:1443-1489`、`ReadTag.java:132-138`、`WriteTag.java:758` |
| `.eml` | 文本 | 每行 32 hex，**无头无 magic** | 行数 ∈ {20,64,128,256} | 空行即判不完整；尾块是普通行；大小写不敏感 | `ImportExportTool.java:593-611`、`mfd2eml.py:34-40` |
| `.bin` / `.mfd` / `.raw` | 二进制 | 16×N 原始字节 | **精确** 320 / 1024 / 2048 / 4096 | 无文件头；**尾块内联**（含 KeyA/AC/GPB/KeyB）；不按扩展名判格式 | `ImportExportTool.java:573-591`；`example-dump-file.raw` 实证 |
| `.json` | 文本 | `{"Created":"MifareClassicTool","FileType":"mfcard","blocks":{...}}` | 同 .bin | 键为**十进制绝对块号字符串**；导入必须含 `0..n-1` 全部键 | `ImportExportTool.java:541-571,686-692` |
| `.keys` | 文本 | 每行 1 把 6 字节密钥 | ≥1 行 | `#`（整行/行内）注释；trim；纯 hex；**恰好 12 字符**；**`000000000000` 是合法密钥，不得剔除** | `Common.java:1505-1544`、`DumpEditor.java:988-1001` |
| keys `.bin` | 二进制 | 6 字节密钥串联 | 长度 %6==0 | | `ImportExportTool.java:760-778` |
| 哨兵 | — | `NO_KEY` = 12×`-`；`NO_DATA` = 32×`-`；`DEFAULT_KEY` = `FFFFFFFFFFFF` | — | Key 段缺失用 `NO_KEY`，块不可读用 `NO_DATA` | `MCReader.java:51-59` |

**尾块字符偏移（务必与 AC 的 3 字节语义区分）**

```
hex偏移  0        12       18     20        32
字节     0..5     6..8     9      10..15
含义     Key A    AC(3B)   GPB    Key B
```
出厂态 `FFFFFFFFFFFFFF078069FFFFFFFFFFFF`；**末扇区 GPB=0xBC**（`example-dump-file.txt:80` 与 `.raw` 末 16 字节实证一致）。静态 AC 批量替换**只覆盖 `[12,18)`，保留 GPB**（`WriteTag.java:921-924`）。

**AC 字节布局（尾块 byte6/7/8）**

```
acBytes[0]=byte6 = (~C1[0..3] & 0x0F) | (~C2[0..3] << 4)
acBytes[1]=byte7 = (~C3[0..3] & 0x0F) | ( C1[0..3] << 4)
acBytes[2]=byte8 = ( C2[0..3] & 0x0F) | ( C3[0..3] << 4)
合法性: byte7>>4 == ~byte6 & 0x0F  且  byte8 & 0x0F == ~byte6>>4 & 0x0F  且  byte8>>4 == ~byte7 & 0x0F
出厂默认 FF 07 80 69 → 数据块 (C1,C2,C3)=(0,0,0)、尾块=(0,0,1)
```
证据：`Common.java:1263-1348`、`AccessConditionTool.java:330-412`。

**数据块权限 8 行**（`0=Never 1=KeyA 2=KeyB 3=KeyA|B`；**KeyB 可读时 `A|B` 退化为 `KeyA`**）

| C1C2C3 | Read | Write | Increment | DecTransRest |
|---|---|---|---|---|
|000|A\|B|A\|B|A\|B|A\|B|
|010|A\|B|Never|Never|Never|
|100|A\|B|B|Never|Never|
|110|A\|B|B|B|A\|B|
|001|A\|B|Never|Never|A\|B|
|011|B|B|Never|Never|
|101|B|Never|Never|Never|
|111|Never|Never|Never|Never|

**尾块权限 8 行**

| C1C2C3 | ReadKeyA | WriteKeyA | ReadKeyB | WriteKeyB | ReadAC | WriteAC |
|---|---|---|---|---|---|---|
|000|Never|A|A|A|A|Never|
|010|Never|Never|A|Never|A|Never|
|100|Never|B|Never|B|A\|B|Never|
|110|Never|Never|Never|Never|A\|B|Never|
|001|Never|A|A|A|A|A|
|011|Never|B|Never|B|A\|B|B|
|101|Never|Never|Never|Never|A\|B|B|
|111|Never|Never|Never|Never|A\|B|Never|

`isKeyBReadable(c1,c2,c3)` ⇔ `c1==0 且 (c2,c3) ∈ {(0,0),(1,0),(0,1)}`（尾块行 000/010/001）。证据：`Common.java:1109-1252`、`MCReader.java:1085-1096`。

**Value Block 16 字节**

```
[0:4] value (小端有符号 int32)   [4:8] ~value
[8:12] value (重复)              [12] addr  [13] ~addr  [14] addr  [15] ~addr
```
证据：`Common.java:1398-1414`；解析 `struct.unpack('<i', b[0:4])`；构造 `struct.pack('<i', v)`。

**Block 0 布局**

```
UID(4/7/10 B) | BCC(1B，仅 4 字节 UID 时存在且需计算) | SAK(1B) | ATQA(2B) | 其余厂商数据
4 字节 UID: block0 = uid(8hex) + BCC(2hex) + SAK(2hex) + ATQA(4hex) + 8 字节其它
7/10 字节: 整块透传，BCC1/BCC2 由调用方提供（MCT 无实现）
```
证据：`CloneUidTool.java:195-210`、`Common.java:1620-1732`。

---

## 附录 B：许可证合规清单（R1 路线）

```text
[ ] 1. PyMifareTool 根目录新增 LICENSE（GPLv3 全文，674 行，与 MCT 一致）
[ ] 2. 新增 NOTICE，列出：
       - MifareClassicTool (c) Gerhard Klostermeier / SySS GmbH，GPLv3，来源 URL
       - 每个被移植文件的来源文件与行号范围
       - proxmark3（MCReader.java:352-353）、SLURP（Common.java:122-128）、
         NXP AN10927/AN10833/AN10834（Common.java:1612-1614）、AOSP MifareClassic
         （MCReader.java:1164-1178）等二次出处
[ ] 3. 每个衍生文件头加：原版权行 + "This file is part of PyMifareTool,
       derived from MifareClassicTool; modified on <date>" + GPLv3 声明
[ ] 4. README 增加"许可证与致谢"章节
[ ] 5. 禁止复制 MCT 的美术资源：Logo（CC BY-NC-SA 4.0）、Oxygen 图标（LGPL）、
       RFID Tag 图（CC 3.0）——这些不是 GPL，需按各自许可单独处理或不用
[ ] 6. extended-std.keys 等密钥汇编的来源需单独评估（文件头注明汇集自
       SLURP / proxmark3 / 公开搜索）
[ ] 7. 不随包分发 mfoc/mfcuk/nfc-bin 等第三方二进制；仅支持"用户指定路径"
[ ] 8. 若最终选 R2（clean-room）：删除一切 MCT 派生代码与注释，
       NOTICE 中声明"仅依据 NXP 应用笔记与 ISO/IEC 14443-3 独立实现"
```

---

## 附录 C：本文件证据索引（关键结论 → 出处）

| 结论 | 出处 |
|---|---|
| 当前硬件是单向广播器，不响应下行指令 | `README.md:25`、`core/card_service.py:229-238`、`tests/run_tests.py:519-527` |
| 适配层是死代码 | 全仓 grep `Adapter` 仅命中 `core/adapters/*` |
| 4K 硬件路径错位 | `core/card_service.py:126,180,202,265,277` vs `core/dump_model.py:83-94` |
| 2K 静默截断 | `core/dump_model.py:375-388` |
| `.mct` 零污染缺陷 | `core/dump_model.py:345-358` vs `MCReader.java:51,55`、`ReadTag.java:132-138` |
| Diff 硬编码 64 块 | `ui/dump_diff.py:123,128` |
| 密钥双份硬编码 | `core/card_service.py:20-37`、`ui/dictionary_tools.py:16-33` |
| 测试实测 27 项 | `QT_QPA_PLATFORM=offscreen python tests/run_tests.py` → `Ran 27 tests ... OK (skipped=1)` |
| MCT 为 GPLv3 | `MifareClassicTool/LICENSE.txt:1-2` |
| Key Map 模型 | `MCReader.java:62,130-159,1106-1109` |
| `readSector` 合并语义 | `MCReader.java:204-290` |
| Key B 可读则不可用于认证 | `MCReader.java:263-282` |
| AC 权限表与合法性 | `Common.java:1109-1348` |
| Value Block 结构 | `Common.java:1398-1414`、`ValueBlockTool.java:76-129` |
| Block 0 校验 | `Common.java:1620-1732` |
| 魔术卡仅 Gen2 直写 | `CloneUidTool.java:223-291`、`MCReader.java:367-392`（Gen3 被禁用）、Gen1a **不存在** |
| 格式规格 | `ImportExportTool.java:556-724`、`Common.java:1434-1544`、`tools/example-files/*` |
| MCT 菜单全集 | `app/src/main/res/menu/*.xml` |

---

## 附录 D：上游 `tools/` 脚本可复用性评估（用于 §7.1 的 L2 预言机）

| 文件 | 作用 | 可复用性判定 |
|---|---|---|
| `dump-file-converter/mfd2eml.py` | 二进制 → `.eml`（16 B/行 `hexlify`，小写） | ✅ **可直接当预言机**（逻辑与待实现功能等价） |
| `dump-file-converter/eml2mct.py` | `.eml` → `.mct`，按 4/16 块插 `+Sector: N` | ✅ **境界公式可移植**，可作 L2 预言机；但**无尺寸校验、不处理 `-`**，仅用于"我方 `.eml` → 上游 `.mct`"单向比对 |
| `dump-file-converter/eml2mfd.py` | `.eml` → 二进制，逐行 `unhexlify` | ⚠️ 仅参考（无校验，遇 `#`/`-` 即抛异常） |
| `dump-file-converter/mct2eml.py` | `.mct` → `.eml`，缺扇区用全 `00` 填充 | ❌ **不要当预言机**：末尾缺失扇区未补（上游自带 TODO），产出的行数可能不是 20/64/128/256，**MCT 自己都会拒收** |
| `key-file-diff/key-file-diff.py` | 读两个 key 文件输出差集；`parse_keys()` 用 `^[0-9a-fA-F]{12}` 行首匹配 | ✅ **`parse_keys()` 逻辑可直接搬进 Python 字典工具** |
| `key-file-converter/prox-keys2mct-keys.sh` | Proxmark 屏幕表格 → `.keys`（`sed` + `sort -u`） | ⚠️ 需 bash/sed，且硬编码第 4–19 行（仅 1K）；建议用 Python 等价正则 `^.{7}([0-9A-Fa-f]{12}).{9}([0-9A-Fa-f]{12})` 重写 |
| `mct-dump2prox-emulator/mct-dump2prox-emu` | expect 脚本驱动 proxmark3 客户端加载 dump 并模拟 | ❌ 不可直接用；但"非 `+` 行即块数据、顺序编号"再次印证 `.mct` 解析模型 |
| `example-files/example-dump-file.txt`（80 行） | 标准 `.mct`，16 扇区 | ✅ **黄金测试向量** |
| `example-files/example-dump-file.raw`（1024 B） | 原始 1K dump，含 KeyA/AC/GPB/KeyB | ✅ **黄金测试向量**（已与 `.txt` 逐字节核对一致） |
| `example-files/example-key-dump.txt` | Proxmark nested attack 屏幕表格（20 行） | ⚠️ **不是** MCT key 格式，只能作为 `prox-keys2mct` 的输入样本，**不可当 `.keys` 解析测试向量** |

---

## 附录 E：与 `REVIEW_REPORT.md` 的关系

* `REVIEW_REPORT.md`（上一轮）解决的是**"项目宣称 vs 硬件事实"的诚实性问题**，其 P0/P1 整改经本轮核验**基本到位**（契约错配已修、`.txt` 解析已修、`_pending_cmd` 已加锁、AC 位序已修正、测试从 15 项增至 27 项）。
* 本文件解决的是**"下一步往哪走、怎么走"的工程路线问题**，并发现上一轮整改遗留的**结构性缺陷**（N-3 适配层未接线、N-4 4K 未接硬件路径）与**本轮新增的高危缺陷**（N-13 写卡静默清零、N-14 尾块无条件写入、N-15 测试污染生产库、N-1 2K 截断、N-5 `.mct` 零污染）。
* ⚠️ **`REVIEW_REPORT.md:11-20` 的 SHA256 基线已全部失效**（实测 12 个文件无一相符），且项目当时无 git，无法回溯。Phase 0.2 建立 git 后，应重新生成一份基线（放在 `docs/baselines/`）。
* 两份文件**不冲突**，建议并列保留：`REVIEW_REPORT.md` = 历史体检报告；本文件 = 路线图与实施指导。

