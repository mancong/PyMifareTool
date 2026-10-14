# PyMifareTool - 智能 Mifare Classic (M1卡) 全功能上位机管理套件

一款专为 Windows 平台打造的现代化、高颜值 **Mifare Classic (M1 卡)** 桌面端分析、暴力破解与发卡管理套件。
本项目基于 **Python 3.12 + PyQt6** 构建，深度集成对标 [MifareOneTool](https://github.com/xcicode/MifareOneTool) 的全功能体验，并遵循软件工程**整洁分层架构 (Clean Layered Architecture)** 进行模块解耦与拓展插槽设计。

---

## 🛠️ 多硬件自适应拓扑与驱动架构

PyMifareTool 具备自适应硬件探测与驱动协商能力，支持物理双向读写器、简易广播发卡器与内存离线虚拟仿真卡：

```text
                     [PyMifareTool 桌面端上位机]
                                  │
    ┌─────────────────────────────┼─────────────────────────────┐
    ▼                             ▼                             ▼
【专业 PCR532 / PN532】       【简易 UID 广播发卡器】        【💻 离线虚拟卡仿真器】
(115200 bps HSU 双向协议)    (38400 bps 单向广播帧)         (纯软件内存 Dump 映射)
  • NXP PN532 射频主控         • 8051 MCU + CV627            • 零硬件物理免插拔测试
  • M1/CUID 寻卡/认证/读写      • 被动监听 AA BB 上报卡号     • 虚拟扇区密钥认证/读写
  • 二代证 (ISO14443-B) 穿透   • 门禁发卡极速登记            • 自动化算法与流水平台
```

---

## ✨ 核心特性矩阵

1. **双硬件与离线虚拟仿真自适应协商**
   * **PCR532 / PN532 全功能模式**：支持 115200bps HSU 协议、SAM 配置、Mifare Classic 逐块认证与读写、Block 0 魔术卡改写；
   * **二代居民身份证 (ISO/IEC 14443-B) 8 字节 UID 穿透读取**：自适应调谐 12 组 CIU 射频寄存器，执行 REQB -> ATTRIB -> Read GUID 完整时序；
   * **软件虚拟卡仿真 (Virtual Dump Adapter)**：无需硬件即可挂载 `.dump` 进行离线寻卡、密码认证与读写调试。

2. **MCT 标准字典生态与智能三阶段并发破解**
   * 内置 `std.keys`、`hotel-std.keys` 与 1400+ 项 `extended-std.keys` 扩展字典；
   * 采用**三阶段启发式剪枝加速引擎**：
     * 阶段 1：极速高频出厂默认键筛查（<0.5s 秒破）；
     * 阶段 2：已破解密钥全卡扇区传导互通（95% 卡片复用命中）；
     * 阶段 3：多线程 ThreadPoolExecutor 并发批次块暴力测试，单扇区早退快速剪枝。

3. **16/40 扇区三态彩色矩阵与就地编辑 (Sector Table)**
   * 支持 Mifare Classic 1K (S50) 与 4K (S70)；
   * 严格三态生命周期可视化：`-` (未读取) / `Hex` (已读取/编辑) / `??` (加密未破)；
   * 支持单元格双击 Hex 就地编辑与自动防呆校验。

4. **全行业格式导入导出与双卡差分比对 (Diff Tool)**
   * 无缝双向兼容导入/导出 `.dump`、`.mfd`、`.bin`、`.mct` (MifareClassicTool)、`.eml` 与 `.json` (RFIDtools / Proxmark3)；
   * 字节级双卡 Dump 差分比对器，直观对比充值/消费前后数据变动。

5. **本地 SQLite 发卡登记与审计流水库**
   * 记录每次贴卡物理时间戳、Hex/8H10D/WG26/WG34 卡号、持卡人备注与原始报文；
   * 支持一键导出 CSV 报表与安全清空流水。

---

## 🏗️ 软件工程解耦与分层架构

工程严格划分 5 层边界，保障纯函数算法、设备驱动与物理 I/O 相互解耦：

* **底层传输层 (`core/transport/`)**：`ITransport` 链路抽象与 `SerialTransport`（严格保持 DTR/RTS=False 物理复位保护与线程互斥锁）；
* **无状态协议层 (`core/protocols/`)**：`PN532Protocol` (HSU/ACK)、`AABBProtocol` (AA BB/BCC)、`ISO14443BProtocol` (CRC-B/CIU寄存器)；
* **领域模型层 (`core/models/`)**：`MifareDump` (1K/4K 内存数据模型)、`CardConverter` (全格式换算)、`AccessBitsDecoder/Encoder` (控制字位运算)；
* **硬件适配器与拓展层 (`core/adapters/`)**：`BaseReaderAdapter`、`PN532Adapter`、`BroadcasterAdapter`、`ReaderAdapterFactory`、扩展插槽 `extensions/pcsc_adapter.py` 与 `extensions/virtual_adapter.py`；
* **应用业务服务层 (`core/services/`)**：`CardOperationWorker` (并发破解工作器)、`KeyManager` (字典分发)、`SerialWorker` (异步轮询)、`AttackRunner` (外部工具链包装)；
* **表现层 (`ui/`)**：基于 PyQt6 的现代暗黑科技风仪表盘组件。

---

## 🚀 快速启动

在终端中进入项目根目录：

```bash
cd D:\Workspace\Works\Other\PyMifareTool
python main.py
```

---

## 🧪 自动化测试验证 (质量准入标准)

本项目提供涵盖协议打包解包、位运算、4K 内存模型、SQLite、无头 GUI 交互、二代证时序、解耦分层与拓展插槽的 **45 项全自动集成测试套件**：

```bash
python tests/run_tests.py
```
* **运行结果**：`Ran 45 tests ... OK (skipped=1)`，零失败，零回归。

