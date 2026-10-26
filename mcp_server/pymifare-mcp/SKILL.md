---
name: pymifare-mcp
description: "PyMifareTool 智能卡 (RFID/NFC/二代证/CPU卡) 全功能 MCP 服务调用与控制指南。当需要通过 MCP 操控读卡器硬件、执行 M1 认证与读写、二代身份证物理读取、CPU 卡 APDU 交互、密钥字典暴力破解、Dump 镜像管理及 SQLite 发卡审计时激活此技能。"
---

# PyMifareTool MCP 智能卡服务标准规范指南

本规范旨在指导 AI Agent 或大语言模型如何通过 Model Context Protocol (MCP) 标准协议无缝接入并全权调度 `PyMifareTool` 智能卡上位机核心引擎。

---

## 1. 架构定位与工作模式

`PyMifareTool MCP Server` 是基于官方标准 Python MCP SDK (`FastMCP`) 构建的异步智能卡服务，运行在读写器底层适配层与外部模型之间。

### 1.1 服务通信拓扑

```text
[外部客户端 / LLM Agent]
       │
       │  MCP Protocol (JSON-RPC 2.0 via stdio 或 SSE)
       ▼
[PyMifareTool MCP Server (mcp_server.py)]
  ├── McpServerConfig (动态功能白名单与安全阈值)
  ├── McpContext (异步互斥独占锁 + 状态缓存)
  └── 9 大功能工具集 (35 个纯中文描述 MCP Tools)
       │
       │  asyncio.to_thread / 线程安全调度
       ▼
[ReaderAdapter / Transport / SQLite DB / KeyManager]
       │
       ▼
[物理硬件: PN532 / PCR532 / 二代证 / BLE / CPU卡]
```

### 1.2 启动与部署方式

1. **标准标准输入输出 (stdio) 模式（默认，用于嵌入式 Agent）**：
   ```bash
   python mcp_server.py
   ```
2. **HTTP Server-Sent Events (SSE) 模式（用于远程网络调用）**：
   ```bash
   python mcp_server.py --transport sse --host 0.0.0.0 --port 8000
   ```
3. **查看当前已注册的工具清单**：
   ```bash
   python mcp_server.py --list-tools
   ```

---

## 2. 配置文件规范 (`mcp_server_config.json`)

服务通过 `mcp_server_config.json` 进行动态功能裁剪与访问控制：

```json
{
  "server_name": "PyMifareTool-MCP",
  "transport_mode": "stdio",
  "host": "127.0.0.1",
  "port": 8000,
  "default_port": "COM3",
  "default_baudrate": 115200,
  "default_device_type": "auto",
  "enabled_categories": [
    "hardware",
    "card",
    "m1",
    "cracking",
    "id_card",
    "cpu_card",
    "dump",
    "database",
    "external_tools"
  ],
  "disabled_tools": [],
  "allow_block0_write": false
}
```

### 动态白名单分类表 (`enabled_categories`)

| 分类标识 | 中文名称 | 说明 |
|---|---|---|
| `hardware` | 硬件链路 | 串口枚举、连接、断开、状态与能力探测 |
| `card` | 基础寻卡 | 射频寻卡、在位检测与 UID 多行业格式换算 |
| `m1` | Mifare Classic 读写 | 扇区认证、块读写、整扇区解析、魔术卡改写、UFUID锁卡 |
| `cracking` | 密钥破解 | 本地字典加载、解析、跨扇区传播破解、已知密钥查询 |
| `id_card` | 二代身份证 | ISO14443-B 非标寄存器握手、GUID/PUPI 读取与 Type A 自动复位 |
| `cpu_card` | CPU 卡与 APDU | 原生 APDU 收发、61xx/6Cxx 自动协商、交通联合/金融卡信息读取 |
| `dump` | Dump 镜像管理 | 各种格式 Dump 导入导出、结构合法性验证、BCC纠错与差分对比 |
| `database` | 数据库档案 | 本地 SQLite 卡片建档、持卡人查询、刷卡历史流水审计 |
| `external_tools` | 外部工具链 | mfoc, mfcuk, libnfc_hardnested 等外部程序就绪检测 |

---

## 3. 全量 MCP 工具集清单 (35 个工具)

### 3.1 全局服务与硬件控制

1. **`get_mcp_service_status()`**
   - **说明**：获取 MCP 服务的当前状态、网络模式、已激活的功能分类及硬件连接概况。
2. **`list_serial_ports()`**
   - **说明**：扫描操作系统中所有可用物理串口与 USB 虚拟串口（含端口号、芯片厂商描述与硬件 ID）。
3. **`connect_reader(port: str = None, baudrate: int = None, device_type: str = None)`**
   - **说明**：连接指定端口读写器硬件，自动执行芯片唤醒、SAM 配置与自适应探测。
4. **`disconnect_reader()`**
   - **说明**：安全断开读写器硬件，释放串口占用与锁资源。
5. **`get_device_status()`**
   - **说明**：获取当前链路的波特率、设备名称、固件版本、双向通信能力与当前缓存卡片。
6. **`probe_capabilities()`**
   - **说明**：深度探测读写器硬件特性（M1/二代证/CPU卡/魔术卡）与本地外部攻击工具链状态。

### 3.2 寻卡与卡号换算

7. **`poll_card()`**
   - **说明**：执行一次 13.56MHz 射频寻卡，返回 UID、ATQA、SAK、ATS、卡片类型推断，以及 8H10D、WG26、WG34 等换算结果，并置入会话上下文。
8. **`is_card_present()`**
   - **说明**：原位存活探测，无侵入式快速验证卡片是否仍在感应区天线上。
9. **`convert_uid_formats(uid_hex: str)`**
   - **说明**：纯算法计算：对给定的 16 进制 UID 进行正序、倒序、8H10D（门禁十位卡号）、WG26、WG34 编码换算。

### 3.3 Mifare Classic 核心读写与魔术卡

10. **`authenticate_sector(sector: int, key_type: str = "A", key_hex: str = "FFFFFFFFFFFF", uid_hex: str = None)`**
    - **说明**：以指定密钥认证扇区（Key A 或 Key B），保持底层射频 CRYPTO1 会话。
11. **`read_block(block: int, authenticate_first: bool = False, key_type: str = "A", key_hex: str = None)`**
    - **说明**：读取指定数据块（16 字节），可开启前置认证。
12. **`write_block(block: int, data_hex: str, allow_block0_write: bool = False)`**
    - **说明**：向指定块写入 16 字节数据。**安全红线：Block 0 默认拦截保护，防止报废普通卡！**
13. **`read_sector(sector: int, key_type: str = "A", key_hex: str = "FFFFFFFFFFFF")`**
    - **说明**：完整读取扇区内所有数据块，并解析尾块控制字 (Access Bits) 权限。
14. **`write_magic_block0(block0_hex: str, magic_type: str = "CUID")`**
    - **说明**：魔术卡专写 Block 0，支持 CUID（普通指令后门）、GEN1A（特殊指令解锁后门）、UFUID（可固化后门）。
15. **`lock_ufuid_card(confirm: bool = False)`**
    - **说明**：**单向高危硬件操作**：向 UFUID 卡发送固化锁死指令，永久关闭后门变为只读普通卡。需显式传入 `confirm=True`。

### 3.4 密钥字典与密码恢复

16. **`list_key_dictionaries()`**
    - **说明**：列出本地 `keys/` 目录下全部字典文件（std.keys, hotel-std.keys, extended-std.keys 等）及条目概览。
17. **`parse_key_dictionary_file(filename: str)`**
    - **说明**：解析并提取指定字典中的 12 字符十六进制密钥列表。
18. **`save_custom_keys(keys: List[str])`**
    - **说明**：向用户字典 `custom.keys` 中追加保存新密钥并自动去重。
19. **`get_card_known_keys(uid: str = None)`**
    - **说明**：从 SQLite 数据库中查询目标卡片历史上已恢复或保存的所有扇区已知密钥。
20. **`crack_card_keys(start_sector: int = 0, end_sector: int = 15, dictionary_files: List[str] = None, crack_mode: str = "fast")`**
    - **说明**：在位卡片多阶段高阶字典密钥恢复。支持 `fast`、`both`、`a`、`b` 四种破解策略，恢复成功的密钥自动入库。

### 3.5 二代居民身份证 (ISO14443-B)

21. **`read_id_card()`**
    - **说明**：执行 Type B 射频寄存器配置 -> REQB/ATQB 握手 -> 提取 4 字节 PUPI -> ATTRIB 激活 -> 读取 8 字节物理 GUID。**操作完成后严格复位 Type A 寄存器**。

### 3.6 CPU 智能卡与 APDU

22. **`send_apdu(apdu_hex: str, auto_get_response: bool = True)`**
    - **说明**：向 CPU 智能卡下发原生 7816 APDU，遇 `61xx` 自动 `GET RESPONSE` 取全长数据，遇 `6Cxx` 自动重发修正 Le。
23. **`read_cpu_card_public_info()`**
    - **说明**：一键全量读取全国交通联合卡/城市公交卡/银联金融卡的卡号、发行机构、有效期、电子钱包余额及多笔交易记录。
24. **`scan_cpu_card_filesystem(max_depth: int = 2)`**
    - **说明**：深度遍历 CPU 卡内部的 Master File (MF) 与 Dedicated Files (DF) 目录树。

### 3.7 Dump 镜像文件管理

25. **`load_dump_file(filepath: str)`**
    - **说明**：载入 `.dump`, `.mfd`, `.bin`, `.mct`, `.eml`, `.json` 格式的 Dump 文件至内存。
26. **`save_dump_file(filepath: str)`**
    - **说明**：将当前内存 Dump 导出为各种格式文件保存。
27. **`get_dump_summary()`**
    - **说明**：获取当前 Dump 的全景统计（卡型规格、扇区数、有效块/坏块比例、已知密钥）。
28. **`verify_and_repair_dump(repair: bool = False)`**
    - **说明**：校验 Block 0 BCC 校验位与扇区控制字补码合法性，可选自动纠错修复。
29. **`compare_dumps(dump_a_path: str, dump_b_path: str)`**
    - **说明**：逐块对比两个 Dump 文件的差分变化。

### 3.8 卡片档案与流水审计数据库

30. **`query_card_profile(uid: str)`**
    - **说明**：从 SQLite 库中查询卡片档案（持卡人、卡类型、门禁换算号、刷卡计数、建档时间）。
31. **`upsert_card_profile(uid: str, card_name: str, card_holder: str, card_type: str, note: str)`**
    - **说明**：新增或修改卡片归档档案。
32. **`list_registered_cards()`**
    - **说明**：获取数据库中全部建档卡片列表。
33. **`get_swipe_history(limit: int = 50)`**
    - **说明**：分页查询历史刷卡日志流水。
34. **`record_swipe_log(uid: str, raw_hex: str = "")`**
    - **说明**：向数据库追加一条刷卡记录并递增刷卡计数。

### 3.9 外部密码学攻击工具

35. **`get_external_tools_status()`**
    - **说明**：探测本地 `tools/m1t/nfc-bin` 目录下 `mfoc`, `mfcuk`, `libnfc_hardnested` 的就绪状态。

---

## 4. 核心实战工作流

### 场景一：读卡器连接与智能卡快速巡检
1. 调用 `list_serial_ports()` 扫描可用串口；
2. 调用 `connect_reader(port="COM3", baudrate=115200)` 初始化硬件；
3. 调用 `poll_card()` 寻卡。如果检测到卡片，提取 UID 与换算信息；
4. 若需要识别是否已登记，调用 `query_card_profile(uid=card["uid"])`。

### 场景二：M1 卡密码字典恢复与全卡备份
1. 调用 `poll_card()` 确认卡片在位；
2. 调用 `crack_card_keys(start_sector=0, end_sector=15, crack_mode="fast")` 恢复各扇区密钥；
3. 调用 `get_dump_summary()` 检查已恢复状态；
4. 调用 `save_dump_file(filepath="backups/card_dump.mct")` 导出为 MCT 格式备份。

### 场景三：二代身份证物理识别
1. 将身份证贴近读卡器；
2. 调用 `read_id_card()`，读取返回的 8 字节 GUID 与 4 字节 PUPI；
3. 系统在后台自动完成非标 Type B 射频寄存器配置与操作后的 Type A 复位。

### 场景四：全国交通联合卡/金融卡余额流水查询
1. 将交通卡贴近读卡器；
2. 调用 `read_cpu_card_public_info()`；
3. 直接获取标准解析的卡号、发卡机构、卡片余额（元）与最近充值/消费明细流水。

---

## 5. 硬件安全红线准则 (Strict Guardrails)

在通过 MCP 调用硬件时，LLM 必须时刻遵守以下安全约束：
1. **DTR/RTS 禁用**：物理传输驱动已强制保持 DTR/RTS=False，严禁通过任何方式拉高，以免引发 CH340E/CP2102 复位死锁。
2. **Block 0 默认防写**：严禁向普通 Mifare Classic 芯片的 Block 0 执行常规写块指令，写入 Block 0 必须调用 `write_magic_block0` 且必须明确为魔术卡。
3. **UFUID 锁死二次确认**：UFUID 锁死为单向永久硬件固化，不可逆转，在未获得用户明确二次授权前严禁传参 `confirm=True`。
4. **广播器单向只读**：简易广播发卡器物理上不接受任何下行帧，严禁对其下发认证、写卡或探测指令。
