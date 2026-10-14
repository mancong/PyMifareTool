# PyMifareTool 硬件通信协议与数据格式技术规范书

> **适用硬件**：基于 NXP CV627 + XB9AE 934GB + WCH CH340E 架构的 USB 13.56MHz RFID/NFC 读卡器  
> **通信参数**：波特率 38400 bps，数据位 8，校验位 None (无)，停止位 1 (8N1)

---

## 一、物理串口通信规范

| 参数项 | 配置值 | 说明 |
|:---|:---|:---|
| 接口类型 | USB 虚拟串口 (VCP) | WCH CH340E 芯片桥接 |
| 推荐波特率 | **38400 bps** | 读卡器出厂默认波特率 |
| 数据位 / 停止位 | 8 位 / 1 停止位 | 标准无校验 (8N1) |
| 流控与握手 | **无硬件流控** | **必须保持 DTR=False, RTS=False** (避免单片机复位) |

---

## 二、AA BB 协议帧结构定义

读卡器采用标准的定长/变长二进制帧协议：

```text
+----------+----------+--------+--------+------------------+--------+
| 帧头 1   | 帧头 2   | 长度   | 命令字 | 数据载荷 (Data)  | 校验和 |
| (0xAA)   | (0xBB)   | (LEN)  | (CMD)  | (N 字节, 可选)   | (BCC)  |
+----------+----------+--------+--------+------------------+--------+
  1 字节     1 字节     1 字节   1 字节       N 字节         1 字节
```

### 1. 字段详细解析
1. **帧头 (Sync Header)**：固定 `0xAA 0xBB`（2 字节）。
2. **长度位 (LEN)**：
   $$\text{LEN} = \text{CMD (1 字节)} + \text{Data (N 字节)} + \text{BCC (1 字节)} = N + 2$$
3. **命令字 (CMD)**：标识报文类型或操作指令代码（1 字节）。
4. **数据载荷 (Data)**：随具体命令变动的业务参数（如 UID、密钥、块号、控制字等）。
5. **异或校验和 (BCC Checksum)**：
   从长度位 (LEN) 开始，至数据载荷末字节为止的全部字节进行异或校验：
   $$\text{BCC} = \text{LEN} \oplus \text{CMD} \oplus \text{Data}[0] \oplus \text{Data}[1] \oplus \cdots \oplus \text{Data}[N-1]$$

---

## 三、指令字集与报文示例

### 1. 读卡器自动上报帧（进卡感应）
当 ISO 14443-3A 卡片贴近读卡器天线时，读卡器蜂鸣并向串口主动上报 9 字节卡号帧：

* **命令字**：`CMD = 0x01`
* **载荷内容**：4 字节卡片物理 UID（大端序）
* **报文示例**：
  ```text
  AA BB 06 01 D7 7E A0 DF D1
  ```
  * `AA BB`：帧头
  * `06`：长度 (LEN = 4 + 2 = 6)
  * `01`：命令 (0x01 = 感应上报 UID)
  * `D7 7E A0 DF`：4 字节物理 UID
  * `D1`：校验和 ($0x06 \oplus 0x01 \oplus 0xD7 \oplus 0x7E \oplus 0xA0 \oplus 0xDF = 0xD1$)

---

## 四、卡号格式多行业标准换算规范

针对 4 字节 UID（如 `D7 7E A0 DF`），行业内存在多种主流读卡显示格式：

| 格式名称 | 换算方法 | 示例值 (`D7 7E A0 DF`) | 应用场景 |
|:---|:---|:---|:---|
| **正序 Hex** | 直接十六进制大写展示 | `D7 7E A0 DF` | 程序员与底层分析 |
| **倒序 Hex** | 字节序列逆序 (Little-Endian) | `DF A0 7E D7` | 多数标准门禁系统 |
| **正序 10 进制** | `int.from_bytes(uid, 'big')` | `3615416543` | 早期一卡通系统 |
| **8H10D (倒序10进制)**| `int.from_bytes(uid[::-1], 'big')` 前补0至10位 | `3751837399` | **商用门禁、考勤机最主流格式** |
| **韦根 WG26** | 倒序第2字节为区号，后2字节为卡号 | `160,32471` | 经典 WG26 门禁读头标准 |
| **韦根 WG34** | 倒序前2字节为区号，后2字节为卡号 | `00160,32471` | 现代 WG34 门禁读头标准 |

---

## 五、Access Bits (控制字) 位运算解码表

Mifare Classic 1K 扇区尾块（Block 3, 7, 11...）的字节 6~8 决定了该扇区所有块的访问权限：

* **出厂默认控制字**：`FF 07 80 69`（传输配置/空卡模式，Key A 可认证，Key B 可读写）
* **只读保护控制字**：`08 77 8F 69`（只读锁卡模式，Key A/B 仅允许读数据，禁止修改）

### 控制位提取公式 (按照 NXP MF1S50 / AN1305 规范)：
对于块 $i \in \{0, 1, 2, 3\}$（块 3 为扇区尾块）：

$$\text{C1}_i = (\text{Byte7} \gg (4 + i)) \& 1, \quad \text{C2}_i = (\text{Byte8} \gg i) \& 1, \quad \text{C3}_i = (\text{Byte8} \gg (4 + i)) \& 1$$

其对应的取反校验位分布为：
$$\overline{\text{C1}}_i = (\text{Byte6} \gg i) \& 1, \quad \overline{\text{C2}}_i = (\text{Byte6} \gg (4 + i)) \& 1, \quad \overline{\text{C3}}_i = (\text{Byte7} \gg i) \& 1$$

必须满足 $\text{C}_k \ne \overline{\text{C}}_k$ 取反校验恒成立，控制字才被视为有效合法。

---

## 六、NXP PN532 HSU 通信协议帧技术规范

适用于 PCR532 / PN532 全功能双向读写器（基于 115200 bps 高速串口）：

### 1. HSU 帧结构定义
```text
+----------+----------+--------+--------+--------+------------------+--------+----------+
| 前导码   | 起始符   | 长度   | 长度验 | 标识符 | 数据载荷 (Data)  | 数据验 | 结束符   |
| (0x00)   | (00 FF)  | (LEN)  | (LCS)  | (TFI)  | (N 字节, 含 CMD) | (DCS)  | (0x00)   |
+----------+----------+--------+--------+--------+------------------+--------+----------+
  1 字节     2 字节     1 字节   1 字节   1 字节       N 字节         1 字节     1 字节
```
* **长度与长度校验**：
  $$\text{LEN} = \text{len(DATA)} + 1 (\text{包含 TFI}), \quad \text{LCS} = (-\text{LEN}) \ \& \ \text{0xFF}$$
* **帧标识符 (TFI)**：
  * 主机发往 PN532：`TFI = 0xD4`
  * PN532 返回主机：`TFI = 0xD5`
* **数据校验和 (DCS)**：
  $$\text{DCS} = (-(TFI + \sum \text{DATA})) \ \& \ \text{0xFF}$$
* **ACK 握手确认帧**：`00 00 FF 00 FF 00`

### 2. 常用操作命令字集
| 命令字 (CMD) | 协议名称 | 典型作用 |
|:---|:---|:---|
| `0x02` | `GetFirmwareVersion` | 获取固件版本与芯片标识 |
| `0x14` | `SAMConfiguration` | 配置射频安全模块 (进入 Normal 模式) |
| `0x4A` | `InListPassiveTarget` | ISO 14443-A 寻卡并捕获 UID |
| `0x40` | `InDataExchange` | Mifare Classic 密码认证 (0x60/0x61) 与块读写 (0x30/0xA0) |
| `0x42` | `InCommunicateThru` | 底层裸帧透传 (用于二代身份证 ISO14443-B 握手) |
| `0x08` | `WriteRegister` | 写入 CIU 射频内部寄存器参数 |

---

## 七、二代居民身份证 (ISO/IEC 14443-B) 穿透时序规范

由于二代身份证内部芯片为非标 ISO 14443 Type B 实现，标准 `InListPassiveTarget` 无法寻卡，需通过 CIU 寄存器重设与 `InCommunicateThru` 4 步时序穿透读取 8 字节硬件 GUID：

### 1. 12 组 CIU 内部射频寄存器配置
通过 `WriteRegister (0x08)` 指令调谐芯片射频参数：
```text
CIU_Mode: 0x6301 = 0xFF        CIU_TxAuto: 0x6305 = 0x00
CIU_TxMode: 0x6302 = 0x03      CIU_RxMode: 0x6303 = 0x03
CIU_TypeB: 0x630E = 0x03       CIU_Demod: 0x6309 = 0x4D
CIU_GsNOn: 0x6317 = 0xFF       CIU_CWGsP: 0x6318 = 0x3F
CIU_ModGsP: 0x6319 = 0x18      CIU_RxThreshold: 0x6308 = 0x4D
CIU_ModWidth: 0x6314 = 0x68    CIU_ManualRCV: 0x630D = 0x10
```

### 2. ISO 14443 Type B CRC-B 计算公式
多项式 `0x8408` (反转 `0x1021`)，初始值 `0xFFFF`，取反，低字节在前：
* `REQB (05 00 00)` 计算得 CRC-B 为 `71 FF`
* `Read GUID (00 36 00 00 08)` 计算得 CRC-B 为 `57 44`

### 3. 四步交互时序
1. **配置寄存器**：写入上述 12 组 CIU 寄存器；
2. **REQB 寻卡**：发送 `05 00 00 71 FF`，接收 `ATQB` 并抽取 4 字节 `PUPI`；
3. **ATTRIB 激活链路**：发送 `1D [PUPI 4B] 00 08 01 08 + CRC-B`；
4. **读取 8 字节 GUID**：发送 `00 36 00 00 08 57 44`，返回全球唯一 8 字节硬件 UID。

---

## 八、整洁分层架构设计规范 (Clean Architecture)

| 分层 | 职责定位 | 对应代码目录 |
|:---|:---|:---|
| **物理传输层** | 串口 I/O 读写、DTR/RTS 硬件安全保护、读写流锁 | [core/transport/](file:///d:/Workspace/Works/Other/PyMifareTool/core/transport/) |
| **无状态协议层** | 纯函数式二进制数据帧打包、解包与校验，无 I/O 状态 | [core/protocols/](file:///d:/Workspace/Works/Other/PyMifareTool/core/protocols/) |
| **领域模型层** | Mifare 内存数据结构、AccessBits 算法、卡号换算 | [core/models/](file:///d:/Workspace/Works/Other/PyMifareTool/core/models/) |
| **硬件适配器层** | 统一设备驱动标准抽象、工厂注册中心、未来拓展插槽 | [core/adapters/](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/) |
| **应用服务层** | 异步刷卡轮询、三阶段智能并发字典破解、全卡烧录 | [core/services/](file:///d:/Workspace/Works/Other/PyMifareTool/core/services/) |
| **表现层 (UI)** | PyQt6 现代暗黑科技风组件，通过 Qt 信号槽解耦交互 | [ui/](file:///d:/Workspace/Works/Other/PyMifareTool/ui/) |

