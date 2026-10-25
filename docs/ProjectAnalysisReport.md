# PyMifareTool 全量代码分析报告

> 分析范围：项目源码、测试、配置与数据文件；已忽略所有 `.` 开头目录及 `.md` 文档，结论均来自代码本身。

---

## 1. 项目定位与总体结论

PyMifareTool 是一个基于 **Python 3.12+ / PyQt6 / pyserial / bleak / SQLite3** 的 Mifare Classic 与智能卡综合上位机，覆盖：

- Mifare Classic 1K/4K 的 UID 读取、扇区认证、全卡读取、字典破解、写卡、Dump 编辑与差分；
- 二代身份证 ISO14443-B GUID 读取；
- CPU 智能卡（PBOC/交通联合/ETC 等）APDU 交互、余额与交易流水、文件树扫描；
- 魔术卡 UID 写号、工厂化清卡、UFUID 锁死；
- 一键克隆向导、卡片档案库、刷卡流水审计、MCT 字典管理；
- 三种硬件形态：PCR532/PN532 双向读写器、38400 单向广播发卡器、Minicopy/WCH BLE 无线读写器。

整体架构清晰，协议层基本保持无状态，传输层与适配器层解耦较好，硬件安全约束（DTR/RTS、独占锁、Block 0 保护）在主要链路上落实。但 UI 与业务层存在若干**未被测试覆盖的 P0 级断裂**，主要集中在克隆向导、魔术卡工厂清卡和字典工具的部分按钮。

---

## 2. 技术栈与运行入口

**依赖**（`requirements.txt`）：

| 依赖 | 版本 |
|---|---|
| pyserial | `>=3.5,<4.0` |
| PyQt6 | `>=6.6.0,<7.0` |
| bleak | `>=0.22.0,<2.0` |

**入口** `main.py`：

1. 将项目根目录插入 `sys.path`；
2. 启用高 DPI 缩放；
3. 创建 `QApplication`，设置名称与版本；
4. 实例化 `ui.main_window.MainWindow` 并进入事件循环。

---

## 3. 目录与分层架构

```text
main.py
└── ui/                 表现层：主窗口、扇区矩阵、工具页、各类对话框
    └── services/       业务服务层：串口线程、卡操作线程、字典、外部攻击
        └── adapters/   硬件适配层：PN532 / 广播器 / libnfc / 虚拟卡 / PCSC
            └── transport/ 物理传输层：串口、BLE、传输工厂
                └── protocols/ 无状态协议层：AABB、PN532 HSU、ISO14443-B、ISO7816
                    └── models/ 领域模型：Dump、Access Bits、UID 换算
```

| 层 | 目录 | 职责 |
|---|---|---|
| 协议层 | `core/protocols/` | 组帧、解帧、校验、APDU/TLV 编解码，无 I/O |
| 模型层 | `core/models/` | Mifare Dump、三态块状态、权限位、卡号换算 |
| 传输层 | `core/transport/` | 串口/BLE 打开关闭、读写、缓冲区、DTR/RTS |
| 适配层 | `core/adapters/` | 将具体硬件协议映射为统一读卡接口 |
| 服务层 | `core/services/` | QThread 异步串口、卡操作、字典加载、外部工具调用 |
| 表现层 | `ui/` | PyQt6 界面、交互编排、可视化 |
| 兼容门面 | `core/protocol.py`、`core/dump_model.py` 等 | 旧导入路径 re-export |

---

## 4. 核心协议层

### 4.1 AABB 协议（简易广播发卡器）

`core/protocols/aabb.py`

帧格式：

```text
AA BB LEN CMD DATA... BCC
LEN = len(DATA) + 2
BCC = LEN XOR CMD XOR DATA...
```

- 命令覆盖：自动 UID、Request A、防冲突、选卡、认证 A/B、读块、写块、加/减/恢复/传输、Halt、波特率、LED、蜂鸣器、版本。
- `parse_frame()` 具备帧头搜索、长度校验、BCC 校验和失配重同步能力。
- 自动 UID 帧支持 4/7/10 字节 UID。
- 该协议只用于广播器的**上行接收**；广播器固件不响应下行指令。

### 4.2 PN532 HSU 协议

`core/protocols/pn532.py`

```text
00 00 FF LEN LCS TFI DATA... DCS 00
```

- `LEN = len(TFI + DATA)`，`LCS = -LEN & 0xFF`；
- `DCS = -(TFI + ΣDATA) & 0xFF`；
- ACK 固定为 `00 00 FF 00 FF 00`；
- 支持固件版本、寄存器读写、SAM 配置、寻卡、InDataExchange、InCommunicateThru、释放目标等；
- 解帧支持 ACK 识别、LCS/DCS 校验、帧头重同步。

### 4.3 ISO14443-B / 二代身份证

`core/protocols/iso14443b.py`

- 实现 CRC-B（多项式 `0x8408`、初值 `0xFFFF`、结果取反、小端输出）；
- 提供 Type B 身份证专用 CIU 寄存器组；
- 流程：
  1. 写 12 组 Type B 寄存器；
  2. `REQB` 广播寻卡；
  3. 解析 ATQB 中的 4 字节 PUPI；
  4. `ATTRIB` 激活；
  5. 通过 APDU `00 36 00 00 08` 读取 8 字节 GUID；
  6. 最后恢复 Type A 寄存器。

### 4.4 ISO7816 / APDU

`core/protocols/iso7816.py`（约 823 行）

- 内置常见 AID：PPSE、交通联合、PBOC 借记/贷记/现金、ETC 等；
- 内置约 40 个中国银行 BIN 映射；
- 提供 APDU 构造：
  - SELECT：`00 A4 04 00 ...` / `00 A4 00 00 02 ...`
  - READ BINARY：`00 B0 ...`
  - READ RECORD：`00 B2 ...`
  - 余额：`80 5C 00 02 04`
  - GET CHALLENGE、GET RESPONSE
- 提供：
  - `parse_balance()`：4 字节有符号大端，分转元；
  - `parse_ppse_response()`：扫描 `4F` 标签选择应用；
  - `parse_t_union_card_info()`：卡号、发卡方、有效期；
  - `parse_pboc_card_info()`：PAN/Track2/有效期；
  - `parse_transaction_record()`：PBOC 与交通联合两种布局；
  - `parse_tlv()`：递归 BER-TLV；
  - `dissect_apdu_response()`：面向调试控制台的语义解析；
  - `get_sw_description()`：状态字解释。

协议层整体质量较好，纯函数化程度高，未持有串口句柄。

---

## 5. 领域模型层

### 5.1 `MifareDump`（`core/models/dump.py`）

- 支持 1K（16 扇区/64 块/1024 B）与 4K（40 扇区/256 块/4096 B）；
- 每个块维护三态：`UNREAD / READ_OK / READ_FAILED`；
- 提供扇区首块、尾块、块数量、块所属扇区等 4K 兼容计算；
- 出厂化时写入标准尾块：`FF FF FF FF FF FF FF 07 80 69 FF FF FF FF FF FF`；
- 支持 UID 写入及 BCC/SAK/ATQA 生成；
- 支持 `verify_dump()`、`repair_dump()`、密钥字典导出；
- 支持 `.dump/.mfd/.bin/.mct/.eml/.json/.txt` 读写；
- MCT 加载能识别死扇区/未发现密钥并标记失败块。

### 5.2 Access Bits（`core/models/access_bits.py`）

- 提供 NXP AN1305 数据块与尾块权限表；
- `AccessBitsDecoder.decode()` 校验 C1/C2/C3 反码对；
- `AccessBitsEncoder.encode()` 根据 4 个块的权限配置生成 4 字节控制字；
- UI 的权限位工具直接复用该模型。

### 5.3 卡号换算（`core/models/card_converter.py`）

- 随机 UID 生成；
- Block 0 构造（4 字节/7 字节 UID）；
- 正序/倒序十六进制、8H10D、韦根 26/34、UID 类型识别；
- 韦根公式与常见门禁标准一致。

---

## 6. 传输层

### 6.1 串口传输 `core/transport/serial_transport.py`

- 打开串口后强制：

```python
ser.dtr = False
ser.rts = False
```

- 8N1，默认 115200；
- 所有写操作受 `threading.Lock` 保护；
- 提供 `is_open`、`in_waiting` 的可调用/可布尔兼容包装，便于适配 pyserial 与 BLE；
- 读取时临时修改超时，读期间持锁。

### 6.2 BLE 传输 `core/transport/ble_transport.py`

- 基于 `bleak`，后台 asyncio 线程；
- 默认 GATT：
  - WCH CH59x：服务 `0000ff00...`，通知 `ff01`，写 `ff02`；
  - Minicopy：服务 `ae00`，通知 `ae02`，写 `ae01`；
- 自动发现 notify/write 特征；
- 按 MTU 分片写入，默认 20 字节/片；
- 读取使用条件变量等待；
- `scan_devices()` 支持扫描、分类、去重、按优先级和 RSSI 排序。

### 6.3 BLE 分类器 `core/transport/ble_classifier.py`

- 识别厂商、读卡器、音频、手柄、键鼠、穿戴、手机、PC 等类别；
- 读卡器优先级最高；
- 输出图标、标签、信号质量、是否读卡器。

### 6.4 传输工厂

`TransportFactory` 支持 `serial / ble / tcp / modbus` 常量，但仅串口与 BLE 有实现。

---

## 7. 适配器层

### 7.1 统一接口 `core/adapters/base_adapter.py`

定义：

- `init_device`
- `parse_incoming`
- `poll_card`
- `authenticate`
- `read_block`
- `write_block`
- `write_magic_block0`
- `lock_ufuid_card`

### 7.2 广播器适配器

`BroadcasterAdapter`：

- 单向，38400；
- 只解析 AABB 上行帧；
- 认证/读写全部为空实现，符合硬件特性。

### 7.3 PN532 适配器（核心）

`core/adapters/pn532_adapter.py`（约 745 行）

能力：

- HSU 唤醒、固件读取、SAM 配置；
- Type A 寻卡、认证、读块、写块；
- 魔术卡 Block 0 写入：
  - CUID/GEN2/FUID 直接写；
  - GEN1A 先发后门指令；
- UID 锁定；
- 二代身份证 Type B GUID 读取；
- CPU 卡 APDU：
  - 自动处理 `61xx` GET RESPONSE；
  - 自动处理 `6Cxx` 长度修正；
- CPU 卡公共信息读取；
- CPU 卡文件树扫描。

### 7.4 其他适配器

| 适配器 | 状态 |
|---|---|
| `LibnfcCliAdapter` | 已实现，依赖外部 `nfc-bin` 工具链，但未进入 UI 设备下拉 |
| `PCSCReaderAdapter` | 仅有骨架，所有操作返回空/False |
| `VirtualDumpReaderAdapter` | 内存虚拟卡，可用于无硬件测试；但不校验权限位与认证状态 |

### 7.5 适配器工厂

`ReaderAdapterFactory`：

- 支持 `auto / pn532 / broadcaster / virtual / pcsc / libnfc`；
- UI 仅暴露 `auto / pn532 / broadcaster / virtual`；
- 自动探测逻辑存在缺陷，见后文 P1。

---

## 8. 服务层

### 8.1 `SerialWorker`（`core/services/serial_worker.py`）

- QThread 管理串口/BLE 连接；
- 自动轮询贴卡，默认 300ms；
- 通过 `set_exclusive(True)` 暂停轮询，保证射频半双工独占；
- 统一透传认证、读块、写块、魔术写、UID 锁定、APDU、CPU 卡读取、文件树扫描；
- 所有底层收发受 `_tx_lock` 保护；
- 发出连接、断开、贴卡、移卡、原始日志、状态、响应等信号。

### 8.2 `CardOperationWorker`（`core/services/card_worker.py`）

支持操作：

- `crack_keys`
- `read_card`
- `read_sector`
- `write_card`
- `probe_firmware`

关键设计：

- 进入操作前 `set_exclusive(True)`，结束后恢复；
- 使用 `_hardware_lock` 串行化底层认证/读写；
- 认证失败后调用 `reactivate_target` 或重新寻卡，避免卡片停留在 HALT 状态；
- 读卡失败块标记 `READ_FAILED`；
- 写卡默认跳过 Block 0；
- 破解采用三阶段：
  1. 高频优先密钥快速尝试；
  2. 已破解扇区密钥跨扇区传播；
  3. 剩余字典深度扫描。

### 8.3 `KeyManager`

- 从 `keys/` 目录加载 `.keys/.dic/.txt`；
- 支持默认字典、酒店字典、扩展字典；
- 去重、合并、排序；
- 当前项目实际包含约 **7.4 万条**密钥（含 8 个共享大字典）。

### 8.4 `AttackRunner`

- 封装 `mfoc / mfcuk / hardnested / mfdetect`；
- 使用 `QProcess` 调用外部工具；
- 解析进度、密钥命中、完成状态。

---

## 9. 数据持久化与配置

### 9.1 SQLite 数据库 `cards.db`

表结构：

```sql
cards(
  uid TEXT PRIMARY KEY,
  card_name TEXT,
  card_holder TEXT,
  card_type TEXT,
  dec_10d TEXT,
  wiegand_26 TEXT,
  wiegand_34 TEXT,
  note TEXT,
  created_at TIMESTAMP,
  last_swiped_at TIMESTAMP,
  swipe_count INTEGER
)

swipe_logs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT,
  swiped_at TIMESTAMP,
  raw_hex TEXT
)

card_keys(
  uid TEXT,
  sector INTEGER,
  key_a TEXT,
  key_b TEXT,
  updated_at TIMESTAMP,
  PRIMARY KEY(uid, sector)
)
```

实现特点：

- WAL 模式；
- `busy_timeout=5000`；
- 线程本地连接；
- 密钥保存时保留已有非空值；
- 当前数据库有 11 张卡、548 条刷卡流水、56 条扇区密钥。

### 9.2 字典文件

| 文件 | 有效密钥数 |
|---|---:|
| `std.keys` | 3 |
| `hotel-std.keys` | 约 28 |
| `extended-std.keys` | 2477 |
| `extended-std_share_key_1..8.keys` | 71,722 |
| 合计 | 约 74,230 |

共享字典没有专门元数据，会被当作普通自定义字典列出，解析开销较大。

### 9.3 Dump 文件格式

支持：

- `.dump / .mfd / .bin`：原始二进制；
- `.mct`：Mifare Classic Tool 文本；
- `.eml`：每行一个块；
- `.json`：带元数据的结构化格式；
- `.txt`：带扇区横幅和 ASCII 的可读文本。

---

## 10. 关键业务流程

### 10.1 连接与设备识别

```text
UI 选择串口/BLE
→ SerialWorker.set_connection / set_ble_connection
→ run() 创建 SerialTransport / BleTransport
→ ReaderAdapterFactory.probe_device()
→ adapter.init_device()
→ 发出 sig_connected / sig_device_identified
→ 进入自动轮询
```

### 10.2 Mifare 读卡

```text
CardOperationWorker(read_card)
→ set_exclusive(True)
→ 寻卡
→ 逐扇区尝试字典 KeyA/KeyB
→ 认证成功则读取该扇区所有块
→ 写入 MifareDump，更新块状态
→ 发出块读取/扇区破解/完成信号
→ UI 刷新矩阵、统计、雷达图
```

### 10.3 字典破解

三阶段：

1. 高频密钥优先扫描所有目标扇区；
2. 已破解密钥跨扇区复用；
3. 对未破解扇区进行完整字典深度扫描。

每破解一个扇区即发出 `sig_sector_cracked`，UI 立即持久化密钥。

### 10.4 写卡

```text
写前确认
→ 逐扇区用 Dump 中 KeyA/KeyB 或自定义字典认证
→ Block 0 默认跳过
→ 魔术卡可显式允许写 Block 0
→ 写块并统计成功/失败/跳过
```

### 10.5 CPU 卡

```text
恢复 Type A 寄存器
→ InListPassiveTarget 激活
→ SELECT PPSE
→ 选择交通联合/PBOC 应用
→ 读取 0015 公共信息
→ 查询余额 80 5C
→ 读取 0x18 / 0x0B 交易记录
→ 解析并展示
```

APDU 控制台支持手动发送、状态字解释、TLV/余额/记录语义解析。

### 10.6 BLE

```text
扫描设备 → BleClassifier 分类 → 选择读卡器
→ BleTransport 连接
→ 自动发现 GATT 特征
→ 订阅通知
→ 按 MTU 分片发送 HSU 帧
```

### 10.7 克隆与魔术卡

- 克隆向导：读源卡 → 写目标卡 → 生成报告；
- 魔术卡工具：UID 写号、工厂化清卡、UFUID 锁死。

> 这两条链路目前存在多个 P0 缺陷，见第 13 节。

---

## 11. UI 功能地图

| 组件 | 功能 |
|---|---|
| `MainWindow` | 连接管理、串口/BLE 切换、贴卡 Hero UID、卡号换算、注册卡片、日志、M1/CPU 页切换 |
| `SectorTableWidget` | 16/40 扇区矩阵、块编辑、读卡/写卡/破解/单扇区解密、Dump 导入导出、校验修复、魔术工具、克隆入口 |
| `SectorWidgets` | 统计头、扇区雷达、块检查器、值块解析/构造 |
| `DictionaryToolsWidget` | Access Bits 编解码、卡号换算、字典管理、AA BB 调试终端、外部攻击 |
| `CpuCardWidget` | CPU 卡概览、余额、交易流水、文件树扫描、APDU 控制台 |
| `MagicCardDialog` | UID 写号、工厂化清卡、UFUID 锁死 |
| `CloneWizardDialog` | 三步克隆向导 |
| `CardManageWidget` | 卡片档案、刷卡流水、CSV 导出、双模清空 |
| `DumpDiffWidget` | 双 Dump 字节级差分 |
| `KeySelectDialog` | 字典勾选、合并统计 |
| `CrackDialogs` | 扇区范围选择、手动密钥输入 |

主窗口默认显示扇区表，CPU 卡页通过右上角自定义 TabBar 切换。

---

## 12. 测试与质量

执行：

```bash
python tests/run_tests.py
```

结果：

- **96 项测试全部通过**
- 0 failures / 0 errors
- 耗时约 **3.0 秒**
- 16 个测试类，覆盖协议、Dump、数据库、GUI 无头渲染、PN532、字典并发、二代证、架构解耦、BLE、CPU 卡、4K、魔术卡/克隆/攻击器。

但测试存在明显盲区：

- 克隆向导只验证界面渲染和步骤切换，不执行真实读写；
- 魔术卡工厂清卡未执行；
- 字典导入/保存未执行；
- 固件探测测试替换了 `get_firmware_version`；
- 移卡中止测试替换了 `is_card_present`。

因此下述 P0/P1 缺陷可以全部通过测试。

---

## 13. 缺陷与风险清单

### P0：功能直接不可用

1. **克隆向导入口崩溃**  
   `ui/sector_table.py:855` 使用 `self.card_db`，但该类只定义了 `self.db`。点击克隆向导即 `AttributeError`。

2. **克隆向导操作类型错误**  
   `ui/clone_wizard_dialog.py:349` 使用 `op_type="read"`，`:410` 使用 `op_type="write"`；而 `CardOperationWorker` 的常量是 `"read_card"` / `"write_card"`。即使入口修复，源卡读取和目标卡写入都会落入“未知操作类型”。

3. **克隆向导保存数据库崩溃**  
   `ui/clone_wizard_dialog.py:476` 调用不存在的 `CardDatabase.upsert_card(...)`，且传入数据库不存在的 `department/phone/remark` 字段。

4. **克隆向导保存 MCT 崩溃**  
   `ui/clone_wizard_dialog.py:464` 调用不存在的 `MifareDump.export_to_mct_file()`，实际方法为 `save_mct()`。

5. **魔术卡工厂清卡崩溃**  
   `ui/magic_card_dialog.py:568` 调用不存在的 `MifareDump.get_key_a()`；模型只提供 `get_sector_info()`。

### P1：主要功能缺陷/硬件误判

6. **自动设备探测永远偏向 PN532**  
   `core/adapters/factory.py:94-98` 先调用 `PN532Adapter.init_device()`，该函数即使没有有效固件响应也会返回 `True` 并设置 `"PN532 兼容设备 (快速模式)"`；随后基类 `get_firmware_version()` 返回该字符串，包含 `"PN532"`，导致自动探测几乎总是选中 PN532，广播器自动识别分支不可达。

7. **广播器首帧可能被吞**  
   `core/adapters/factory.py:101-104` 通过 `read()` 窥探 `AA BB`，会消费串口缓冲区数据，可能丢失广播器第一帧。

8. **PN532 未实现 `get_firmware_version()` 与 `is_card_present()`**  
   - 固件探测步骤不会真正重新查询硬件；
   - `SerialWorker.is_card_present()` 在适配器无该方法时恒返回 `True`，导致破解过程中的“连续 3 次无卡中止”在真实 PN532 上永远不会触发。

9. **读卡/单扇区解密中止后不发送完成信号**  
   `core/services/card_worker.py:393-394`、`:457-458` 直接 `return`，UI 进度面板可能停留在运行状态。

10. **字典工具外部导入缺少 `import os`**  
    `ui/dictionary_tools.py:451-453` 使用 `os.path`，模块顶层未导入 `os`，触发 `NameError`。

11. **字典工具保存已恢复密钥调用不存在的方法**  
    `ui/dictionary_tools.py:877` 调用 `KeyManager.save_custom_keys()`，`:879` 调用 `self._load_custom_keys()`，两者均不存在。

12. **4K 扇区范围对话框计算错误**  
    `ui/crack_dialogs.py:109,126` 固定使用 `sector * 4` 和 4 块范围；4K 的 32–39 扇区实际首块为 `128 + (sector-32)*16`，会显示错误的块范围。

13. **广播器固件探测违反单向约束**  
    正常读写链路对广播器不会下发指令，但 `CardOperationWorker._do_probe_firmware` 的广播器分支会主动发送 Request A、防冲突、版本、LED、蜂鸣器等 AABB 下行帧。虽然只在用户点击“固件探测”时触发，仍与“广播器物理上不响应下行”的硬件事实冲突。

### P2：性能、兼容性与实现不完整

14. **PN532 每次寻卡失败都尝试二代证 Type B 读取**  
    会反复写/恢复 12 组 CIU 寄存器，增加轮询延迟与发热，影响普通 Mifare 轮询体验。

15. **APDU `6Cxx` 修正假设最后一个字节是 Le**  
    `PN532Adapter.send_apdu()` 对无 Le 的 case-1 APDU 可能错误替换/追加字节；`61xx` 也只处理一次 GET RESPONSE，未做链式处理。

16. **字典选择对话框反复全量解析**  
    `KeySelectDialog._update_summary()` 在每次勾选变化时重新合并最多约 7.4 万条密钥；`KeyManager.list_available_files()` 每次都会解析全部共享字典，易造成 UI 卡顿。

17. **克隆向导固定 1K**  
    `is_4k=False`、16 个扇区硬编码，无法克隆 4K 卡。

18. **固件探测结果存在过度声明**  
    `_do_probe_firmware` 的总结文案声称支持 ISO14443-A/B/后门等能力，但并未逐项验证。

19. **PCSC 适配器为空壳**  
    `core/adapters/extensions/pcsc_adapter.py` 所有操作返回 `None/False`，但工厂已暴露 `pcsc`。

20. **libnfc 适配器未进入 UI**  
    已实现 `nfc-mfclassic` 等调用，但 `DEVICE_CHOICES` 未包含，用户无法从界面选择。

21. **传输工厂存在未实现类型**  
    `tcp`、`modbus` 仅有常量，没有对应传输类。

22. **虚拟卡不校验权限位**  
    `VirtualDumpReaderAdapter` 认证后读写不检查 Access Bits 与认证状态，仅适合仿真。

### P3：细节问题

23. `ui/card_manage.py:198-199` 连续弹出两次相同的成功提示。
24. `PN532Adapter.lock_ufuid_card()` 只要收到任意响应就返回 `True`，判定过宽。
25. `MifareDump.reset_factory_default()` 的 Key B 使用 `FF...FF`，符合常见出厂值，但需注意与部分卡种差异。
26. 主窗口/扇区表承担了较多业务编排逻辑，UI 与业务边界仍有进一步下沉空间。

---

## 14. 硬件红线合规性

| 红线 | 实现情况 |
|---|---|
| DTR/RTS 必须为 False | `SerialTransport.open()` 与广播器初始化均强制设置，合规 |
| 串口/射频独占 | `SerialWorker._tx_lock`、`set_exclusive`、`CardOperationWorker._hardware_lock` 均已落实 |
| 广播器不得下发指令 | 正常读写链路合规；固件探测分支例外，需修正 |
| Block 0 写保护 | UI 默认勾选保护，Worker 默认 `allow_block0_write=False`，合规 |
| CPU 卡 T=CL 状态恢复 | CPU 卡读取/扫描前重新激活，Type B 寄存器在 `finally` 中恢复，合规 |
| APDU 61xx/6Cxx | 已实现自动处理，但 6Cxx 对无 Le APDU 不够稳健 |

---

## 15. 技术债与扩展点

### 技术债

- 大量 UI 直接调用模型/数据库/Worker，缺少独立的应用服务层；
- 克隆向导、魔术卡工具与数据库模型之间存在“设计先行、实现未对齐”的接口漂移；
- 字典加载没有缓存，7 万级密钥反复解析；
- PN532 适配器职责过重（协议、寻卡、身份证、APDU、文件树扫描集中在一个类）；
- 测试偏向“可渲染/可调用”，缺少真实业务路径的端到端断言；
- 旧门面模块与新旧导入路径并存，增加维护成本。

### 扩展点

| 扩展 | 入口 |
|---|---|
| PCSC/ACR122U | 补全 `PCSCReaderAdapter` 并注册工厂 |
| libnfc 命令行工具链 | 将 `LibnfcCliAdapter` 加入 UI 设备列表 |
| TCP/Modbus 传输 | 实现 `ITransport` 并注册 `TransportFactory` |
| 虚拟卡仿真 | 完善 `VirtualDumpReaderAdapter` 的权限位与认证状态 |
| 外部破解引擎 | 继承 `BaseAttackEngine`，接入 Proxmark3/crapto1 等 |
| 新 UI 工具页 | 在 `ui/` 新建 QWidget，挂入 `MainWindow.tabs` |

---

## 16. 建议修复优先级

1. **立即修复 P0**：克隆向导入口、操作类型、数据库保存、MCT 保存、魔术卡 `get_key_a`。
2. **修复 P1 硬件识别**：为 PN532 实现真实 `get_firmware_version()` / `is_card_present()`；重写自动探测，避免 `init_device()` 的宽松成功判定；不要消费广播器首帧。
3. **修复 P1 工具链**：字典导入 `import os`、保存密钥接口、4K 扇区范围。
4. **补测试**：为克隆向导真实读写、魔术卡工厂清卡、字典导入/保存、自动设备探测增加端到端测试。
5. **性能优化**：缓存字典解析结果，延迟加载共享大字典，字典勾选时只做增量统计。
6. **完善 4K 与 CPU 卡路径**：克隆向导支持 4K；APDU 6Cxx 处理区分有无 Le。

总体而言，项目的协议层、模型层和底层传输层设计扎实，硬件安全约束执行到位；主要问题集中在**新功能 UI 与既有服务接口未完全对齐**，以及**自动设备探测和测试覆盖**。修复上述 P0/P1 后，项目可达到较完整的可用状态。
