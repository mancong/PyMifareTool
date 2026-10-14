# PyMifareTool 项目审阅报告

**审阅日期**：2026-10-12
**审阅对象**：`D:\Workspace\Works\Other\PyMifareTool`
**审阅方式**：静态代码走查 + 本地可执行验证（无实机，本机无 COM 端口）+ 上游项目一手证据核对

> ⚠️ **基线声明**：审阅期间工作区被**并发修改**。`docs/`（3 个文件）、`AGENTS.md`、`README.md` 均为本次会话进行中被创建/追加；`tests/run_tests.py` 也在审阅中途被改写（317 行 → 296 行，其中 `Test05` 已改为缺少 `COM3` 时 `skipTest`，即与本报告 §4.4 的建议一致）。本报告所有结论均绑定到下列 SHA256 前 16 位快照，并在报告完成前复核：`core/`、`ui/`、`main.py` **全部未变**；`tests/run_tests.py` 已按**新版本**（`898E24E8B9BABC14`）重新验证。
>
> 若这些文件在报告之后再度变更，请以本表哈希为准。

| 文件 | 哈希 | 文件 | 哈希 |
|:---|:---|:---|:---|
| `core/protocol.py` | `3EBD5186CE0309FA` | `ui/main_window.py` | `E62DA88312A955ED` |
| `core/serial_worker.py` | `81137EDD30CCB8B4` | `ui/sector_table.py` | `498822C58DC5C003` |
| `core/card_service.py` | `C64D91F3659A753D` | `ui/dump_diff.py` | `040A35914459D1EC` |
| `core/dump_model.py` | `6242E2B24CDB9457` | `ui/card_manage.py` | `75847D8D4A80B6A3` |
| `core/card_db.py` | `F458B9696DB5121A` | `ui/dictionary_tools.py` | `70F72477DA352526` |
| `tests/run_tests.py` | `898E24E8B9BABC14` ※ | `main.py` | `32216ACD683DFD23` |

※ `tests/run_tests.py` 在审阅中途被并发改写（原 `16631E7FCDFBA22E`）。上表为新版本，§4.4 的测试结论已在新版本上复测。

---

## 一、总体结论（先看这里）

| 问题 | 结论 |
|:---|:---|
| **是否发挥了 CV627 芯片的全部实力？** | **完全没有。而且"CV627"这个型号本身无法证实，几乎可以肯定不是 NXP 的芯片。** 本项目与射频前端芯片之间**不存在任何通信通路**——没有任何寄存器级/SPI/I2C/RC522 指令操作，只被动接收 MCU 经 CH340E 播出的 UART 帧。按能力维度计，芯片的认证引擎（Crypto1）、READ/WRITE、值块操作、寄存器控制**全部闲置**。 |
| **是否完全复刻了 MifareOneTool 的功能？** | **没有，差距很大。** 29 项能力对照中仅 "差异比较" 1 项真正复刻（另 4 项部分等价），其余核心能力（5 类密钥恢复攻击、全套魔术卡操作、格式化、密钥文件、MCT 格式、全卡校验修复、多硬件后端）**均缺失**。而且仅有的"读卡/写卡/破解"三项因代码缺陷**必然失败**。 |

**一句话**：这是一个**功能完整度仅约 15%、且与硬件能力脱节**的项目。它把"离线文件分析工具"的骨架做得像样，但把"读写卡套件"的外观建立在一个**从未打通的协议**和一个**物理上不会回包的硬件**之上；同时它声称对标的 MifareOneTool 的核心价值（破解与魔术卡）几乎没有实现。

---

## 二、问题一：CV627 芯片能力发挥度

### 2.1 前提：型号归属存疑，且证据来源是项目自己

全仓库检索 `CV627` 仅出现在**项目自身的叙述文字**中，无任何数据手册、厂商页面、抓包记录或实物照片支撑：

- `README.md:18` — `[NXP 射频前端芯片 (CV627 / CV520 / RC522 衍生型)]`
- `ui/main_window.py:312` — 状态栏 `"就绪 - 支持 NXP CV627 + 新唐 ML51 + CH340E 读卡器"`
- `docs/PROTOCOL_SPECIFICATION.md:3`、`docs/AI_AGENT_DEVELOPMENT_PROCESS.md:36,40`、`AGENTS.md`

**对外核实结果（NXP 官方与分销渠道）**：

| 核查途径 | 结果 |
|:---|:---|
| NXP 官方 NFC Reader IC 全线目录 | 仅 CLRC663/plus、MFRC522、MFRC523、MFRC631、PN512、PN5180/5190、PN532、PN7120/7150/7160、PN7220、PN736X/7462/7642、PR5331、PRH601、SLRC610 — **无 CV627** |
| NXP 站内搜索 `CV627` | 空结果，无产品页、无文档 |
| Findchips（聚合 Arrow/Avnet/Mouser/Digi-Key 等） | `No results were found for CV627` |
| Alldatasheet | `No Data`（全球 `CV62x` 命中均为 Bourns/Stackpole 压敏电阻） |

NXP 的读卡/前端 IC 前缀仅为 `MFRC / CLRC / PN / PR / SLRC / PRH`，**不存在 `CV` 前缀**；`CV627` 在网络索引中实际指向服装/手表 SKU（Carven 手表 `CV627-RWH`、Brunello Cucinelli 毛衣 `M2200100CV627`）。

> 结论：**"NXP CV627"是一个无法证实的、由本项目自行产生的断言，且很可能是错的。** 最可能是廉价 UID 读卡器板厂的板型标号，或对 `CV520` 之类的误读。唯一可靠的澄清方式是**物理查看芯片封装丝印并拍照**——网络上不存在它的数据手册。
>
> 附带：同一叙述中的 MCU 标识也不自洽——`README.md:16` 写"新唐科技 ML51XB9AE"，而 `docs/AI_AGENT_DEVELOPMENT_PROCESS.md:37` 写"XB9AE 934GB"。后者更像把**丝印第一行（型号）与第二行（批次码）**误当作一个型号串。

### 2.2 关键事实：本项目从未与这颗芯片对话

这是比"型号写错"更本质的问题。审视数据通路：

```text
PC ──USB──> CH340E ──UART──> MCU(8051) ──SPI/I2C──> 射频前端芯片 ──RF──> 卡
     ↑ 本项目仅在此处收发        ↑ 固件逻辑全封闭，本项目无法触及
```

- `core/` 中**没有任何** SPI、I2C、RC522/MFRC522 寄存器读写、地址映射或位操作代码。
- `core/protocol.py` 定义的是**自定义 `AA BB` 帧**（`HEADER = 0xAA,0xBB`），这是 MCU 的串口协议，**不是**射频前端的 PCD 指令接口。芯片的 `FIFO`、`CommandReg`、`FIFODataReg` 等一概未使用。
- 因此本项目能拿到的一切，**都只是 MCU 固件愿意广播的内容**——即一个 4 字节 UID。

**能力维度利用率**：

| 前端芯片能力 | 本项目利用情况 |
|:---|:---|
| 寄存器/SPI/I2C 控制 | ❌ 零接触 |
| REQA/WUPA + 防冲突 + SELECT | ⚠️ 间接（由 MCU 固件完成，上位机只收结果） |
| MIFARE 三次认证 / Crypto1 引擎 | ❌ 完全未用 |
| READ (0x30) / WRITE (0xA0) | ❌ 完全未用 |
| 值块 INCREMENT/DECREMENT/RESTORE/TRANSFER | ❌ 完全未用 |
| HALT、射频场控制、天线增益 | ❌ 完全未用 |
| ISO14443-4 / 其他协议 | ❌ 完全未用 |

**唯一被利用的，是"读 UID"这一项**，而它还是 MCU 固件完成的，上位机连"请求"都没发出过（被动监听）。

### 2.3 项目自身文档已承认硬件是单向发卡器

`AGENTS.md`（"红线 2"）明确写道：

> 当前读卡器出厂烧录为**单向广播发卡器（UID Broadcaster）**，单片机主循环只在检测到进卡时向 UART TX 发送卡号 `AA BB 06 01 [UID] [BCC]`。单片机未开启串口接收中断，**物理上不会响应任何上位机下行指令**。

`docs/AI_AGENT_DEVELOPMENT_PROCESS.md` §六.2/§六.3 记录了穷举扫描结论：

> 读卡器在所有下发指令下**均保持完全静默（0 字节回包，全超时）**……单片机出厂固件**根本没有开启串口接收中断，也没有编写任何解析上位机指令的代码**。

**我的独立佐证**（未实机复现，但证据链一致）：
1. `tools/` 下 4 个探针脚本（`probe_reader.py`、`test_candidate_commands.py`、`card_detect.py`、`interactive_sniffer.py`）分别猜测了 4 套**互不相同**的协议——PN532 帧、STX 帧、BA 帧（SL018/031）、SL600 格式、单字节 `0x26/0x52`。若任何一套打通，开发者会固化下来而不是同时保留 4 套猜测。
2. `card_detect.py:79` 甚至在过滤"硬件串扰固定字" `00 05 03 20 05 23`——即收到的是自身发送字节的回显噪声，而非应答。
3. `tools/decode_bits.py` / `decode_38400.py` 中唯一"捕获"到的波形是 14 字节 `E0 1C FC FC 00 1C FC 1C …`（波特率不匹配的帧错误乱码），**仓库中不存在任何一次成功解出的 `AA BB` 下行应答**。
4. `cards.db` 中 23 条刷卡记录**全部是同一个 UID、同一帧** `AA BB 06 01 D7 7E A0 DF D1` ——与 README 示例完全一致。这说明**上行广播帧确实工作**（且是"单卡验证"），但也说明项目从未在多于一张卡上验证过任何东西。

> **小结（问题一）**：即使假设这颗芯片是一颗功能完整的 MFRC522 级前端，本项目也只用了它约 **1/8 的能力**，且是通过 MCU 固件间接使用的。真正的瓶颈是**封闭的单向 MCU 固件**——在这块硬件上，"发挥全部实力"物理上不可能，除非更换硬件（PN532/ACR122U/Proxmark3）或重新烧写 MCU 固件。这一点项目文档说对了，但 `README.md` 与 UI **仍在宣称支持读写卡，属于与自身文档冲突的过度宣传**。

---

## 三、问题二：MifareOneTool 功能复刻度

### 3.1 上游功能清单（一手证据）

我没有依赖二手描述，而是从上游仓库的 WinForms 设计器资源文件直接提取了真实控件文本与提示：

- `Form1.partial.resx`（主窗体，518 条属性）
- `FormHTool.resx`（集成 Hex 编辑器 S50HTool）
- `FormHardNes.resx`（HardNested 对话框）
- `Resources.Designer.cs`（全部字符串资源）

提取到的原始按钮文案（节选）：

```text
[设备控制]  检测设备(目前支持PN532、ACR122U) / 手动扫描 / 手动CLI / 停运行 / 清终端 / 存日志
[普通卡操作] 读M1 / 写M1 / 清M1 / 选择key.mfd(加载含密钥及控制位的MFD文件)
[魔术卡]    UID读 / UID写 / UID写号(厂商设为复旦) / UID全格(ACbit损坏·KEY被改的急救)
            / UID重置(0块UID随机) / 锁Ufuid(锁死UFUID 0块) / CUID写(CUID/FUID)
[破解]      MFOC读(Nested) / 全加密爆破(Darkside,mfcuk) / 字典测试(导入字典做Nested)
            / 知n密(已知密钥Nested) / 检加密(检测卡片加密情况)
[工具]      Hex编辑器 / 差异比较
```

字符串资源进一步确认：`开始执行HardNested收集数据……`、`开始执行HardNested解密强化卡……`、`nfc-bin/collect.exe`、`字典文件|*.dic`、`MCT格式`、`导入/导出MCT格式`、`导出密钥字典`、`检查全卡`、`检查并纠正全卡`、`列出全卡密钥`、`修改UID`、`已启用CUID空卡写入补丁`、`俄语`（多语言）。

即 MifareOneTool 的**五类密钥恢复能力**为：字典、已知密钥 Nested、Nested(mfoc)、Darkside(mfcuk)、**HardNested**；硬件后端为 **PN532 / ACR122U**（libnfc）。

**上游架构事实（决定了"复刻"的合理形态）**：MifareOneTool 本身**不含任何 NFC 代码**，它只是一个 C# WinForms **外壳**，实际靠调用随发布包提供的 libnfc 系列命令行程序完成工作：`nfc-scan-device.exe`（列设备）、`nfc-list.exe`（寻卡/取 UID）、`nfc-mfclassic.exe`（读/写/格式化）、`nfc-mfsetuid.exe`（魔术卡 0 块）、`mfoc.exe`（Nested）、`mfcuk.exe`（Darkside）、`cropto1_bs.exe`+`collect.exe`（HardNested）、`mfdetect.exe`（检加密）。**这些二进制不在仓库中**（以 `nfc-bin.zip` 发布资产形式提供）。

**上游自身的能力边界（用于公平对照）**：卡型**仅 Mifare Classic**，UI 明确写着"本工具仅支持 SAK=08/18/28 的卡片复制"（即 Classic 1K/4K/S70）；**不支持** Ultralight / NTAG / Plus / DESFire / ISO15693，也**不支持** Proxmark3 / RDM880；**没有**值块 init/inc/dec/restore/transfer 命令、韦根换算、UID 十进制换算、`.eml/.bin/.json`、内置默认密钥字典、卡号数据库、插件系统（界面语言仅中文+俄语）。

### 3.2 逐项对照

| # | MifareOneTool 能力（含上游实现方式） | PyMifareTool | 判定 |
|:--|:---|:---|:---|
| 1 | 检测/选择 NFC 设备（`nfc-scan-device`；PN532 UART 自动探测、ACR122U 经 DLL 切换） | 仅枚举 Windows COM 口 | ❌ 缺失 |
| 2 | 手动 CLI（在 `nfc-bin` 下开 `cmd`） | 有原始 Hex 调试终端 | ⚠️ 形似而非等价 |
| 3 | 读 M1（`nfc-mfclassic r A/B/x`，可加载密钥文件） | "一键读卡" | ❌ **因缺陷必然失败**（§4.1） |
| 4 | 写 M1（`nfc-mfclassic w`） | "一键写卡" | ❌ **因缺陷必然失败**（§4.1） |
| 5 | 清 M1 / 格式化普通卡（`nfc-mfclassic f`，需密钥） | 无 | ❌ 缺失 |
| 6 | 选择 `key.mfd`（含密钥**及控制位**）；**按 UID 自动加载** `auto_keys\<UID>*.mfd` | 无密钥文件概念；`.mfd` 仅当 1024B dump 处理 | ❌ 缺失 |
| 7 | 写前校验/写保护（`writecheck()` 预检 dump 合法性） | 无 | ❌ 缺失 |
| 8 | UID 读 / UID 写（含块 0） | 无 | ❌ 缺失 |
| 9 | UID 写号（指定卡号，厂商写"复旦"） | 无 | ❌ 缺失 |
| 10 | UID 全格 / 重置（ACbit 损坏·KEY 被改的急救） | 无 | ❌ 缺失 |
| 11 | 锁 UFUID（`-q -l`，不可逆警告） | 无 | ❌ 缺失 |
| 12 | CUID 写 / CUID/FUID 写入 + **CUID 空卡补丁**（`cuid_empty.kmf`） | 无 | ❌ 缺失 |
| 13 | **MFF08 CUID 修复**（v1.7.0，从上次写入的 dump 修复 0 块） | 无 | ❌ 缺失 |
| 14 | MFOC 读（Nested 破解；Ctrl+点击加已知密钥） | 无 | ❌ 缺失 |
| 15 | 字典测试（`mfoc -f` 导入 `.dic` 做 Nested） | 仅 16 条硬编码密钥线性尝试 | ❌ 不等价**且失效** |
| 16 | 知 n 密 / 知一密破解（`mfoc -k` 已知密钥 Nested） | 无 | ❌ 缺失 |
| 17 | 全加密爆破（Darkside，`mfcuk -v 3 -C -R -1 -s 250 -S 250`） | 无 | ❌ 缺失 |
| 18 | **HardNested**（`cropto1_bs`+`collect`，含"只采集不计算"、弱 PRNG 卡识别、云计算卸载） | 无 | ❌ 缺失 |
| 19 | 检加密 / 检测加密（`mfdetect`；Ctrl+点击加自定义密钥） | 无 | ❌ 缺失 |
| 20 | S50 Hex 编辑器：扇区/块 hex、KeyA/KeyB、**4 组 AC-bit 选择器**（8+8 条人类可读权限） | 表格双击改单字节 | ⚠️ 仅极小子集 |
| 21 | `检查全卡` / `检查并纠正全卡`（自动修复非法 AC 位、修正 UID 校验值） | 无（仅有离线解码器） | ❌ 缺失 |
| 22 | `列出全卡密钥` / `导出密钥字典` / `修改 UID` | 无 | ❌ 缺失 |
| 23 | 格式互转：`.mfd`/`.dump`/`.mct` 导入导出（MCT = Mifare Classic Tool 文本格式） | `.dump/.mfd/.bin/.txt`；**无 MCT**，且 `.txt` 有损坏缺陷（§4.2） | ⚠️ 部分且有问题 |
| 24 | 按 UID 自动命名保存 `auto_keys\<UID>_<时间>.mfd` | 无 | ❌ 缺失 |
| 25 | 差异比较（`FormDiff`，按块/按字节） | DumpDiff，逐字节 + 差值 | ✅ **已复刻（粒度更细）** |
| 26 | 运行日志落盘（`m1t.log`）/ 清终端 / 计时器 | 串口日志 + 刷卡流水 CSV | ⚠️ 用途不同 |
| 27 | 复制卡模式向导（一键解原卡→读→写新卡，含"请放原卡/请放新卡"引导） | "一键读卡/写卡"两按钮，无向导 | ❌ 缺失 |
| 28 | 单实例保护、GitHub 更新检查、中/俄双语 | 无 | ❌ 缺失 |
| 29 | 4K/S70（SAK=28）卡片支持 | 硬编码 1K（64 块/1024B） | ❌ 缺失 |

**计数：29 项对照中，真正复刻 1 项（#25），弱等价/部分 4 项（#2/#20/#23/#26），缺失 24 项。复刻度约 15%~20%。**
（完整上游功能清单与证据来源见随本报告保留的 `MIFAREONETOOL_FEATURE_INVENTORY.md`。）

### 3.3 PyMifareTool 相对上游的**独有**增量（应予肯定）

- SQLite 发卡档案 + 持卡人管理 + 刷卡流水审计与 CSV 导出（**上游完全没有**记录库）
- UID → 正/倒序 Hex、8H10D、WG26/WG34 换算看板（上游**无**韦根/十进制换算器）
- `AccessBitsDecoder` 完整 C1/C2/C3 反码校验 + NXP AN1305 权限表映射（**实现正确**，见 §4.4）
- 内置 16 条高频默认密钥表（上游**不含**内置字典，需用户自备 `.dic`）
- 实时贴卡 Hero 看板、串口报文流监视器、暗黑主题 UI 的完成度与工程质量高于上游

> **小结（问题二）**：**未复刻。** 更关键的是：本项目缺少的恰恰是 MifareOneTool 存在的**全部理由**——密钥恢复攻击与魔术卡操作。目前的 PyMifareTool 更像一个"**离线 dump 查看/比对器 + 刷卡登记台账**"，而非"M1 卡分析发卡套件"。公平地说，PyMifareTool 在**台账/换算/UI**这三个方向上确有上游不具备的增量；但这无法弥补核心能力的空缺。

---

## 四、实测确认的代码缺陷

以下均为我在本机**实际运行验证**的结果，非推断。

### 4.1 【P0】三处"契约错配"使读卡/写卡/破解必然失败

`core/protocol.py` 的解析器返回**字符串**状态，而 `core/card_service.py` 拿**整数常量**比较；且读块取错了字典键名。

| 位置 | 代码 | 解析器实际产出 | 后果 |
|:---|:---|:---|:---|
| `card_service.py:328` | `return status == ReaderProtocol.STATUS_SUCCESS` | `status` 为 `'success'`/`'auth_fail'` 字符串；`STATUS_SUCCESS` = `0x00` | **认证恒为 `False`** → 字典破解永不成功 |
| `card_service.py:335` | `data = resp.get("data", b"")` | 键名是 `block_data`（`protocol.py:205`） | **读块恒为 `None`** → "一键读卡"64 块全部报失败 |
| `card_service.py:346` | `return status == ReaderProtocol.STATUS_SUCCESS` | 同第一行 | **写块恒为 `False`** → "一键写卡"全部报失败 |

**复现证据**（用桩传输喂入真实解析器，即证明"解析器→服务层"契约断裂）：

```text
AUTH  -> service returns: False      (parser status: 'success'  ← 明明成功)
READ  -> service returns: None       (parser keys: [... 'block_data' ...])
WRITE -> service returns: False
```

**影响**：即使插入一台完美的双向读写器，`一键读卡`/`一键写卡`/`字典破解` **三个主打按钮依然 100% 失败**。这是本次审阅最严重的问题——它使 §二/§三 的争论变得次要：功能不是"受硬件限制"，而是"**代码本身就没接通**"。

### 4.2 【P0】`.txt` 导入静默损坏数据

`core/dump_model.py:104-109` 的兜底分支用"抽取全文所有十六进制字符"的方式还原数据：

```python
hex_digits = "".join(c for c in all_text if c in "0123456789abcdefABCDEF")
if len(hex_digits) >= self.TOTAL_BYTES * 2: ...
```

当导入**带 ASCII 预览列的常见 hexdump 格式**（其他工具普遍输出，且不含 `Block NN:` 关键字）时，ASCII 列中恰为十六进制字符的字符（`0-9`、`a-f`）会被错误计入，导致**字节流错位**。实测：

```text
loaded: True                       ← 返回"成功"
corrupted blocks: 15 / 64          ← 静默损坏
block 49 expected: 31 31 31 ... 31
block 49 got     : 00 00 00 00 00 00 00 00 31 31 31 31 31 31 31 31
```

**双重危害**：① 数据被静默篡改；② `load_from_file()` 返回 `True`，UI 弹出"导入成功"，用户无从察觉。对取证/比对类工具而言这是数据完整性事故。

### 4.3 【P1】其他功能与声明不符

| 问题 | 位置 | 说明 |
|:---|:---|:---|
| 7/10 字节 UID 支持是**死代码** | `protocol.py:172-176` | `uid_bytes = payload[:4]` 强制截断后再交给 `CardConverter`，故 `CardConverter` 的 7/10 字节分支在唯一调用点永不可达；且 7 字节 UID 会被截成 4 字节显示 |
| WG34 **算了但从不显示** | `protocol.py:265` → `ui/main_window.py` | `wiegand_34` 无任何 UI 消费点（`_on_card_swiped` 只设置 `val_wg26`），而 `README.md:43` 宣称显示 WG34 |
| `card_type` 键名不匹配 | `card_db.py:80` ← `protocol.py:270-274` | 生产者给的是 `uid_type`，消费者读 `card_type` → 数据库该字段**恒为默认字面量** |
| `MifareDump` 仅支持 1K | `dump_model.py:11-13` | 硬编码 64 块/1024B；载入 4096B 的 4K dump 会被**静默截断**且返回 `True`。无 Ultralight/NTAG/DESFire 支持 |
| 跨线程共享 `_pending_cmd` 无锁 | `serial_worker.py:88,154` | `send_and_wait`（在 `CardOperationWorker` 线程）与 run 循环无同步地读写该字段，存在竞态 |
| 启动即自动连接 | `main_window.py:141,341-344` | 只按端口数量决定连接，不校验设备身份，可能占用无关串口 |
| `_toggle_connection` 死分支 | `main_window.py:355-356` | `else` 分支内再判断 `isRunning()`，条件恒假 |

### 4.4 【P2】测试与文档的可靠性

**测试套件覆盖缺口**：`tests/run_tests.py` 的 15 项用例中，**没有任何一项覆盖 `core/card_service.py`** —— 这正是 §4.1 三个 P0 缺陷得以逃逸的直接原因。测试通过 ≠ 功能可用。建议优先补 `CardOperationWorker` 的桩测试（我已验证该桩方案可行）。

**测试结果（在新版 `tests/run_tests.py` = `898E24E8B9BABC14` 上实测）**：

```text
Ran 15 tests
skipped=1  ERROR=2
  ERROR: test_file_io_roundtrip      ← 沙箱禁止写入新建临时目录（环境因素）
  ERROR: test_swipe_and_persistence  ← 同上
  skipped: test_serial_port_detection ← 新版已改为无 COM3 时安全跳过 ✔
```

两项 ERROR 经我绕开沙箱后**直连验证功能正常**（`.dump`/`.txt` 往返、SQLite 增删改查均正确），因此**不计为项目缺陷**。原文 §4.4 关于 `Test05` 硬依赖 `COM3` 的问题，**已被审阅期间的并发修改修复**（现为 `skipTest`），此处据实更新。

**文档与代码矛盾**：`docs/PROTOCOL_SPECIFICATION.md:85` 给出的控制位公式

$$\text{C2}_0 = (\text{Byte8} \gg 4) \& 1,\qquad \text{C3}_0 = (\text{Byte8} \gg 0) \& 1$$

**与正确的代码实现相反**。`AccessBitsDecoder`（`protocol.py:345-354`）的位提取与 NXP MF1S50 规范一致：`C1_i=byte7[4+i]`、`C2_i=byte8[i]`、`C3_i=byte8[4+i]`，且数据块/尾块权限表与 AN1305 完全吻合——我用 `FF 07 80 69`（出厂）与 `08 77 8F 69`（只读）验证其 `valid` 与权限映射均正确。**是文档错了，不是代码错了。**

### 4.5 文档宣称与事实冲突清单

| 宣称位置 | 宣称内容 | 事实 |
|:---|:---|:---|
| `README.md:18`、`main_window.py:312` | "NXP CV627" | NXP 无此型号，无任何公开佐证（§2.1） |
| `README.md:43` | 显示 WG34 | 计算了但 UI 未显示（§4.3） |
| `README.md:38-65`、UI 按钮 | 读卡/写卡/字典破解 | 因 P0 缺陷必然失败（§4.1） |
| `README.md:50` | 支持 `.dump/.mfd/.bin/.txt` | `.txt` 对常见格式静默损坏（§4.2）；`.mfd` 密钥语义不支持 |
| `README.md:4` | "完整参照/升级了 MifareOneTool" | 复刻度约 15%~20%（§3） |
| `AGENTS.md` 红线 2 | 硬件不会响应任何下行指令 | ✅ 与其他文档一致；但与 README 的读写卡宣称**自相矛盾** |
| `docs/…PROCESS.md` §六.2 | 以 `sweep_commands.py` 的"全量指令空间穷举"作为硬件定性的决定性证据，并称已覆盖 `0x00~0x3F` 全部 64 个指令码 | ① 该 `sweep_commands.py` **在仓库中不存在**（`tools/` 实际只有 16 个文件），关键证据无法复核；② 现存的 16 个探针**从未测试** 0x22、0x30–0x37、0x40、0x50、0x60/0x61、0xF0 |

---

## 五、修复建议（按优先级）

**P0 — 先让功能"能通"**
1. 统一状态契约：令 `parse_frame` 返回稳定的枚举/常量（如 `status` 用 `STATUS_SUCCESS` 整型，或让服务层比较字符串），并加一处**契约测试**锁死。
2. `card_service.py:335` 改为 `resp.get("block_data")`。
3. `.txt` 导入：改为**按行严格匹配**（16 个两位 hex token/行），失败即返回 `False`，**禁止**"抽取全文 hex 字符"的模糊兜底；并对 <8 / >1024 字节输入给出显式错误而非静默补零/截断。
4. 补齐 `card_service` 测试（桩传输 + 真实解析器），覆盖认证成功/失败、读块 16B、写块成功/失败、中止。

**P1 — 让声明与事实一致**
5. 移除或改写一切 "NXP CV627" 表述为"板载 13.56 MHz ISO14443A 读卡前端（型号未确认）"；同步修正 `README.md:18`、`ui/main_window.py:312`、`docs/*`、`AGENTS.md`。
6. `README.md` 明确标注硬件为**单向 UID 广播发卡器**，读写卡/破解功能在当前硬件上**不可用**；或将这些按钮置灰并提示"需要 PN532/ACR122U 级硬件"。
7. 修正 `docs/PROTOCOL_SPECIFICATION.md:85` 的控制位公式。
8. 统一 `uid_type`/`card_type` 键名；删除或接通 `wiegand_34`；明确 1K-only 限制。

**P2 — 真要"复刻 MifareOneTool"**（按上游真实实现方式）
9. 抽象硬件适配层（`core/adapters/`），实现 **PN532(UART) 与 ACR122U(libnfc)** 后端——**这是所有破解/魔术卡功能的先决条件**。上游正是靠调用 `mfoc/mfcuk/crypto1_bs/nfc-mfclassic/nfc-mfsetuid/mfdetect` 这批 libnfc CLI 完成全部重活；可直接以子进程方式对接，亦可用 `libnfc` 的 Python 绑定重写。
10. 按依赖顺序补齐：密钥文件（`.mfd` 密钥+控制位 / `.dic` 字典）读写 → 写前校验 → 字典/已知密钥 Nested → mfoc(Nested) → mfcuk(Darkside) → HardNested（含"只采集不计算"）→ 检加密 → 魔术卡（UID 重置/写号/全格、UFUID 锁定、CUID/FUID 写入）→ 清 M1 → MCT 格式导入导出 → 全卡检查与纠正 → 列出全卡密钥/导出字典 → 复制卡向导。
11. 补 **4K/S70（SAK=28）** 卡型支持（现为 1K 硬编码）。注意：Ultralight / NTAG / Plus / DESFire / ISO15693 与 Proxmark3 后端**属超出上游范围的扩展**，不是"复刻缺口"，可按需另立目标。
12. `tests`：`Test05` 的 `skipUnless` 已由并发修改补上（§4.4）；剩余工作是**新增 `card_service` 覆盖**（见 P0-4），并在 CI 中分离"需要硬件的用例"。

---

## 六、审阅局限性（请一并采信）

1. **无实机**：本机 `serial.tools.list_ports.comports()` 返回 `[]`，我**未能**复现 §2.3 的硬件静默扫描。"全指令静默"来自项目文档（`AGENTS.md` + `docs/…PROCESS.md`），我的佐证是 4 套互斥探针脚本的存在、回显噪声过滤代码、以及 `cards.db` 中只有单一 UID 的 23 条记录。**建议在有设备的机器上重跑一次穷举扫描以最终定案。**
2. **上游功能清单**来自 GitHub **官方 API 一手抓取**：完整解码了 `MifareOneTool/Form1.cs`（master，66,885 B）、`Form1.zh.resx`、`FormHTool.resx`、`FormHardNes.resx`、`Properties/Resources.Designer.cs`，并核对了 releases / issues。**未获取**：仓库 wiki（不可达）、两份 PDF 手册、`nfc-bin.zip` 内容，以及 9 个较小的 `.cs` 文件（`ClassMifareS50.cs`、`FormHTool.cs`、`FormDiff.cs`、`FormHardNes.cs`、`FormMFF08.cs` 等）。故"有哪些功能按钮/后端调用"置信度**高**（有源码/资源字符串为证）；个别**算法内部实现与边界**未逐一核对，报告中已就地标注。完整清单见 `MIFAREONETOOL_FEATURE_INVENTORY.md`。
3. **`CV627` 定性**基于 NXP 官方目录与分销渠道的**否定性证据**。否定性证据无法 100% 排除"存在一颗无任何网络足迹的国产裸片"这一可能；最终判据只能来自**实物丝印**。
4. **工作区并发变更**：本次审阅进行中，`docs/`（3 个文件）、`AGENTS.md`、`README.md` 被其他进程/会话创建或追加，`tests/run_tests.py` 亦被改写。我已将全部结论绑定到 §一 的哈希快照，复核确认 `core/`、`ui/`、`main.py` 未被改动；若相关文件在报告之后再度变更，请以哈希为准。
5. **沙箱副作用（需人工清理）**：审阅过程中因 DSH 文件沙箱对"删除子目录"的 ACL 限制（工作区根目录含 `Everyone:(CI)(DENY)(DC)`），在项目根目录遗留一个**无法自动删除**的空目录 `.tmptest\`（内含两个空子目录 `.tmptest\tmpcw457hwg`、`.tmptest\tmpzavm8rj8`）。另一处 `_runtmp\` 已清理成功。源码未受影响；建议以管理员身份执行 `icacls .tmptest /reset /T /C` 后再删除。
6. **本报告不代表任何修复**：我**未修改任何一行项目源码**，仅新增本报告与上游功能清单两份文档。

---

*报告完成时间：2026-10-12 | 证据基线：§一 哈希表*
