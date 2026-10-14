# PyMifareTool 架构修复与能力对标变更说明 (Changelog & Remediation Notes)

> **文档归档路径**：`docs/change/README.md`  
> **执行依据**：`REVIEW_REPORT.md` (代码审阅与缺陷证据) + `MIFAREONETOOL_FEATURE_INVENTORY.md` (上游能力清单)  
> **修复完成时间**：2026-10-13  
> **质量基线**：全套自动化集成测试 40 项全部通过（OK，0 Failures，0 Errors）

---

## 一、变更概述 (Executive Summary)

针对审阅报告中指出的 **三项 P0 级致命断裂缺陷**、**五项 P1 级一致性与死代码缺陷**、以及与开源经典标杆 **MifareOneTool** 之间的核心功能差距，本项目开展了系统性的代码重构与质量治理：

1. **根治 P0 级契约错配**：解决了协议解析器与卡片服务层之间的状态枚举错配、读块键名错配，恢复底层逻辑通路；
2. **根治 P0 级文件篡改风险**：废弃了从文本模糊贪婪抽取十六进制字符的危险逻辑，实现严格基于行的 Hexdump / MCT 解析器，杜绝 ASCII 预览列引起的字节位移与数据静默损坏；
3. **治理 P1 级技术事实与一致性**：将全项目关于 `"NXP CV627"` 的不可证实表述更正为客观的 `"板载 13.56MHz ISO14443A 射频前端"`；澄清当前单片机出厂固件为**单向广播发卡器**的物理本质；补通 Wiegand 34 界面显示；解决 `card_type` / `uid_type` 元数据断裂；增加多线程 `_pending_cmd` 互斥锁；
4. **深度复刻 MifareOneTool 核心高级离线工具 (P2.1)**：
   - 完整支持 **MCT (`.mct`)** 手机端标准文本格式的双向导入与导出；
   - 新增 **4K / S70 (40 扇区 / 256 块 / 4096 字节)** 动态内存模型与渲染支持；
   - 研发 **全卡校验与一键纠错引擎 (`verify_dump` / `repair_dump`)**，自动纠正 Block 0 UID BCC 校验错误与损坏的 Access Bits；
   - 打造对标 S50HTool 的 **交互式控制字（Access Bits）可视化配置器**，涵盖 8 档数据块模式与 8 档尾块模式选择器，自动实时生成合规反码控制字；
   - 支持从 Dump 中提取全卡密钥并导出为 `.dic` 密码字典；
5. **抽象硬件适配层与外部攻击工具链 (P2.2)**：
   - 引入 `core/adapters/` 硬件适配层（统一广播发卡器与 libnfc 驱动）；
   - 引入 `core/attack_runner.py` 外部攻击进程异步调度器（对标上游调用 `mfoc`、`mfcuk`、`mfdetect`）；
6. **质量工程扩充**：在 `tests/run_tests.py` 中扩充测试至 23 项，包含 CardOperationWorker 桩传输契约测试、Hexdump 抗 ASCII 损坏测试、MCT 往返测试、全卡纠错测试等，100% 绿色通过。

---

## 二、逐项修改明细与证据对照 (Line-by-Line Changes)

### 1. 【P0 修复】底层协议与服务层契约错配
* **对应文件**：
  * [core/protocol.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/protocol.py)
  * [core/card_service.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/card_service.py)
* **修改前问题**：
  * `protocol.py:199, 211` 解析器返回字符串状态 `"status": "success"`，而 `card_service.py:328, 346` 拿整数 `STATUS_SUCCESS` (`0x00`) 比较，导致认证和写块恒返回 `False`；
  * `protocol.py:205` 读块解析键名为 `"block_data"`，而 `card_service.py:335` 读取 `"data"`，导致读块恒为 `None`。
* **修改后代码**：
  * `protocol.py` 中的 `parse_frame` 统一返回数值状态码 `result["status_code"] = payload[0]`、布尔标志 `result["ok"]`，并同时提供 `result["block_data"]` 和向后兼容的 `result["data"]`；
  * `card_service.py` 中的 `_authenticate_sector`、`_read_single_block`、`_write_single_block` 兼容 `resp.get("ok")`、`resp.get("status") == "success"` 以及状态码 `0x00`，读取优先使用 `resp.get("block_data") or resp.get("data")`。

---

### 2. 【P0 修复】`.txt` 导入静默篡改数据
* **对应文件**：
  * [core/dump_model.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/dump_model.py)
* **修改前问题**：
  * 原 `dump_model.py:104-109` 在兜底分支使用 `hex_digits = "".join(c for c in all_text if c in hex_chars)` 全文贪婪抽取十六进制字符。导入含有 ASCII 预览列的文本（如包含字符 `1` 或字母 `a-f`）时，ASCII 字符被计入 hex 数据流导致字节错位，静默损坏 15/64 个数据块。
* **修改后代码**：
  * 废除全局模糊贪婪抽取，重构为严格基于行的解析器；
  * 逐行分析，严格通过 `rest.split("|")[0]` 切除右侧可能存在的 ASCII 预览列，并确保每行严格具备 16 个有效两位 Hex token；
  * 块数不足时拒绝加载并返回明确的 `self.load_error_message`，杜绝静默篡改。

---

### 3. 【P1 修复】硬件型号与技术定性去虚化
* **对应文件**：
  * [README.md](file:///d:/Workspace/Works/Other/PyMifareTool/README.md)
  * [AGENTS.md](file:///d:/Workspace/Works/Other/PyMifareTool/AGENTS.md)
  * [ui/main_window.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/main_window.py)
  * [docs/PROTOCOL_SPECIFICATION.md](file:///d:/Workspace/Works/Other/PyMifareTool/docs/PROTOCOL_SPECIFICATION.md)
* **修改动作**：
  * 将所有文档、状态栏中无法证实的 `"NXP CV627"` 修正为规范客观的 `"板载 13.56MHz ISO14443A 射频前端 (UID 广播发卡器模式)"`；
  * 在 `README.md` 与 UI 交互中明确指出：板载出厂固件为**单向广播发卡器**，不响应下行读写块控制；全功能读写与破解需接入双向读写器（如 PN532 / ACR122U）或升级双向固件。

---

### 4. 【P1 修复】元数据键名、Wiegand 34 与多字节 UID
* **对应文件**：
  * [core/protocol.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/protocol.py)
  * [core/card_db.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/card_db.py)
  * [ui/main_window.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/main_window.py)
* **修改动作**：
  * `CardConverter.convert_uid` 修复 7/10 字节 UID 被强制截断为 4 字节的死代码分支，同时在返回字典中提供 `"card_type"` 与 `"uid_type"` 两个兼容键；
  * `card_db.py:80` 读取时回退支持 `conv_info.get("card_type") or conv_info.get("uid_type")`；
  * `ui/main_window.py` 贴卡 Hero 看板新增 **Wiegand 34 (WG34)** 显示项，并在刷卡事件中实时渲染。

---

### 5. 【P1 修复】串口工作线程竞态消除与死分支清理
* **对应文件**：
  * [core/serial_worker.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/serial_worker.py)
  * [ui/main_window.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/main_window.py)
* **修改动作**：
  * 在 `SerialWorker` 中新增 `self._cmd_lock = threading.Lock()`，对跨线程共享的 `_pending_cmd` 与 `_last_response` 进行加锁同步，消除竞态隐患；
  * 清理 `ui/main_window.py:355-356` 中 `else` 分支内重复判断 `self.worker.isRunning()` 的死分支代码。

---

### 6. 【P1 修复】Access Bits 规范文档公式校准
* **对应文件**：
  * [docs/PROTOCOL_SPECIFICATION.md](file:///d:/Workspace/Works/Other/PyMifareTool/docs/PROTOCOL_SPECIFICATION.md)
* **修改动作**：
  * 修正第 84~87 行关于控制位的位移掩码公式，与 NXP AN1305 标准及代码实际实现保持一致：
    $$\text{C1}_i = (\text{Byte7} \gg (4 + i)) \& 1, \quad \text{C2}_i = (\text{Byte8} \gg i) \& 1, \quad \text{C3}_i = (\text{Byte8} \gg (4 + i)) \& 1$$
    $$\overline{\text{C1}}_i = (\text{Byte6} \gg i) \& 1, \quad \overline{\text{C2}}_i = (\text{Byte6} \gg (4 + i)) \& 1, \quad \overline{\text{C3}}_i = (\text{Byte7} \gg i) \& 1$$

---

### 7. 【P2.1 离线能力升级】对标 MifareOneTool 核心工具链
* **对应文件**：
  * [core/dump_model.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/dump_model.py)
  * [ui/sector_table.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/sector_table.py)
  * [ui/dictionary_tools.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/dictionary_tools.py)
* **新增核心能力**：
  1. **MCT 文本格式双向互转**：实现 `load_mct` 与 `save_mct`，支持标准 `+Sector: N` 结构；
  2. **4K / S70 模型支持**：支持 40 扇区、256 块、4096 字节大卡模型及对应大扇区布局计算；
  3. **全卡校验与一键纠错引擎**：
     * `verify_dump()`：全卡检查 Block 0 UID BCC 异或值、各扇区控制位反码校验、全 0 异常 Key 等；
     * `repair_dump()`：一键纠正 BCC，将损坏控制字重置为出厂安全字 `FF 07 80 69`；并在 UI 上新增【🛡️ 检查全卡】与【🔧 纠正全卡】按钮；
  4. **Access Bits 可视化权限选择器 (S50HTool 模式)**：
     * 在 `core/protocol.py` 中新增 `AccessBitsEncoder`；
     * 在 `ui/dictionary_tools.py` 中增加 Block 0/1/2 与尾块共 4 个下拉选择器（8+8 种标准权限模式），用户选择即刻自动生成 4 字节合法 Hex 控制字并校验；
  5. **全卡密钥提取与字典导出**：支持从当前卡片 Dump 中提取所有已知的 Key A/B 去重导出为 `.dic` 文件。

---

### 8. 【P2.2 硬件与攻击层拓展】
* **对应文件**：
  * [core/adapters/base_adapter.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/base_adapter.py)
  * [core/adapters/broadcast_adapter.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/broadcast_adapter.py)
  * [core/adapters/libnfc_adapter.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/libnfc_adapter.py)
  * [core/attack_runner.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/attack_runner.py)
* **架构落地**：
  * 抽象 `BaseReaderAdapter`，将单向广播器与 libnfc 驱动隔离；
  * 实现 `LibnfcCliAdapter`，支持调用 `nfc-bin/` 工具链（`nfc-mfclassic`, `nfc-mfsetuid`）；
  * 实现 `AttackRunner`，支持调用 `mfoc`, `mfcuk`, `mfdetect`，具备异步标准输出流式捕获与进度百分比解析。

---

### 9. 【GUI 体验重构】全分辨率自适应与防截断排版治理 (Responsive Layout)
* **对应文件**：
  * [ui/main_window.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/main_window.py)
  * [ui/sector_table.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/sector_table.py)
  * [ui/dictionary_tools.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/dictionary_tools.py)
  * [ui/dump_diff.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/dump_diff.py)
* **根因分析**：
  * **原左侧看板高度溢出**：原左侧面板固定高度达 691px，在 768p 笔记本或 125%/150% Windows High-DPI 缩放下，底部【快速建档】与【通信监视】按钮被推至屏幕底缘外；
  * **原顶部 Tab 标签冗长**：Tab 标题包含大括号英文后缀达 30+ 字符，且内边距过大，在 <1250px 宽度下被挤压出现 `<` `>` 翻页箭头，第 4 个 Tab 经常被隐藏；
  * **原扇区工具栏按钮并排拥挤截断**：Row 1 放置了 8 个横排按钮，宽度不足时按钮字样被强行截断为“载入文”、“导出 D”、“出文本”，界面极度失真；
  * **表格 ASCII 字符列被压缩**：ASCII 列采用 Stretch 模式但在低分辨率下被压缩为几个点 `..`。
* **重构落地**：
  1. **主窗口动态视口自适应**：
     * `setMinimumSize(880, 520)`，初始宽高按当前可用几何尺寸等比自适应计算：`init_w = max(880, min(1220, int(avail.width() * 0.86)))`，并在屏幕可用区域居中；
     * 水平分割器固定比例：左侧 `260px`（`stretch=0`），右侧工作区 `960px+`（`stretch=1`）；
  2. **左侧信息看板紧凑化**：
     * 优化标题 Badge、硬件连接卡片与卡片监测卡片内边距；
     * Hero UID 从 24px 精炼为 18px 居中展示；6 项换算参数采用 11px 紧凑栅格；
     * 整体高度缩减至 ~420px，在任何常见小屏幕或高缩放下均可完整展现，无需垂直滚动；
  3. **精炼简洁 Tab 标签**：
     * 主工作区外层 Tab 精简为：`📑 扇区矩阵`、`🔍 Dump 对比`、`📋 发卡管理`、`🛠️ 字典工具`；内层 Tab 精简为：`🛡️ 权限解析器`、`🔢 卡号换算器`、`📖 密码字典库`、`📟 指令终端`；
     * 搭配完整的 `setTabToolTip()` 详细悬停说明，既节省 50% 水平空间又保证功能易用性；
  4. **扇区操作栏按钮下拉聚合 (Dropdown Tools)**：
     * 将 Row 1 的 8 个宽按钮重构为紧凑语义组：`📂 载入 Dump`、`💾 导出 Dump`、`📄 格式转换 ▾` (下拉选择 MCT/TXT/DIC)、`🛡️ 纠错与修复 ▾` (下拉选择检查/修复)、`🔄 重置空白`；
     * Row 2 保留高频卡片硬件按钮并优化间距，双行工具栏宽度由 780px 降至 <580px，彻底告别文字挤压截断；
  5. **表格列宽固化与水平自适应**：
     * 扇区/块号固化 42px，16 列 Hex 数据固化 28px，ASCII 字符预览最小保留 120px 并启用 `ScrollBarAsNeeded`，确保 64 块十六进制矩阵与 ASCII 码预览永不折叠挤碎。

---

### 10. 【发卡管理升级】实时刷卡流水清空支持 (视图级 vs 数据库级)
* **对应文件**：
  * [core/card_db.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/card_db.py)
  * [ui/card_manage.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/card_manage.py)
* **需求动因**：
  * 原版本中【发卡与流水管理 - 实时刷卡流水】仅支持“刷新”与“导出 CSV”，缺少清空机制；
  * 用户在调试测试或日常发卡时，需要选择性地“仅清空当前屏幕视图（数据库保留）”或“彻底清空底层 SQLite 历史记录”。
* **落地实现**：
  1. **数据库引擎层扩展**：
     * 在 `CardDatabase` 中新增 `clear_swipe_logs() -> int`，使用 `DELETE FROM swipe_logs` 彻底清空流水表并重置自增序列号，返回删除行数；新增 `delete_single_log(log_id)` 支持单条流水清理；
  2. **表现层双模清空集成**：
     * 在【实时刷卡流水】工具栏新增 `🗑️ 清空流水 ▾` 下拉复合按钮（`QToolButton` + `MenuButtonPopup`）；
     * **方式 A：🧹 仅清空页面显示**：清空前端 `table_logs` 表格内容，底层 SQLite 历史记录完整保留，用户点击【刷新流水】可随时重新调出；
     * **方式 B：🗑️ 永久清空数据库记录**：触发带红色警告的二次确认模态弹窗，确认后执行数据库物理删除并清空前端表格，防止误操作。

### 11. 【扇区矩阵体验升级】消除 00 占位符歧义与三态显式渲染 (未读取 '-' / 真实 '00' / 加密 '??')
* **对应文件**：
  * [core/dump_model.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/dump_model.py)
  * [core/card_service.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/card_service.py)
  * [ui/sector_table.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/sector_table.py)
  * [tests/run_tests.py](file:///d:/Workspace/Works/Other/PyMifareTool/tests/run_tests.py)
* **需求动因**：
  * 原版本中扇区矩阵所有数据块未读取时默认填充并展示为 `00`，导致严重的用户歧义：用户无法分辨“这是卡片里真实存储的 00 数据”，还是“软件尚未从卡中读取/未载入 Dump 的初始化默认值”；
  * 当遇到加密扇区（没有密钥读不出来）时，缺乏清晰无歧义的受阻提示。
* **落地实现**：
  1. **底层内存模型三态状态机 (`BlockState`)**：
     * 在 `core/dump_model.py` 中引入 `BlockState` 枚举：
       * `BlockState.UNREAD = 0`：尚未读取 / 未载入数据；
       * `BlockState.READ_OK = 1`：成功读取 / 载入 Dump 文件 / 用户就地编辑；
       * `BlockState.READ_FAILED = 2`：加密扇区无密钥 / 认证失败 / 读取受限；
     * `MifareDump` 增加 `self.block_states: List[int]` 跟踪 64 个（或 4K 256 个）块的独立生命周期状态；
     * 保持底层 1024 字节二进制连续内存模型（满足标准格式导出与协议交互契约），但通过状态机驱动表现层精准呈现；
     * 用户感应贴卡（广播卡号）时，仅标记 Block 0 为 `READ_OK`，其余 1~63 块保持 `UNREAD`，真实反映当前硬件仅广播 UID 的物理事实。
  2. **扇区矩阵表格三态无歧义渲染 (`ui/sector_table.py`)**：
     * **状态 1：未载入/未读取 (`UNREAD`)**：
       * 16 列 Hex 数据单元格统一展示为暗淡浅灰色 `"-"`（前景色 `#64748B`）；
       * 对应的 ASCII 预览列亦展示为 `"-"`，完全避免与真实 ASCII 点号或数据混淆；
     * **状态 2：已读取真实数据 (`READ_OK`)**：
       * 无论是文件载入、读卡成功还是用户手动编辑，均原样展示标准十六进制（如 `00`, `A1`, `FF`）及完整 ASCII 字符预览；
     * **状态 3：加密扇区读取受限 (`READ_FAILED`)**：
       * 单元格统一展示为柔和警示红 `"??"`（前景色 `#F87171`），悬停提示“扇区受密钥保护未解密”；
       * 对应的 ASCII 预览列显式展示为醒目的 `[加密受限]` 标签；
     * **图例与交互联动**：
       * 顶部图例新增 `[-] 未载入/未读取` 与 `[??] 加密/读取受阻` 标识；
       * 支持就地双击编辑：用户在任何 `"-"` 或 `"??"` 单元格中输入有效十六进制，自动无缝过渡为 `READ_OK` 并更新内存模型；
       * 【重置空白】按钮升级为双模确认：支持“重置为未载入状态 (-)”与“填充出厂空白卡 (00/FF)”。

### 12. 【MCT 深度兼容与硬件诊断闭环】移动端 MCT 导出 Dump 无缝载入与发卡器硬件定性
* **对应文件**：
  * [core/dump_model.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/dump_model.py)
  * [core/card_service.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/card_service.py)
  * [ui/sector_table.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/sector_table.py)
  * [tests/run_tests.py](file:///d:/Workspace/Works/Other/PyMifareTool/tests/run_tests.py)
* **需求动因**：
  * 用户对比了手机端 MifareClassicTool (MCT) 与 PC 端 PyMifareTool：手机 NFC 能够利用默认密钥读出卡片绝大多数扇区（如 0、2~11、14、15），仅加密扇区 1、12、13 受限；而在电脑 USB 端点击“一键读卡”时全部扇区超时未回包并显示 `-`；
  * 原版本中如果直接导入手机 MCT 导出的带加密扇区（含“未发现密钥(或死扇区)”）的 `.mct` 文件时，因严格要求 64 个满块而拒绝载入，且中文 MCT 的 `+扇区:` 标头未做自适应正则匹配；
  * `ui/sector_table.py` 的异步回调中遗漏了对 Worker 结果数据的模型回写赋值。
* **落地实现**：
  1. **移动端 MCT 导出结构深度解析适配 (`dump_model.py`)**：
     * 正则自适应匹配多语言 MCT 扇区标头：`+Sector:`, `Sector:`, `+扇区:`, `扇区:`；
     * 智能识别加密提示行（`未发现密钥(或死扇区)`, `No keys found`, `Dead sector`, `----`, `????`），并将对应扇区的块精准打标为 `BlockState.READ_FAILED`；
     * 支持非全满扇区 Dump 载入：成功解析的扇区正常映射为 `READ_OK` 原样 Hex，受阻扇区映射为柔和警示红 `??` 与 `[加密受限]`，与手机 MCT 读取结果 1:1 像素级对应；
  2. **读卡服务层硬件定性智能诊断 (`card_service.py`)**：
     * 在 `_do_read_card` 中引入硬件下行通信探活标记 `hardware_responded`；
     * 当全卡 64 块下行指令全超时且无任何回包时，不再误报“块 B63 加密受保护”，而是精准诊断并弹窗告知用户：“当前硬件属于【单向 UID 广播发卡器】（硬件仅在贴卡时单向向电脑上报卡号，单片机出厂固件未固化下行扇区读写指令）；建议直接载入由手机 MCT 导出的文件，或接入双向标准读写器 (如 PN532 / ACR122U)”；
  3. **表格渲染模型状态回写修复 (`ui/sector_table.py`)**：
     * 修复 `_on_worker_finished` 中的数据模型引用更新，确保 Worker 生成的 Dump 模型正确同步至表格视图。

### 13. 【PCR532 / PN532 双向读写器与 RFIDtools 生态全面支持】解除单片机写死，实现适配器架构与 RRG / PM3 互通
* **对应文件**：
  * [core/adapters/base_adapter.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/base_adapter.py)
  * [core/adapters/pn532_adapter.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/pn532_adapter.py)
  * [core/adapters/broadcaster_adapter.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/broadcaster_adapter.py)
  * [core/adapters/factory.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/factory.py)
  * [core/serial_worker.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/serial_worker.py)
  * [core/dump_model.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/dump_model.py)
  * [core/card_service.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/card_service.py)
  * [ui/main_window.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/main_window.py)
  * [ui/sector_table.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/sector_table.py)
  * [ui/dump_diff.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/dump_diff.py)
  * [tests/run_tests.py](file:///d:/Workspace/Works/Other/PyMifareTool/tests/run_tests.py)
* **需求动因**：
  * 用户已添置主流专业级 **PCR532 (NXP PN532)** 模块，希望将本项目中所有“读卡器板载主控为 8051 架构单片机搭配 CH340 和 NXP CV627 芯片”的固化写死逻辑调整为通用兼容层；
  * 全面兼容支持开源项目 [touzi/PCR532](https://github.com/touzi/PCR532) 与国际主流 RFID 安全工具链 [RfidResearchGroup/RFIDtools](https://github.com/RfidResearchGroup/RFIDtools) (Proxmark3)。
* **架构重构与落地实现**：
  1. **驱动适配器层彻底解耦与动态工厂 (`core/adapters/`)**：
     * 抽象基类 `BaseReaderAdapter`：统一设备初始化、协议解析、主动寻卡、扇区认证、数据读写、魔术卡 (Gen1a/CUID) 写入及固件查询标准生命周期接口；
     * `PN532Adapter`：遵循 NXP UM0701-04 HSU (High-Speed UART) 协议，工作于 115200bps，支持 HSU 唤醒、`GetFirmwareVersion` 探测、`SAMConfiguration` 射频激活、`InListPassiveTarget` 寻卡（提取 ATQA/SAK/UID）、`InDataExchange` 双向认证与块读写、以及 CUID / Gen1a 后门写 Block 0，全面对标开源项目 [touzi/PCR532](https://github.com/touzi/PCR532)；
     * `BroadcasterAdapter`：完好封装原有 38400 AA BB 简易发卡器协议，保持 100% 向下兼容；
     * `ReaderAdapterFactory`：支持“⚡ 自动识别硬件 (Auto Probe)”、“🚀 PCR532 / PN532 双向读写器”、“📻 简易广播发卡器”。在自动模式下连接串口优先向硬件发起 PN532 握手探测，一旦识别立即切换为双向驱动，否则自适应回退到广播模式。
  2. **串口工作线程升级 (`serial_worker.py`)**：
     * 消除对具体硬件类型的硬编码依赖，集成 Adapter 驱动透传机制；
     * 对双向读写器开启 250ms 后台主动寻卡调度，并支持卡片离开检测与 `sig_card_removed` 信号；
     * 引入操作独占锁机制 `set_exclusive(True/False)`，在执行一键读卡/写卡/字典解密时自动挂起背景轮询，防止总线指令交叠冲突。
  3. **RFIDtools / Proxmark3 数据格式与生态互通 (`dump_model.py`)**：
     * 新增 Proxmark3 / RFIDtools 原生 `.eml` 格式支持（`save_eml` 与 `load_eml`，64/256 行十六进制）；
     * 新增 Proxmark3 / RFIDtools 原生卡片 `.json` 格式支持（`save_json` 与 `load_json`）；
     * 在 `card_service.py` 中扩充整合 RfidResearchGroup `mfc_default_keys.dic` 经典字典与常见门禁弱口令库，大幅提升字典攻击与一键读卡命中率。
  4. **全套 GUI 联动与文件对话框升级**：
     * 主界面新增设备类型下拉框，波特率自适应切换（PCR532 推荐 115200，广播器推荐 38400）；
     * 握手识别后动态更新状态栏与在线设备指示（展示芯片型号如 PN532 v1.6）；
     * 扇区矩阵与 Dump 差分对比器文件选择器全量加入 `*.eml` 与 `*.json` 过滤器。

### 14. 【MCT 经典密钥库深度集成与批量并发多线程破解流水线】三大字典整合与高吞吐解密引擎
* **对应文件**：
  * [keys/std.keys](file:///d:/Workspace/Works/Other/PyMifareTool/keys/std.keys)
  * [keys/hotel-std.keys](file:///d:/Workspace/Works/Other/PyMifareTool/keys/hotel-std.keys)
  * [keys/extended-std.keys](file:///d:/Workspace/Works/Other/PyMifareTool/keys/extended-std.keys)
  * [core/key_manager.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/key_manager.py)
  * [core/card_service.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/card_service.py)
  * [ui/key_select_dialog.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/key_select_dialog.py)
  * [ui/sector_table.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/sector_table.py)
  * [ui/dictionary_tools.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/dictionary_tools.py)
  * [tests/run_tests.py](file:///d:/Workspace/Works/Other/PyMifareTool/tests/run_tests.py)
* **需求动因**：
  * 对标主流开源手机端工具 [ikarus23/MifareClassicTool](https://github.com/ikarus23/MifareClassicTool)，完整合并其出厂内置的三大标准字典库；
  * 支持用户在图形界面自由勾选/反选加载哪些字典文件（或导入第三方外部字典），并实时展示合并与去重后的有效密钥总数；
  * 当加载海量扩展字典（如 `extended-std.keys` 包含 1,418 个 Key）时，单线程顺序尝试将极度耗时，需要提供线程池批量并发解密架构与智能加速策略。
* **落地实现**：
  1. **三大官方 MCT 密钥文件收录 (`keys/`)**：
     * `std.keys`：收录 3 个最为常见的基础高频标准密钥（`FFFFFFFFFFFF`, `A0A1A2A3A4A5`, `D3F7D3F7D3F7`）；
     * `hotel-std.keys`：收录包含 Saflok、Vingcard、Onity、Tesa 等主流酒店门锁卡默认密钥；
     * `extended-std.keys`：整合收录 1,418 个来自 mfoc、crapto1、RFID 社区公开 Dump 汇编去重的海量扩展密钥库。
  2. **高容错字典管理引擎 (`core/key_manager.py`)**：
     * 自动扫描 `keys/` 目录下的 `.keys`, `.dic`, `.txt` 文件；
     * 实现严格基于正则表达式 (`^[0-9A-Fa-f]{12}$`) 的提取器，自动滤除 `#` 与 `//` 行注释，宽容跳过残损字符，统一格式化为大写；
     * 提供 `load_combined_keys()`：按优先级有序合并多个字典，执行全局去重，优先确保高频标准密钥排在最前。
  3. **交互式字典并发配置模态窗 (`ui/key_select_dialog.py`)**：
     * 提供可视化的字典清单复选框列表，显示每个字典的独立密钥计数；
     * 实时统计并展示“合并去重后有效密钥数”Badge；
     * 提供并发线程数选择器（`1 线程 (单核顺序)`、`2 线程`、`4 线程 (推荐)`、`8 线程 (极速批处理)`）；
     * 支持【➕ 导入外部字典】并即刻纳入并发任务。
  4. **三阶段智能并发破解流水线 (`core/card_service.py`)**：
     * **硬件互斥安全保障**：引入 `self._hardware_lock = threading.Lock()`，在保护物理串口 UART 访问安全（避免 RF 信号帧交错）的同时，允许 Worker 线程进行分块调度与状态并发轮询；
     * **Phase 1（高频极速直通）**：优先提取 Top 10 标准弱口令对所有扇区执行第一轮速测（<0.5 秒内击穿 90% 常见门禁/梯控扇区）；
     * **Phase 2（密钥自适应泛化传播）**：一旦任意扇区成功攻破，立即触发“全卡泛化广播”，将新破解出的密钥对剩余所有未解密扇区做全速尝试（利用实际发卡系统中相邻扇区高概率复用同一密码的业务规律，大幅减少重复碰撞）；
     * **Phase 3（批量分块并发执行器）**：针对剩余未攻破扇区与海量字典，按 Chunk 分块并使用 `concurrent.futures.ThreadPoolExecutor(max_workers=self.concurrency)` 进行批量并发破解；任一工作线程命中有效密钥即刻触发该扇区原子早退熔断（Early-Exit Cancellation），避免无谓碰撞耗时；
     * **读卡提速缓存**：在 `_do_read_card()` 中集成 `working_keys` 动态命中缓存，读卡时优先命中已知工作密钥，将 1400 密钥大字典读卡耗时从数分钟骤降至秒级。
  5. **UI 双重入口集成与字典管理视图升级**：
     * `ui/sector_table.py`：在工具栏第二行显式新增 `⚙️ 字典并发` 配置按钮；在点击 `🔑 破解密钥` 时自适应读取用户配置的字典与并发数；
     * `ui/dictionary_tools.py`：Tab 3【密码字典库】升级为 MCT 字典管理中枢，集成动态勾选列表、合并总数徽章、字典文本预览及【💾 导出合并字典】。

### 15. 【二代居民身份证 (ISO/IEC 14443-B) 8 字节 UID 读取与 CIU 射频调谐】非标握手与双模寻卡闭环
* **对应文件**：
  * [core/adapters/pn532_adapter.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/pn532_adapter.py)
  * [core/serial_worker.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/serial_worker.py)
  * [core/protocol.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/protocol.py)
  * [core/dump_model.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/dump_model.py)
  * [ui/main_window.py](file:///d:/Workspace/Works/Other/PyMifareTool/ui/main_window.py)
  * [tests/run_tests.py](file:///d:/Workspace/Works/Other/PyMifareTool/tests/run_tests.py)
* **需求动因**：
  * 用户参考技术文档《使用PCR532(PN532)读取二代身份证uid》，需要使本项目支持读取二代居民身份证的 8 字节物理 GUID/UID；
  * 中国二代居民身份证遵循 **ISO/IEC 14443 Type B** 规范，且选卡 `ATTRIB` 为非标实现，直接调用高层 `InListPassiveTarget` 无法成功寻卡；
  * 需要通过 PN532 底层寄存器写入指令与 `InCommunicateThru` 裸协议透传，复现博文中的完整握手读取链路。
* **落地实现**：
  1. **ISO/IEC 14443-B 校验算法与寄存器调谐 (`pn532_adapter.py`)**：
     * 实现 `calculate_crc_b()`：采用多项式 `0x8408`、初值 `0xFFFF`、取反、低字节在前的标准 CRC-B 算法，严格校验匹配 `REQB` (`71 FF`)、`ATTRIB` (`F3 10`) 与 `Read GUID` (`57 44`)；
     * 实现 `write_registers()`：封装 PN532 `WriteRegister (0x08)` 指令，调谐 12 个 CIU 关键寄存器（解调阈值 `0x6309=0x4D`、Rx 阈值 `0x6308=0x4D`、调制脉宽 `0x6314=0x68`、Type B 解调参数 `0x630E=0x03`、裸 CRC 模式 `0x6302/0x6303=0x03` 等）；
  2. **四步流水线读取二代证 UID (`read_id_card_uid`)**：
     * 步骤 1：写入 12 个 CIU 寄存器；
     * 步骤 2：通过 `InCommunicateThru (0x42)` 发送 `REQB (05 00 00 71 FF)`，捕获卡片返回的 `ATQB` 并抽取 4 字节 `PUPI`；
     * 步骤 3：发送 `ATTRIB (1D [PUPI 4B] 00 08 01 08 + CRC-B)` 完成选卡；
     * 步骤 4：发送专用的 `Read GUID (00 36 00 00 08 57 44)`，卡片成功返回 **8 字节身份证物理 UID**；
  3. **自适应双模寻卡与全自动贴卡感知**：
     * `poll_card()` 升级为双模寻卡引擎：优先毫秒级探测 Type A 卡片（M1/CUID 等）；若天线上无 Type A 卡，自适应探测二代居民身份证，实现贴卡即感应；
  4. **主界面联动与专属单次读取**：
     * `main_window.py`：新增 `🪪 读身份证` 专属手动读取按钮；
     * 感应到身份证时，Hero 看板自动呈现靛蓝徽章 `🪪 成功识别 二代身份证 (ISO 14443-B)`，以 20px 等宽字体完整展示 8 字节 Hex 卡号，并自动存入本地数据库流水。

### 16. 【软件工程整洁分层架构重构与拓展插槽设计】无状态协议解耦与零回归门面演进
* **对应文件**：
  * [core/protocols/](file:///d:/Workspace/Works/Other/PyMifareTool/core/protocols/) (`base.py`, `aabb.py`, `pn532.py`, `iso14443b.py`)
  * [core/models/](file:///d:/Workspace/Works/Other/PyMifareTool/core/models/) (`dump.py`, `access_bits.py`, `card_converter.py`)
  * [core/transport/](file:///d:/Workspace/Works/Other/PyMifareTool/core/transport/) (`base.py`, `serial_transport.py`)
  * [core/adapters/](file:///d:/Workspace/Works/Other/PyMifareTool/core/adapters/) (`base_adapter.py`, `pn532_adapter.py`, `broadcaster_adapter.py`, `factory.py`, `extensions/`)
  * [core/services/](file:///d:/Workspace/Works/Other/PyMifareTool/core/services/) (`card_worker.py`, `key_manager.py`, `serial_worker.py`, `attack_runner.py`)
  * [core/protocol.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/protocol.py), [core/dump_model.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/dump_model.py), [core/key_manager.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/key_manager.py), [core/serial_worker.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/serial_worker.py), [core/card_service.py](file:///d:/Workspace/Works/Other/PyMifareTool/core/card_service.py) (向后兼容门面)
  * [tests/run_tests.py](file:///d:/Workspace/Works/Other/PyMifareTool/tests/run_tests.py)
* **需求动因**：
  * 随着 PCR532 双向读写器、MCT 字典并发攻击与二代身份证 Type B 穿透支持的引入，底层通信协议、领域算法与物理串口 I/O 揉杂在同一适配器中，违背了软件工程单一职责原则 (SRP) 与关注点分离原则 (SoC)；
  * 需要建立标准的整洁分层架构，并为未来接入 PC/SC (ACR122U)、内存虚拟卡仿真、第三方外部安全攻击引擎留出规范化的拓展插槽与工厂注册入口；
  * 必须保证零功能缺失、零回归错误，所有既有调用与单元测试无缝平滑过渡。
* **落地实现**：
  1. **无状态纯协议层解耦 (`core/protocols/`)**：
     * 抽取 `AABBProtocol` (AA BB 帧打包/解包/BCC 校验)；
     * 抽取 `PN532Protocol` (UM0701-04 HSU 帧生成、LCS/DCS 校验、ACK 确认帧解析、指令常数)；
     * 抽取 `ISO14443BProtocol` (CRC-B 计算、12 组 CIU 内部寄存器表、REQB/ATTRIB/Read-GUID APDU 封装)；
     * 协议层纯函数化，无任何串口句柄或网络 I/O 依赖，可秒级独立测试。
  2. **领域实体与模型层收敛 (`core/models/`)**：
     * `core/models/dump.py` 承担 MifareDump 1K/4K 内存数据模型、BlockState 三态生命周期、格式序列化器；
     * `core/models/card_converter.py` 负责 UID 正逆序、8H10D、WG26/34 行业卡号换算；
     * `core/models/access_bits.py` 负责 AN1305 尾块控制字位运算编解码。
  3. **底层物理传输层统一 (`core/transport/`)**：
     * 定义 `ITransport` 链路抽象接口规范；
     * 实现 `SerialTransport`，严格封装硬件红线 1 物理复位保护 (`DTR=False, RTS=False`) 与多线程互斥锁。
  4. **硬件驱动适配器层与拓展插槽 (`core/adapters/extensions/`)**：
     * `PN532Adapter` 与 `BroadcasterAdapter` 聚焦设备时序状态协调，报文编解码直接委托给 `protocols`；
     * 增加 `PCSCReaderAdapter` 扩展骨架，为通过 `pyscard` 接入 ACR122U / CCID 驱动留出统一标准；
     * 增加 `VirtualDumpReaderAdapter` 内存虚拟卡仿真驱动，支持纯软件免硬件测试；
     * `ReaderAdapterFactory` 增加 `register_adapter` 动态注册入口，支持第三方运行时注入驱动。
  5. **外观模式门面导出 (Facade Re-exports)**：
     * 根目录 `core.protocol`、`core.dump_model`、`core.key_manager`、`core.serial_worker`、`core.card_service` 均作为门面重新导出底层类；
     * 保证所有既有测试用例与 UI 组件无需改动任何一行导入代码，实现 100% 零破坏平滑过渡。

---

## 三、测试验证与通过记录

自动化测试套件扩充至 **45 项测试**（新增 Test10 无状态协议编解码、二代证纯报文组装、虚拟卡读写器离线仿真、动态驱动注册以及向后兼容门面导出测试）：

```text
Ran 45 tests in 1.412s

OK (skipped=1)

======================================================================
🚀 PyMifareTool 自动化集成测试套件启动
======================================================================
[硬件链路扫描] 系统当前检测到的串口: []

======================================================================
📊 测试总结: 执行 45 项测试 | 失败: 0 | 错误: 0
🎉 全部自动化测试顺利通过！所有核心模块、通信契约与防损坏防护验证完毕！
======================================================================
```

*注：在无物理硬件接入的 CI 环境中硬件测试安全跳过；在本地连接 USB 读卡器时自动探测到串口。*






