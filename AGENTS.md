# AGENTS.md

> **给 AI Agent 的第一读本**  
> 本文件是 PyMifareTool 的项目级上下文与操作规范。开始修改代码前，请先阅读「快速开始」「架构」「硬件红线」三节。  
> 若本文件与源码冲突，**以源码为准**；发现文档过期时，请顺手修正本文件。

---

## 1. 项目速览

| 项 | 内容 |
|---|---|
| 项目名 | `PyMifareTool` |
| 定位 | Mifare Classic 1K/4K、二代身份证（ISO14443-B）、ISO14443-4 CPU 智能卡综合上位机 |
| 语言/框架 | Python 3.12+、PyQt6 6.6+ |
| 通信 | pyserial（USB 串口）、bleak（BLE） |
| 存储 | SQLite3（`cards.db`，WAL 模式） |
| 入口 | `main.py` |
| 测试 | `python tests/run_tests.py` |
| 平台 | Windows 10/11 为主，代码结构支持跨平台 |

### 支持的硬件

1. **PCR532 / PN532 双向读写器**  
   - 115200bps，NXP PN532 HSU 协议；
   - 支持 M1 寻卡、认证、读写、魔术卡、二代身份证 Type B、CPU 卡 APDU。

2. **简易广播发卡器**  
   - 38400bps，单向广播 UID；
   - **物理上不响应任何下行指令**，只能被动接收其 AABB 上行帧。

3. **BLE 无线读写器**  
   - Minicopy / WCH CH59x；
   - 通过 GATT 透明传输 PN532 HSU 帧；
   - 典型服务：WCH `0xFF00`（通知 `FF01`、写 `FF02`）；Minicopy `AE00`（通知 `AE02`、写 `AE01`）。

---

## 2. 快速开始

```bash
# 安装依赖
python -m pip install -r requirements.txt

# 启动应用
python main.py

# 运行全量测试（当前基线：145 项通过，约 2.9 秒）
python tests/run_tests.py
```

无头环境测试会自动使用 `QT_QPA_PLATFORM=offscreen`。

# 启动对外 MCP 服务 (stdio 模式)
python mcp_server.py

# 启动对外 MCP 服务 (SSE 网络模式)
python mcp_server.py --transport sse --host 0.0.0.0 --port 8000

**不要**在未确认硬件连接的情况下运行 `tools/` 下的串口脚本；它们多数直接硬编码 COM 口。

---

## 3. 目录地图

```text
PyMifareTool/
├── main.py                     # 应用入口
├── requirements.txt
├── cards.db                    # 运行时 SQLite（卡片档案/流水/扇区密钥）
│
├── core/
│   ├── protocols/              # 无状态协议编解码（禁止持有 I/O）
│   │   ├── base.py             # BaseProtocolCodec / 协议异常
│   │   ├── aabb.py             # AA BB 广播器协议
│   │   ├── pn532.py            # PN532 HSU 帧
│   │   ├── iso14443b.py        # 二代证 CRC-B / REQB / ATTRIB / GUID
│   │   └── iso7816.py          # APDU、TLV、PBOC/交通联合解析
│   ├── models/                 # 领域模型
│   │   ├── dump.py             # MifareDump、BlockState、MCT/EML/JSON/TXT
│   │   ├── access_bits.py      # Access Bits 编解码
│   │   └── card_converter.py   # UID 正逆序 / 8H10D / WG26/34
│   ├── transport/              # 物理传输
│   │   ├── base.py             # ITransport + 鸭子类型兼容包装
│   │   ├── serial_transport.py # 串口，强制 DTR/RTS=False
│   │   ├── ble_transport.py    # BLE，后台 asyncio + MTU 分片
│   │   ├── ble_classifier.py   # BLE 设备分类
│   │   ├── tcp_transport.py    # TCP / Modbus TCP
│   │   └── factory.py          # TransportFactory
│   ├── adapters/               # 硬件适配
│   │   ├── base_adapter.py     # 统一读卡接口
│   │   ├── pn532_adapter.py    # PCR532/PN532（核心，组合 Mixin 瘦身）
│   │   ├── pn532_id_card.py    # PN532IdCardMixin（二代身份证）
│   │   ├── pn532_cpu_card.py   # PN532CpuCardMixin（CPU卡/APDU）
│   │   ├── broadcaster_adapter.py
│   │   ├── libnfc_adapter.py   # 外部 nfc-* 命令行工具
│   │   ├── factory.py          # ReaderAdapterFactory / probe_device
│   │   └── extensions/
│   │       ├── pcsc_adapter.py # PCSC/ACR122U（可选 pyscard）
│   │       └── virtual_adapter.py
│   ├── services/
│   │   ├── serial_worker.py    # QThread 串口/BLE 轮询与独占
│   │   ├── card_worker.py      # 读卡/破解/写卡/固件探测
│   │   ├── key_manager.py      # 字典扫描、解析、合并
│   │   ├── attack_runner.py    # mfoc/mfcuk/hardnested/mfdetect
│   │   └── capability_probe.py # 设备能力与外部工具链探测
│   ├── card_db.py              # SQLite 访问
│   ├── protocol.py             # 兼容门面
│   ├── dump_model.py           # 兼容门面
│   ├── key_manager.py          # 兼容门面
│   ├── serial_worker.py        # 兼容门面
│   ├── card_service.py         # 兼容门面
│   └── attack_runner.py        # 兼容门面
│
├── ui/
│   ├── main_window.py          # 主窗口、连接、Hero UID、日志、M1/CPU 切换
│   ├── sector_table.py         # 扇区矩阵、读写/破解/工具入口
│   ├── sector_widgets.py       # 统计头、雷达、块检查器、值块
│   ├── dictionary_tools.py     # Access Bits、卡号换算、字典、终端、外部攻击
│   ├── cpu_card_widget.py      # CPU 卡概览/流水/文件树/APDU 控制台
│   ├── magic_card_dialog.py    # UID 写号、工厂清卡、UFUID 锁死
│   ├── clone_wizard_dialog.py  # 克隆向导
│   ├── crack_dialogs.py        # 扇区范围、手动密钥
│   ├── card_manage.py          # 卡片档案、流水审计
│   ├── key_select_dialog.py    # 字典勾选
│   ├── device_capabilities_dialog.py # 连接后设备能力提示
│   └── dump_diff.py            # Dump 差分
│
├── keys/                       # 标准/酒店/扩展/共享字典，约 7.4 万条
├── tests/run_tests.py          # 19 个测试类，140 项测试
├── tools/                      # 开发期串口/协议调试脚本，不参与运行时
│   └── m1t/nfc-bin/            # M1T 的 mfoc/mfcuk/hardnested 工具链
```

---

## 4. 架构与依赖方向

```text
ui  →  services  →  adapters  →  transport
                         ↘
                       protocols  ←  models
```

**必须保持的依赖规则：**

- `core/protocols/` 只做字节编解码，**不得**持有串口、BLE、UI 或数据库对象。
- `core/models/` 只做数据与算法，**不得**发起 I/O。
- 所有物理读写必须经过 `transport/` 与 `adapters/`。
- UI 不得直接调用 `serial.Serial`、`bleak` 或 `pyserial`。
- 耗时操作必须放到 `QThread`（`SerialWorker` / `CardOperationWorker` / 各类 Worker）。
- 兼容门面（`core/protocol.py` 等）仅用于旧导入路径，不要在新代码中扩散。

---

## 5. 硬件红线（最高优先级）

### 红线 1：DTR / RTS 必须保持 False

任何打开串口的地方都必须：

```python
ser.dtr = False
ser.rts = False
```

CH340E/CP2102 的 DTR/RTS 可能直连主控复位端，拉高会导致设备假死。

### 红线 2：广播器只能收，不能发

- 广播器（Broadcaster）是 **38400bps 单向 UID 广播**；
- 正常业务链路不得向其发送认证、读写、寄存器配置等下行帧；
- `BroadcasterAdapter` 的认证/读写为空实现，这是刻意设计；
- 例外：`CardOperationWorker._do_probe_firmware()` 的广播器分支已改为纯被动模式，不发送任何下行探测帧；请继续保持该行为。

### 红线 3：射频/串口必须独占

- 长操作前必须 `serial_worker.set_exclusive(True)`，结束后恢复；
- 底层收发必须受 `_tx_lock` / `_hardware_lock` 保护；
- 禁止工作线程与自动轮询线程同时向同一串口写数据；
- 不要试图用多线程并发认证同一张卡，13.56MHz 是半双工环境。

### 红线 4：Block 0 默认禁止写

- Mifare Classic 的 Block 0 保存 UID/BCC/厂商数据；
- 普通卡写 Block 0 可能永久损坏；
- 默认 `allow_block0_write=False`；
- 只有用户显式取消写保护，且卡为 CUID/GEN1A/UFUID 等魔术卡时，才允许走 `write_magic_block0()`。

### 红线 5：CPU 卡 T=CL 状态机

- Mifare 认证后，双界面 CPU 卡可能停留在 CRYPTO1 状态；
- 下发 APDU 前必须重新 `InListPassiveTarget` 激活到 ISO14443-4；
- Type B 身份证读取会改写 12 组 CIU 寄存器，**必须在 `finally` 中恢复 Type A 默认寄存器**；
- `61xx` 必须 GET RESPONSE，`6Cxx` 必须修正 Le；批量 APDU 必须支持中断与移卡退出。

---

## 6. 协议速查

### 6.1 AA BB（广播器）

```text
AA BB LEN CMD DATA... BCC
LEN = len(DATA) + 2          # 含 CMD 与 BCC
BCC = LEN XOR CMD XOR DATA...
```

自动 UID 上报示例：`AA BB 06 01 [4B UID] [BCC]`。

### 6.2 PN532 HSU

```text
00 00 FF LEN LCS TFI CMD DATA... DCS 00
payload = TFI + CMD + DATA
LEN = len(payload) = 2 + len(DATA)
LCS = (-LEN) & 0xFF
DCS = (-sum(payload)) & 0xFF
```

- ACK：`00 00 FF 00 FF 00`
- 主机 TFI：`D4`；PN532 应答 TFI：`D5`
- 常见命令：`0x02` 固件、`0x4A` 寻卡、`0x40` InDataExchange、`0x42` InCommunicateThru、`0x08` 写寄存器

### 6.3 ISO14443-B 身份证

1. 写 Type B CIU 寄存器；
2. `REQB`（`05 00 00` + CRC-B）；
3. 解析 ATQB，取 4 字节 PUPI；
4. `ATTRIB`（`1D + PUPI + 00 08 01 08` + CRC-B）；
5. APDU `00 36 00 00 08` 读取 8 字节 GUID；
6. 恢复 Type A 寄存器。

### 6.4 CPU 卡 APDU

| 用途 | APDU |
|---|---|
| SELECT AID | `00 A4 04 00 Lc AID` |
| SELECT FID | `00 A4 00 00 02 FID` |
| READ BINARY | `00 B0 P1 P2 Le` |
| READ RECORD | `00 B2 Rec P2 00` |
| 余额 | `80 5C 00 02 04` |
| GET CHALLENGE | `00 84 00 00 Le` |
| GET RESPONSE | `00 C0 00 00 Le` |

### 6.5 UID 换算

给定 4 字节 UID：

- 正序/倒序十六进制；
- 8H10D：`int.from_bytes(uid[::-1], "big")`，补零到 10 位；
- WG26：`uid_rev[1]` + `uid_rev[2:4]`；
- WG34：`uid_rev[0:2]` + `uid_rev[2:4]`。

### 6.6 Access Bits

- 默认尾块：`FF 07 80 69`
- 只读：`08 77 8F 69`
- 修改必须经 `AccessBitsDecoder` 校验，不要手写未验证的控制字。

---

## 7. 核心 API 备忘

### `SerialWorker`

```python
SerialWorker(port="COM3", baudrate=115200, device_type="auto")
set_connection(port, baudrate, device_type)
set_ble_connection(address, device_type)
set_exclusive(True/False)
set_auto_poll(bool)
set_poll_interval(ms)
poll_card_once() -> dict | None
authenticate(block, key_type, key, uid) -> bool
read_block(block) -> bytes | None
write_block(block, data) -> bool
write_magic_block0(block, data, magic_type) -> bool
reactivate_target() -> bool
send_apdu_once(apdu) -> dict
read_cpu_card_once() -> dict
scan_cpu_card_tree_once(...) -> dict
```

关键信号：`sig_connected`、`sig_disconnected`、`sig_card_swiped`、`sig_card_removed`、`sig_raw_log`、`sig_device_identified`、`sig_device_capabilities`。

### `CardOperationWorker`

操作常量：

```python
OP_CRACK_KEYS  = "crack_keys"
OP_READ_CARD   = "read_card"
OP_READ_SECTOR = "read_sector"
OP_WRITE_CARD  = "write_card"
OP_PROBE_FIRMWARE = "probe_firmware"
```

密钥恢复模式（`crack_mode`，默认 `fast`）：

```python
CRACK_MODE_FAST = "fast"   # 任一 Key 命中即停止该扇区
CRACK_MODE_BOTH = "both"   # 同时恢复 Key A 与 Key B
CRACK_MODE_A = "a"         # 仅恢复 Key A
CRACK_MODE_B = "b"         # 仅恢复 Key B
```

阶段 3 使用 key-major 跨扇区扫描；认证失败后的 `reactivate_target()` 结果会被 `_last_reactivate_ok` 复用，避免额外发送 `is_card_present` 查询。

信号：`sig_progress`、`sig_log`、`sig_sector_cracked`、`sig_block_read`、`sig_block_failed`、`sig_finished`。

### `MifareDump`

常用方法：

```python
get_uid() / set_uid()
get_block(n) / set_block(n, data)
get_sector_info(sector)
get_sector_first_block(sector)
get_sector_trailer_block(sector)
verify_dump() / repair_dump()
save_mct() / load_mct()
save_eml() / load_eml()
save_json() / load_json()
save_to_file() / load_from_file()
```

注意：**没有** `get_key_a()`、`get_key_b()`、`export_to_mct_file()`。取密钥请用 `get_sector_info()`。

### `CardDatabase`

常用方法：

```python
record_swipe(uid, conv_info, raw_hex)
update_card_info(uid, name, holder, note)
upsert_card(uid, card_name=..., card_holder=..., card_type=..., note=..., conv_info=None)
get_card(uid)
list_all_cards()
list_recent_logs(limit=100)
save_sector_keys(uid, sector, key_a, key_b)
get_card_keys(uid)
clear_swipe_logs()
close()
```

注意：表结构没有 `department/phone/remark`；归档请使用 `upsert_card()` 的 schema 对齐字段。

### `KeyManager`

```python
get_keys_dir()
list_available_files()
parse_key_file(path)
load_combined_keys(selected_files=None, include_defaults_fallback=True)
save_custom_keys(keys)
```

注意：`CUSTOM_KEYS_FILE` 是 `core/services/key_manager.py` 的模块级常量，不是 `KeyManager` 类属性。

### `ReaderAdapterFactory`

```python
ReaderAdapterFactory.create_adapter(device_type, ...)
ReaderAdapterFactory.probe_device(ser, preferred="auto")
ReaderAdapterFactory.register_adapter(name, cls)
```

UI 可选设备：`auto / pn532 / broadcaster / virtual / libnfc`。

### 设备能力探测

```python
adapter.get_capabilities() -> dict
build_device_capabilities(adapter, connection="serial", port="COM3", baudrate=115200) -> dict
```

- `features` 状态：`supported` / `needs_card` / `external` / `experimental` / `unsupported`；
- `tools` 检测 `tools/m1t/nfc-bin` 下的 mfoc/mfcuk/libnfc_hardnested 等文件；
- 不启动外部进程、不发送破坏性指令；
- `SerialWorker` 在 `sig_device_identified` 后发出 `sig_device_capabilities`，主窗口自动弹出能力窗并可用 QSettings 关闭自动提示。

---

## 8. 主要数据流

### 8.1 连接

```text
UI → SerialWorker.set_connection()
   → run() 打开 SerialTransport / BleTransport
   → ReaderAdapterFactory.probe_device()
   → adapter.init_device()
   → sig_connected / sig_device_identified
   → 自动轮询 poll_card()
```

### 8.2 Mifare 读卡

```text
CardOperationWorker(read_card)
→ set_exclusive(True)
→ 寻卡
→ 逐扇区尝试 KeyA/KeyB（DB 密钥优先，其后字典）
→ 认证成功则读取该扇区全部块
→ 写入 MifareDump，更新 READ_OK / READ_FAILED
→ 发信号刷新 UI
```

### 8.3 字典破解

三阶段：

1. 高频优先密钥快速扫描；
2. 已破解密钥跨扇区传播；
3. 剩余扇区全字典深度扫描。

UI 收到 `sig_sector_cracked` 后立即把密钥写入数据库。

### 8.4 写卡

- 逐扇区认证（Dump KeyA → KeyB → 自定义字典）；
- Block 0 默认跳过；
- 魔术卡写 Block 0 必须显式允许；
- 统计成功/失败/跳过块数。

### 8.5 CPU 卡

```text
恢复 Type A 寄存器
→ 重新激活 T=CL
→ SELECT PPSE
→ 选择交通联合 / PBOC 应用
→ READ BINARY 0x15
→ GET BALANCE
→ READ RECORD 0x18 / 0x0B
→ 解析余额/卡号/交易流水
```

### 8.6 BLE

```text
扫描 → BleClassifier 分类 → 选择读卡器
→ BleTransport 连接
→ 自动发现 notify/write 特征
→ 订阅通知
→ 按 MTU 分片发送 HSU 帧
```

---

## 9. UI 结构

主窗口：

- 左侧：连接方式（USB/BLE）、设备类型、串口/波特率、BLE 扫描、连接、读身份证、自动轮询、Hero UID、卡号换算、注册卡片、日志；
- 右侧：Dump 差分、卡片管理、字典工具、扇区矩阵、CPU 卡页；
- 扇区/CPU 页通过右上角自定义 TabBar 切换；
- 扇区表默认显示，CPU 卡页隐藏在主 Tab 中。

修改 UI 时遵循现有暗黑科技风样式：

- 背景 `#0F172A`
- 容器 `#1E293B`
- 高亮 `#38BDF8`

---

## 10. 测试与质量

```bash
python tests/run_tests.py
```

当前基线：

- **140 项测试通过，0 项跳过（本机 COM3 可用）**
- 约 **2.4 秒**
- 覆盖协议、Dump、数据库、GUI 无头渲染、PN532、字典、二代证、BLE、CPU 卡、4K、魔术卡/克隆/攻击器、TCP/Modbus、PCSC 降级、破解模式、能力探测、M1T 工具链与外部工具 GBK/UTF-8 输出解码。

但请注意测试盲区：

- 克隆向导已验证 1K/4K 参数与界面，但未执行真实读写；
- 魔术卡工厂清卡未在真实魔术卡上执行；
- 字典保存已覆盖文件合并/缓存，但未覆盖真实 UI 全流程；
- 固件探测与在位检测仍以 mock 串口为主；
- PCSC/TCP/广播器路径未做真实硬件联调；
- `tools/m1t/nfc-bin` 的 libnfc/mfoc/mfcuk/hardnested 未在 PCR532 真机上完成 COM 口联调。

因此，**测试全绿不代表所有 GUI/硬件路径可用**。修改相关模块后，必须补充真实路径测试。

---

## 11. 编码与修改规范

- 所有源码/文本使用 **UTF-8 without BOM**，禁止 GBK。
- 保持现有中文注释风格；只写必要注释，不写无意义注释。
- 类型标注优先使用 `typing.Dict/List/Optional/Tuple`。
- 禁止在 UI 主线程执行串口、BLE、破解、文件大树解析。
- 禁止在协议类中持有 I/O 句柄。
- 禁止绕过 `SerialWorker` 直接打开串口，除非是 `tools/` 下的调试脚本。
- 修改硬件相关代码前，先确认 `set_exclusive` / `_hardware_lock` / DTR/RTS / Block 0 保护未被破坏。
- 不要随意改动 `keys/` 与 `cards.db`；测试如需数据库请使用临时路径。
- **不要提交代码，除非用户明确要求。**
- 修改后至少运行 `python tests/run_tests.py`；涉及 GUI 的改动需在 offscreen 下验证。

---

## 12. 扩展指南

### 新增读卡器适配器

1. 继承 `core/adapters/base_adapter.py` 的 `BaseReaderAdapter`；
2. 实现 `init_device`、`parse_incoming`、`poll_card`、`authenticate`、`read_block`、`write_block`；
3. 在 `ReaderAdapterFactory` 注册；
4. 若要在 UI 暴露，加入 `DEVICE_CHOICES`；
5. 在 `tests/run_tests.py` 增加单元测试与无头 UI 测试。

### 新增传输通道

1. 实现 `core/transport/base.py` 的 `ITransport`；
2. 在 `TransportFactory.register_transport()` 注册；
3. 保持 `is_open` / `in_waiting` 的兼容包装；
4. 不要破坏串口 DTR/RTS 与锁语义。

### 新增外部攻击引擎

1. 继承 `core/services/attack_runner.py` 的 `BaseAttackEngine`；
2. 实现 `is_available()`、`start_attack()`、`cancel()`；
3. 用 `QProcess` 启动外部工具，解析进度与密钥；
4. 在 UI 的外部攻击页注册；
5. 外部工具必须独占 COM 口，启动前检查 `SerialWorker.is_connected()` / `isRunning()`；
6. 通过 `AttackRunner.set_device_context()` 传入端口/波特率/连接方式，启动时自动注入 `NFC_DEVICE` 与工作目录；
7. 输出路径必须转为绝对路径，避免切换 cwd 后写错位置。

### 新增 UI 工具页

1. 在 `ui/` 新建 `QWidget`；
2. 在 `MainWindow._init_ui()` 加入 `self.tabs`；
3. 使用现有 QSS 色板；
4. 增加 offscreen 渲染测试；
5. 耗时逻辑放入 Worker，不要阻塞主线程。

### 已完成/待上机验证的扩展点

- PCSC/ACR122U：已实现 `PCSCReaderAdapter`，需安装 `pyscard` 并真机验证；
- libnfc：已加入 UI 设备选项，需真机验证；
- TCP/Modbus：已实现 `TcpTransport`/`ModbusTcpTransport`，需实际设备协议联调；
- 虚拟卡：已校验认证状态与 Access Bits；
- 克隆向导：已支持 1K/4K，需真机验证整卡克隆；
- 魔术卡：已修正密钥读取，工厂清卡需真机验证；
- 字典：已增加解析缓存与选键增量统计；
- 设备能力：已实现适配器 `get_capabilities()`、`core/services/capability_probe.py` 与连接后自动提示窗；
- M1T 工具链：已将 mfoc/mfcuk/mfdetect/libnfc_hardnested/nfc-list 等复制到 `tools/m1t/nfc-bin`，外部工具需先断开 COM 口；
- Crypto1/hardnested：标准 PN532 HSU 不暴露 nonce，是否可用于 PCR532 需真机验证，UI 中标记为外部/实验性。

---

## 13. 数据库与文件格式

### `cards.db`

```sql
cards(uid PK, card_name, card_holder, card_type,
      dec_10d, wiegand_26, wiegand_34, note,
      created_at, last_swiped_at, swipe_count)

swipe_logs(id PK, uid, swiped_at, raw_hex)

card_keys(uid, sector, key_a, key_b, updated_at,
          PRIMARY KEY(uid, sector))
```

- WAL 模式；
- `busy_timeout=5000`；
- 线程本地连接；
- 保存密钥时保留已有非空值。

### Dump 格式

| 扩展名 | 说明 |
|---|---|
| `.dump/.mfd/.bin` | 原始二进制 |
| `.mct` | Mifare Classic Tool 文本 |
| `.eml` | 每行一个块 |
| `.json` | 带元数据 |
| `.txt` | 可读文本（扇区横幅 + ASCII） |

### 字典

- `std.keys`：3 条标准高频；
- `hotel-std.keys`：酒店门锁；
- `extended-std.keys`：2477 条；
- `extended-std_share_key_1..8.keys`：约 7.1 万条共享字典；
- 合计约 7.4 万条（含重复）。
- 解析大字典有性能成本，新增 UI 逻辑时请避免重复全量解析。

---

## 14. MCP 服务支持 (Model Context Protocol)

项目内置原生全功能 MCP 对外服务（基于官方 `mcp>=1.3.0,<2.0` / `FastMCP`）：

- **入口**：`mcp_server.py`
- **配置**：`mcp_server_config.json`
- **架构**：全异步实现，底层物理 I/O 受 `asyncio.Lock` 保护并严格遵守 DTR/RTS 禁用与 Block 0 防写红线；
- **全量工具**：对外提供 35 个纯中文描述 MCP Tools，覆盖硬件管理、寻卡、M1 认证读写、魔术卡、密码破解、二代证、CPU 卡/APDU、Dump 导出校验、数据库档案及外部工具链；
- **传输模式**：支持 `stdio` 与 `sse`；
- **配置裁剪**：可通过 `enabled_categories` 动态裁剪激活的工具分类，不在白名单的工具不予注册；
- **Skill 规范**：详细规范见 `.agents/skills/pymifare-mcp/SKILL.md`，文档见 `docs/MCP_SERVICE_GUIDE.md`。

---

## 15. Agent 开工清单

修改前：

- [ ] 确认要改的层（protocol / model / transport / adapter / service / ui）。
- [ ] 搜索是否已有同类实现，避免重复造轮子。
- [ ] 涉及硬件时，确认 DTR/RTS、独占锁、Block 0 保护。
- [ ] 涉及 UI 时，确认耗时逻辑不在主线程。

修改后：

- [ ] `python tests/run_tests.py` 全绿。
- [ ] 新增/修改功能有对应测试，尤其是克隆、魔术卡、字典、自动探测。
- [ ] 无 UTF-8/BOM 问题。
- [ ] 未提交代码，除非用户明确要求。
- [ ] 若改变公共接口，更新本文件与相关门面导出。

---

**最后更新依据**：基于当前工作区源码的全量静态分析；测试基线 140 项通过（本机 COM3 可用）。若代码已变化，请以实际源码为准并更新本文件。
