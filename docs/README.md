# PyMifareTool 技术文档库

本目录汇集了 PyMifareTool 项目的系统级开发文档、逆向工程过程与底层技术规范。

---

## 文档目录索引

1. [**AI_AGENT_DEVELOPMENT_PROCESS.md (核心开发演进录)**](./AI_AGENT_DEVELOPMENT_PROCESS.md)
   * 记录从零开始基于无名 USB 读卡器，通过 AI Agent 逐步迭代开发出完整现代上位机软件的 6 大演进阶段。
   * 详细包含：硬件逆向、架构搭建、全量审计修复、深水区功能突破、实物人机联调结论与全自动集成测试闭环。
   * 提炼了 AI Agent 进行软硬件协同开发的八大黄金法则。

2. [**PROTOCOL_SPECIFICATION.md (通信协议与算法技术规范书)**](./PROTOCOL_SPECIFICATION.md)
   * 详述读卡器物理串口参数配置（38400 bps 8N1，DTR/RTS 安全策略）。
   * AA BB 协议帧封装格式与 BCC 异或校验算法。
   * 工业卡号换算标准（正反序 Hex、8H10D、韦根 WG26/34）。
   * Access Bits 权限位位运算解码与安全控制字规范。

3. [**MCT_MERGE_AND_REVIEW_GUIDE.md (再度审阅 + MCT 功能合并可行性评估与分阶段实施指导书)**](./MCT_MERGE_AND_REVIEW_GUIDE.md)
   * 对 PyMifareTool 的第二轮全量审阅（含写卡安全、2K 截断、`.mct` 未读语义、测试污染生产库等 25 项发现）。
   * 对上游 MifareClassicTool v4.3.1（GPLv3）的源码级解读与字节级文件格式规格（`.mct/.eml/.mfd/.bin/.json/.keys`）。
   * 30 项功能逐条可行性矩阵、两道硬闸门（许可证 / 硬件）、目标架构与接口契约，以及 Phase 0–5 分阶段落地方案。
   * 附录：格式速查表、许可证合规清单、上游 Python 工具可复用性评估。

---

## 相关文档

* [REVIEW_REPORT.md (第一轮代码审阅报告)](../REVIEW_REPORT.md) —— 历史体检报告，其整改结论已在本指导书 §2 中复核。
* [AGENTS.md (AI 协同开发与维护指导手册)](../AGENTS.md) —— 架构铁律与硬件安全红线。
