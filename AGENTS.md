# AGENTS.md - PyMifareTool AI 协同开发与维护指导手册

> **致未来的 AI Agent / 开发者**：  
> 本文件定义了在本项目（`PyMifareTool`）中进行代码阅读、维护、调试、扩展及自动化测试时的**核心技术上下文、架构铁律、硬件安全红线与开发工作流**。在对本项目进行任何修改或生成新代码前，请务必完整理解本手册规范。

---

## 1. 项目基础元数据

* **项目名称**：`PyMifareTool` (智能 Mifare Classic M1 卡全功能上位机套件)
* **技术基座**：`Python 3.12+` / `PyQt6 6.8+` / `pyserial` / `sqlite3`
* **对标标杆**：开源经典 [MifareOneTool](https://github.com/xcicode/MifareOneTool)
* **运行平台**：Windows 10/11 (当前开发主环境，支持多平台扩展)
* **硬件环境**：支持双硬件架构自适应探测：
  1. **专业双向读写器**：`PCR532 / PN532`（NXP PN532 射频主控 + CH340E USB-UART，115200bps HSU 双向协议，全面支持 ISO14443 Type A 及二代身份证 Type B 读写/破解）；
  2. **简易广播发卡器**：板载 13.56MHz 射频前端 + 新唐 8051 MCU + CH340E（38400bps，出厂固件单向广播 UID）。

---

## 2. 核心架构与目录导航

整个工程严格遵循**软件工程整洁分层架构（Clean Layered Architecture）**，实现传输层、无状态协议层、领域模型层、硬件驱动适配器层与业务服务层的全面解耦：

```text
PyMifareTool/
├── core/                        # [核心引擎层]
│   ├── protocols/               # ── 无状态协议编解码层 (纯数据、无 I/O 依赖)
│   │   ├── base.py              # BaseProtocolCodec 协议抽象基类与异常
│   │   ├── aabb.py              # AA BB 简易读卡器协议帧解包/构建与 BCC 校验
│   │   ├── pn532.py             # NXP PN532 HSU 标准通信帧打包/解包/ACK校验
│   │   └── iso14443b.py         # 二代身份证 ISO14443-B CRC-B 计算与非标 APDU
│   ├── models/                  # ── 领域实体与模型层
│   │   ├── dump.py              # MifareDump 1K/4K 内存数据实体、三态生命周期、序列化器
│   │   ├── access_bits.py       # AccessBitsDecoder & Encoder 尾块控制字位运算算法
│   │   └── card_converter.py    # CardConverter (UID 正逆序/8H10D/WG26/34/二代证等换算)
│   ├── transport/               # ── 底层物理传输层
│   │   ├── base.py              # ITransport 通信链路抽象基类
│   │   └── serial_transport.py  # 物理串口安全传输 (严格保障 DTR/RTS=False 与互斥锁)
│   ├── adapters/                # ── 硬件驱动适配器层
│   │   ├── base_adapter.py      # BaseReaderAdapter 统一驱动抽象接口
│   │   ├── pn532_adapter.py     # PCR532 / PN532 双向读写器适配器 (委托至 protocols)
│   │   ├── broadcaster_adapter.py # 简易单向广播发卡器驱动适配器 (委托至 protocols)
│   │   ├── factory.py           # ReaderAdapterFactory 驱动工厂与动态注册中心
│   │   └── extensions/          # ── 【未来硬件与仿真扩展插槽】
│   │       ├── pcsc_adapter.py  # PC/SC (ACR122U / CCID) 免驱智能卡读卡器接入插槽
│   │       └── virtual_adapter.py # 内存虚拟卡离线仿真适配器 (支持纯软件免硬件测试)
│   ├── services/                # ── 应用业务服务层
│   │   ├── card_worker.py       # CardOperationWorker (三阶段并发字典破解/读写/缓存加速)
│   │   ├── key_manager.py       # KeyManager (MCT 密码字典生态解析/去重/合并分发)
│   │   ├── serial_worker.py     # SerialWorker (PyQt6 QThread 异步串口轮询与独占控制)
│   │   └── attack_runner.py     # AttackRunner & BaseAttackEngine (外部工具链抽象引擎)
│   ├── card_db.py               # SQLite3 本地卡片档案库与刷卡流水存储引擎 (双模清空)
│   ├── protocol.py              # 【门面导出】向下兼容 re-export 所有协议类与模型
│   ├── dump_model.py            # 【门面导出】向下兼容 re-export MifareDump / BlockState
│   ├── key_manager.py           # 【门面导出】向下兼容 re-export KeyManager
│   ├── serial_worker.py         # 【门面导出】向下兼容 re-export SerialWorker
│   └── card_service.py          # 【门面导出】向下兼容 re-export CardOperationWorker
├── ui/                          # [表现层] 现代暗黑科技风 PyQt6 组件
│   ├── main_window.py           # 主窗口仪表盘、连接管理、Hero UID 呈现、二代证专属读取
│   ├── sector_table.py          # 16/40 扇区三态彩色矩阵、就地编辑、字典并发配置弹窗联动
│   ├── card_manage.py           # 发卡档案管理、持卡人编辑、流水审计与双模清空
│   ├── dump_diff.py             # 双卡 Dump 字节级差分比对工具 (Diff Tool)
│   ├── dictionary_tools.py      # MCT 密码字典管理中枢、Access Bits 解析/编码、卡号换算
│   └── key_select_dialog.py     # 字典动态勾选、合并统计与多线程并发配置模态框
├── keys/                        # [MCT 标准字典库]
│   ├── std.keys                 # MCT 经典 3 项标准高频密码
│   ├── hotel-std.keys           # 经典主流酒店门锁卡默认密码
│   └── extended-std.keys        # 1418 项全网海量去重去损扩展字典
├── tests/                       # [质量工程]
│   └── run_tests.py             # 45 项全自动集成测试套件 (协议/解耦/模型/数据库/适配器/并发/二代证/GUI无头)
├── docs/                        # [系统文档]
│   ├── change/README.md         # 架构修复、P0/P1/P2重构、PCR532、MCT并发字典与架构解耦演进录
│   ├── PROTOCOL_SPECIFICATION.md# 硬件串口通信协议与算法技术规范书
│   └── README.md                # 文档索引
├── cards.db                     # 本地 SQLite 运行时数据库
├── main.py                      # 桌面端主程序启动入口
├── requirements.txt             # 依赖声明文件
└── README.md                    # 项目用户说明书
```

---

## 3. 🚨 硬件交互三大红线 (CRITICAL HARDWARE RULES)

当编写或修改与串口通信相关的代码时，**绝对不可触碰以下物理与逻辑红线**：

### 🔴 红线 1：强制保持 DTR / RTS 为 False (物理复位保护)
```python
# 必须在任何打开 serial.Serial 的地方严格声明：
ser.dtr = False
ser.rts = False
```
* **物理根因**：CH340E / CP2102 芯片的 DTR/RTS 引脚在硬件 PCB 上直接与主控芯片的复位端（RESET/BOOT）连通。上位机若拉高 DTR/RTS 会将单片机（8051 或 PCR532 射频控制器）锁死在物理复位状态，导致工作指示灯熄灭、系统“假死”。

### 🔴 红线 2：硬件双模态特性隔离与射频独占互斥 (PCR532 双向 vs 简易广播器)
* **硬件特性严格隔离 (`is_bidirectional`)**：
  * **简易发卡器（Broadcaster）**：出厂固件单向广播 UID（38400bps），未开启串口接收中断，**物理上不会响应任何上位机下行指令**。切勿对其发送任何读写、认证或寄存器配置指令；
  * **PCR532 / PN532 全功能读写器**：基于 115200bps HSU 双向协议，完整支持 Type A (M1/UID/CUID) 寻卡、认证、读写以及二代身份证 (ISO14443-B) 8 字节 GUID 穿透读取。
* **射频半双工与串口通信独占互斥 (`set_exclusive` & `_hardware_lock`)**：
  * 13.56MHz 高频电磁场属于单载波半双工环境，且串口物理总线同一瞬间只能交互一帧数据。
  * 在执行任何长耗时底层操作（全卡读取、扇区写入、并发字典破解、二代身份证专用时序读取）时，**必须调用 `serial_worker.set_exclusive(True)` 暂停后台自动轮询**；
  * 所有的底层数据收发必须受 `self._hardware_lock` 线程锁保护，**绝对禁止工作线程与后台轮询线程并发向物理串口抛掷指令**，否则会导致 UART 粘包错乱或卡片 Mifare 密码认证状态瞬时丢失。

### 🔴 红线 3：Block 0 厂商/UID 块写保护 (防止卡片报废)
* Mifare Classic 1K/4K 的 Block 0（0 扇区 0 块）存放原厂物理 UID、BCC 校验及厂商硬件配置数据。
* 普通原厂 IC 卡（S50/S70）的 Block 0 在物理制造时已熔丝固化，尝试写入会导致写错误甚至卡片永久变砖锁死；仅 CUID（后门指令直接写）或 Gen1a（特殊唤醒后门盲写）魔术卡支持改写 Block 0。
* 任何涉及写卡、Dump 还原的业务逻辑，必须默认开启 `allow_block0_write = False`，除非用户在 UI 上显式取消勾选写保护并确认风险。

---

## 4. 关键协议与数据结构规范

### 1. 通用 AA BB 协议帧封装 (简易广播器)
```text
[AA BB] [LEN] [CMD] [DATA (0~N 字节)] [BCC]
```
* $\text{LEN} = \text{len(DATA)} + 2$
* $\text{BCC} = \text{LEN} \oplus \text{CMD} \oplus \text{DATA}[0] \oplus \cdots \oplus \text{DATA}[N-1]$
* 自动上报进卡帧：`AA BB 06 01 [4字节UID] [BCC]`

### 2. NXP PN532 HSU 标准通信帧协议 (PCR532)
```text
[00 00 FF] [LEN] [LCS] [TFI] [DATA...] [DCS] [00]
```
* **前导码与起始符**：`00 00 FF`
* **长度与长度校验**：$\text{LEN} = \text{len(DATA)} + 1$ (包含 TFI)，$\text{LCS} = (-\text{LEN}) \ \& \ \text{0xFF}$（满足 $(\text{LEN} + \text{LCS}) \ \& \ \text{0xFF} == 0$）
* **帧标识符 TFI**：主机发往下位机为 `D4`，芯片应答为主机为 `D5`
* **数据校验 DCS**：$\text{DCS} = (-(TFI + \sum DATA)) \ \& \ \text{0xFF}$
* **ACK 握手确认帧**：`00 00 FF 00 FF 00`

### 3. 二代身份证 (ISO/IEC 14443-B) 穿透握手时序 (PCR532)
二代居民身份证内置中国公安部定制的 ISO/IEC 14443-B 安全芯片（内部含国密算法，不可越权读取内部加密区，但物理 GUID 序列号开放可读）：
1. **CIU 射频寄存器配置**：写入 12 组 CIU 内部寄存器（包括解调器门限、副载波调制增益、接收通道滤波）；
2. **REQB 广播寻卡**：发送 `05 00 00`，解析带 CRC-B 的 ATQB 响应，提取 4 字节 PUPI；
3. **ATTRIB 激活物理信道**：发送 `1D [PUPI 4B] 00 08 01 08`，建立 Type B 射频传输通道；
4. **读取 8 字节 GUID 序列号**：通过 APDU `00 36 00 00 08` 穿透读取芯片全球唯一 8 字节物理硬件码。

### 4. 卡号标准换算规则
给定 4 字节（Type A M1卡）或 8 字节（二代身份证）大端序 UID：
* **正序十六进制**：`D7 7E A0 DF`（4字节）或 `08 61 24 5A 7B 8C 9D 0E`（8字节）
* **倒序十六进制**：`DF A0 7E D7`
* **8H10D (倒序十进制)**：将逆序字节转大端整数 `int.from_bytes(uid[::-1], 'big')` 并前补零至 10 位（示例：`3751837399`）。
* **韦根 WG26**：`f"{uid_rev[1]:03d},{int.from_bytes(uid_rev[2:4], 'big'):05d}"`（示例：`160,32471`）。

### 5. Access Bits 控制字结构
扇区尾块字节 6~8 存放 $C_1, C_2, C_3$ 控制位（带反码取反校验）：
* 出厂默认空卡控制字：`FF 07 80 69`
* 只读保护控制字：`08 77 8F 69`
* 任何修改必须通过 `AccessBitsDecoder` 校验合法性后再写入 `MifareDump`。

---

## 5. 日常开发与维护工作流

### 1. 运行应用程序
```bash
python main.py
```

### 2. 运行自动化集成测试 (质量准入标准)
在提交任何代码修改后，**必须在终端执行全量自动化测试套件**：
```bash
python tests/run_tests.py
```
* **通过标准**：45 项测试全部通过（`OK`, 0 failures, 0 errors, 1 skipped 物理串口）。
* 测试套件支持在无图形界面的 CI/无头环境（`offscreen`）下全自动仿真运行。

### 3. 代码编写风格约束
* **字符编码**：所有源码与文本文件必须严格保存为 **UTF-8 (without BOM)**，严禁混入 GBK 字符。
* **异步并发**：耗时任务（串口读写、网络、算法暴力破解）绝对禁止在 PyQt6 主 GUI 线程中同步执行，必须使用 `QThread`（如 `SerialWorker`、`CardOperationWorker`）并通过 Qt 信号槽与 UI 交互。
* **分层纯粹性**：协议编解码（`core/protocols/`）必须保持纯函数/无状态，严禁在协议类内持有串口或网络套接字句柄；物理 I/O 统一归入 `core/transport/` 与 `core/adapters/`。
* **类型标注**：优先使用 `typing.Dict`, `typing.List`, `typing.Optional`, `typing.Tuple` 进行类型提示。

---

## 6. 典型扩展任务与插件化指引 (For Future Agents)

### 任务场景 A：接入新的免驱 USB 读写器 (如 ACR122U / PC-SC 驱动)
1. 继承 [core/adapters/extensions/pcsc_adapter.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/extensions/pcsc_adapter.py) 中的 `PCSCReaderAdapter`；
2. 接入 `pyscard`，在 `poll_card()` 中发送 APDU `FF CA 00 00 00` 获取 UID，在 `authenticate()` 中发送 APDU `FF 86...`；
3. 调用 `ReaderAdapterFactory.register_adapter("pcsc", PCSCReaderAdapter)` 注册至工厂；
4. 在 [tests/run_tests.py](file:///d:/Workspace/Works/Other/PyMifareTool/tests/run_tests.py) 中追加对应单元测试。

### 任务场景 B：免硬件离线虚拟卡仿真测试
1. 使用 [core/adapters/extensions/virtual_adapter.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/extensions/virtual_adapter.py) 的 `VirtualDumpReaderAdapter`；
2. 调用 `adapter.set_virtual_dump(dump)` 挂载内存中的 Mifare 卡；
3. 上层业务可完全脱离物理 USB/串口硬件，对虚拟卡进行贴卡感知、密码验证与读写。

### 任务场景 C：挂载外部安全算法引擎 (Hardnested / Darkside)
1. 继承 [core/services/attack_runner.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/services/attack_runner.py) 中的 `BaseAttackEngine`；
2. 实现 `is_available()`、`start_attack()` 与 `cancel()` 接口规范；
3. 可包装外部开源工具（如 Proxmark3 / RFIDtools 的 `crapto1_bs.exe`）或直接编写纯 Python 破解算法。

### 任务场景 D：向 UI 添加新的实用工具 Tab
1. 在 `ui/` 目录下创建新组件（继承自 `QWidget`）；
2. 在 `ui/main_window.py` 的 `_init_ui()` 中将该组件添加到 `self.tabs`；
3. 遵循现有的暗黑科技风 QSS 样式表规范（`#0F172A` 背景，`#38BDF8` 高亮，`#1E293B` 容器卡片）；
4. 在 `tests/run_tests.py` 中添加无头仿真测试确保组件渲染不抛出未捕获异常。
