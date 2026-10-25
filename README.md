# PyMifareTool

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/PyQt6-6.6%2B-41CD52?logo=qt&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D4?logo=windows&logoColor=white)
![Tests](https://img.shields.io/badge/tests-96%20passed-brightgreen)

> 面向 Mifare Classic 1K/4K、二代身份证（ISO/IEC 14443-B）与 ISO/IEC 14443-4 CPU 智能卡的综合上位机。

PyMifareTool 使用 **Python 3.12+ / PyQt6 / pyserial / bleak / SQLite3** 构建，提供串口与 BLE 双通道读卡、扇区矩阵编辑、字典破解、Dump 管理、CPU 卡 APDU 交互、卡片档案与刷卡流水审计等能力，并按协议、模型、传输、适配器、服务、UI 分层组织代码。

---

## 目录

- [功能特性](#功能特性)
- [硬件支持](#硬件支持)
- [项目状态](#项目状态)
- [技术栈](#技术栈)
- [系统架构](#系统架构)
- [环境要求](#环境要求)
- [安装](#安装)
- [快速开始](#快速开始)
- [使用指南](#使用指南)
- [数据与文件](#数据与文件)
- [测试](#测试)
- [项目结构](#项目结构)
- [扩展开发](#扩展开发)
- [贡献](#贡献)
- [安全与合规](#安全与合规)
- [许可证](#许可证)

---

## 功能特性

### Mifare Classic 1K/4K

- 支持 16 扇区 1K（S50）与 40 扇区 4K（S70）；
- 三态扇区矩阵：未读取、已读取、读取失败；
- 双击单元格直接编辑 16 字节块数据；
- 支持 Dump 校验、BCC 修复、Access Bits 校验与尾块修复；
- 支持逐扇区认证、全卡读取、单扇区解密、全卡写入；
- Block 0 默认写保护，仅在显式授权且使用支持的魔术卡时允许改写。

### 密钥与字典

- 标准高频密钥、酒店门锁密钥、扩展密钥与共享字典；
- 当前内置字典合计约 **7.4 万条**密钥（含重复）；
- 三阶段扫描策略：
  1. 高频优先密钥快速筛查；
  2. 已破解密钥跨扇区传播；
  3. 剩余扇区全字典深度扫描；
- 破解结果可回写 SQLite，后续读卡优先复用；
- 受 13.56MHz 半双工限制，认证请求按串行方式执行。

### 魔术卡工具

- 支持 CUID / GEN1A / UFUID 等常见魔术卡类型；
- UID 写号：目标 UID、SAK、ATQA、厂商数据与 BCC 自动组装；
- 随机 UID 生成；
- 工厂化清卡（实验性）；
- UFUID 单向锁死（高风险操作，需二次确认）。

### CPU 智能卡

- 支持 PPSE、PBOC 借记/贷记、交通联合等常见应用；
- 读取余额、卡号、发卡方、有效期与交易流水；
- APDU 控制台：自定义指令、状态字解释、TLV/余额/记录语义解析；
- 自动处理 `61xx` GET RESPONSE 与 `6Cxx` 长度修正；
- COS 文件树扫描与 JSON 导出。

### 二代身份证

- 自适应写入 12 组 Type B CIU 寄存器；
- 完成 `REQB -> ATTRIB -> Read GUID` 时序；
- 读取 8 字节身份证 GUID；
- 读取结束后恢复 Type A 默认寄存器。

### Dump 与数据管理

- 支持 `.dump`、`.mfd`、`.bin`、`.mct`、`.eml`、`.json`、`.txt`；
- 双 Dump 字节级差分；
- SQLite 卡片档案：UID、持卡人、8H10D、WG26、WG34、备注、刷卡次数；
- 刷卡流水审计与 CSV 导出；
- 扇区密钥按 UID/扇区持久化。

### 连接方式

- USB 串口：PCR532 / PN532，115200bps；
- 单向广播器：38400bps，仅接收 UID 上报；
- BLE：Minicopy / WCH CH59x，GATT 透明传输 PN532 HSU 帧；
- 虚拟卡：内存 Dump 仿真，便于无硬件测试。

---

## 硬件支持

| 设备 | 链路 | 方向 | 主要能力 |
|---|---|---|---|
| PCR532 / PN532 | USB 串口 115200bps | 双向 | M1 读写/破解、二代证、CPU 卡、魔术卡 |
| Minicopy / WCH BLE | BLE GATT | 双向 | PN532 HSU 透明传输 |
| 简易广播发卡器 | USB 串口 38400bps | 单向上行 | UID 广播，**不响应下行指令** |
| 虚拟卡适配器 | 内存 | — | 无硬件仿真与自动化测试 |
| libnfc CLI | 外部命令 | 依赖工具链 | `nfc-list` / `nfc-mfclassic` 等，尚未接入 UI |
| PC/SC 读卡器 | PC/SC | 规划中 | 当前仅为适配器骨架 |

> **广播器使用限制**：该设备只主动上报 UID，不能执行认证、读写或寄存器配置。请勿向其发送下行帧。

---

## 项目状态

| 模块 | 状态 | 说明 |
|---|---|---|
| 协议层 / Dump 模型 / SQLite | 稳定 | 有单元测试覆盖 |
| M1 读取 / 破解 / 写入 | 稳定 | 真实硬件路径需自行验证 |
| CPU 卡读取 / APDU 控制台 / 文件树 | 可用 | 依赖卡片与应用实现 |
| 二代身份证 GUID | 可用 | 依赖 PN532 与 Type B 寄存器配置 |
| BLE 连接 | 可用（实验性） | 受设备固件、MTU 与信号影响 |
| 克隆向导 | 实验性 | 接口仍在修复，暂不建议用于生产 |
| 魔术卡工厂化清卡 | 实验性 | 高风险操作，请先备份 Dump |
| 外部攻击工具链 | 可选 | 需自行准备 `nfc-bin` 与对应可执行文件 |
| PC/SC 适配器 | 规划中 | 当前为空壳 |
| libnfc 适配器 | 可用（CLI） | 尚未加入 UI 设备列表 |

---

## 技术栈

| 类别 | 技术 |
|---|---|
| 语言 | Python 3.12+ |
| GUI | PyQt6 6.6+ |
| 串口 | pyserial 3.5+ |
| BLE | bleak 0.22+ |
| 数据库 | SQLite3（WAL 模式） |
| 外部工具 | mfoc / mfcuk / hardnested / mfdetect（可选） |

---

## 系统架构

```text
ui  →  services  →  adapters  →  transport
                         ↘
                       protocols  ←  models
```

| 层 | 目录 | 职责 |
|---|---|---|
| 表现层 | `ui/` | PyQt6 界面、交互编排、可视化 |
| 服务层 | `core/services/` | QThread 串口轮询、卡操作、字典、外部工具 |
| 适配层 | `core/adapters/` | 统一读卡接口与具体硬件适配 |
| 传输层 | `core/transport/` | 串口、BLE、传输工厂 |
| 协议层 | `core/protocols/` | AABB、PN532 HSU、ISO14443-B、ISO7816 |
| 模型层 | `core/models/` | Dump、Access Bits、UID 换算 |

核心约束：

- 协议层只做字节编解码，不持有 I/O 句柄；
- 所有物理读写必须经过 `transport/` 与 `adapters/`；
- UI 不直接操作串口或 BLE；
- 耗时操作放入 Worker，不阻塞主线程；
- 长操作通过 `set_exclusive(True)` 暂停自动轮询。

---

## 环境要求

- Windows 10/11（主要开发与验证平台）；
- Python 3.12 或更高版本；
- 可选硬件：
  - PCR532 / PN532 USB 读写器；
  - Minicopy / WCH BLE 读写器；
  - 38400bps 单向 UID 广播发卡器；
- 使用外部破解工具时，需自行准备 `nfc-bin` 目录及对应可执行文件。

---

## 安装

```powershell
git clone <repository-url>
cd PyMifareTool

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -U pip
python -m pip install -r requirements.txt
```

> 如果 PowerShell 阻止激活虚拟环境，可先执行：
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

---

## 快速开始

```powershell
python main.py
```

基本流程：

1. 选择连接方式：`USB 串口` 或 `BLE`；
2. 选择设备类型；
3. USB 模式选择串口与波特率；
4. BLE 模式点击扫描并选择读卡器；
5. 点击「连接」；
6. 放置卡片，等待自动轮询或点击读卡。

默认波特率：

| 设备 | 波特率 |
|---|---:|
| PCR532 / PN532 | 115200 |
| 单向广播发卡器 | 38400 |

---

## 使用指南

### Mifare Classic

1. 连接读写器并放置 M1 卡；
2. 在扇区表点击「一键读卡」；
3. 未读取扇区可点击「字典破解」；
4. 读取完成后可编辑块、校验/修复 Dump、保存为多种格式；
5. 写卡前请确认目标卡类型与 Block 0 写保护状态。

### CPU 智能卡

1. 切换到 CPU 卡页；
2. 点击自动读取；
3. 查看余额、卡号、有效期与交易流水；
4. 需要调试时使用 APDU 控制台；
5. 文件树扫描可导出 JSON。

### 二代身份证

1. 使用 PN532 连接；
2. 点击「读身份证」；
3. 读取 8 字节 GUID 并显示换算结果。

### BLE 读写器

1. 连接方式选择 BLE；
2. 点击扫描；
3. 选择识别为读卡器的设备；
4. 连接后按 USB 模式操作。

### 外部攻击工具

1. 准备 `nfc-bin` 目录；
2. 放入 `mfoc`、`mfcuk`、`hardnested`、`mfdetect` 等可执行文件；
3. 在「字典工具 → 外部攻击」中配置路径并启动；
4. 工具输出与破解出的密钥会回显到界面。

### 开发调试脚本

`tools/` 下为开发期串口与协议实验脚本，多数直接硬编码 COM 口，**不参与应用运行时**。运行前请确认端口与设备，避免与 `main.py` 同时占用串口。

---

## 数据与文件

### `cards.db`

运行时 SQLite 数据库，包含：

- `cards`：卡片档案；
- `swipe_logs`：刷卡流水；
- `card_keys`：按 UID/扇区保存的密钥。

数据库使用 WAL 模式与线程本地连接。**该文件可能包含个人卡片与刷卡记录，请勿提交到公共仓库。**

### Dump 格式

| 扩展名 | 说明 |
|---|---|
| `.dump` / `.mfd` / `.bin` | 原始二进制 |
| `.mct` | Mifare Classic Tool 文本 |
| `.eml` | 每行一个块 |
| `.json` | 带元数据的结构化格式 |
| `.txt` | 可读文本（扇区横幅 + ASCII） |

### 字典目录

```text
keys/
├── std.keys
├── hotel-std.keys
├── extended-std.keys
└── extended-std_share_key_*.keys
```

其中共享字典体积较大，默认未纳入版本控制；需要完整字典时请自行放入 `keys/` 目录。解析需要一定时间，新增 UI 逻辑时应避免重复全量解析。

---

## 测试

```powershell
python tests/run_tests.py
```

当前基线：

- **96 项测试全部通过**；
- 约 **3 秒**；
- 无头环境自动使用 `QT_QPA_PLATFORM=offscreen`；
- 覆盖协议、Dump、数据库、GUI 渲染、PN532、字典、二代证、BLE、CPU 卡、4K、魔术卡/克隆/攻击器。

测试不能替代真实硬件验证。以下路径仍建议人工回归：

- 克隆向导真实读写；
- 魔术卡工厂化清卡；
- 字典导入与密钥保存；
- 自动设备探测；
- 真实卡片上的 APDU 与 Type B 时序。

---

## 项目结构

```text
PyMifareTool/
├── main.py
├── requirements.txt
├── cards.db
│
├── core/
│   ├── protocols/        # AABB / PN532 / ISO14443-B / ISO7816
│   ├── models/           # MifareDump / Access Bits / UID 换算
│   ├── transport/        # Serial / BLE / TransportFactory
│   ├── adapters/         # PN532 / Broadcaster / libnfc / Virtual / PCSC
│   ├── services/         # SerialWorker / CardOperationWorker / KeyManager / AttackRunner
│   ├── card_db.py
│   └── *.py              # 兼容门面
│
├── ui/
│   ├── main_window.py
│   ├── sector_table.py
│   ├── sector_widgets.py
│   ├── dictionary_tools.py
│   ├── cpu_card_widget.py
│   ├── magic_card_dialog.py
│   ├── clone_wizard_dialog.py
│   ├── crack_dialogs.py
│   ├── card_manage.py
│   ├── key_select_dialog.py
│   └── dump_diff.py
│
├── keys/                 # 字典文件
├── tests/run_tests.py    # 自动化测试
└── tools/                # 开发期调试脚本
```

---

## 扩展开发

开始修改前请先阅读 [AGENTS.md](AGENTS.md)，其中包含：

- 硬件安全红线；
- 协议与数据流说明；
- 核心 API 与信号；
- 测试与编码规范；
- 分层依赖约束。

常见扩展：

1. **新增读卡器**：继承 `BaseReaderAdapter`，在 `ReaderAdapterFactory` 注册；
2. **新增传输通道**：实现 `ITransport`，在 `TransportFactory` 注册；
3. **新增攻击引擎**：继承 `BaseAttackEngine`，使用 `QProcess` 包装外部工具；
4. **新增 UI 工具页**：创建 `QWidget`，挂入 `MainWindow.tabs`，补充无头渲染测试。

---

## 贡献

欢迎提交 Issue 与 Pull Request。

提交前请确认：

- 已阅读 `AGENTS.md`；
- `python tests/run_tests.py` 全部通过；
- 新增功能附带测试；
- 不提交 `cards.db`、个人卡片数据、密钥日志或其他敏感信息；
- 不破坏串口独占、DTR/RTS、Block 0 写保护等硬件安全约束；
- 代码与文本使用 UTF-8（无 BOM）。

---

## 安全与合规

- 本项目仅用于**合法授权的卡片读取、备份、研究与教学**；
- 请勿用于未授权门禁卡、金融卡、身份证件或其他受保护系统；
- 使用前请确认当地法律法规与设备管理规定；
- 修改 Block 0、工厂化清卡、UFUID 锁死等操作可能导致卡片永久损坏，请先备份 Dump；
- 作者不对因使用本项目造成的卡片损坏、数据丢失或法律风险承担责任。

---

## 许可证

当前仓库尚未附带 `LICENSE` 文件，默认保留所有权利。

正式开源前，请补充合适的许可证（例如 MIT 或 Apache-2.0），并在本文件中更新许可证说明与版权信息。

---

## 参考

- NXP PN532 User Manual；
- ISO/IEC 14443-A/B；
- ISO/IEC 7816-4；
- Mifare Classic Tool（MCT）Dump 格式；
- libnfc 工具链。
