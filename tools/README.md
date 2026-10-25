# tools - 硬件联调与协议逆向辅助脚本

本目录存放开发阶段的串口/射频探测脚本，**不属于**桌面端运行时依赖。所有脚本均需手动执行，执行前请关闭 `main.py`，避免与 `SerialWorker` 争用同一 COM 口。

> ⚠️ 硬件安全：直接打开串口会绕过 `SerialWorker` 的互斥锁与 DTR/RTS 保护。调试 CH340E 设备时务必保持 DTR/RTS 为低电平，禁止向简易单向广播发卡器发送下行指令。

## 设备探测与连通性

| 脚本 | 用途 |
| --- | --- |
| `card_detect.py` | 自动探测可用读卡器并尝试识别卡片 |
| `probe_reader.py` | 读取设备信息、探测固件响应 |
| `test_open.py` | 串口打开/关闭与 DTR/RTS 基础验证 |
| `test_echo.py` | 串口回环收发测试 |
| `test_idle.py` | 空闲状态监听，观察设备主动上报 |

## 波特率与协议实验

| 脚本 | 用途 |
| --- | --- |
| `decode_38400.py` | 38400bps 广播报文解码验证 |
| `decode_bits.py` | 位级波形/字节流辅助分析 |
| `test_all_bauds_pn532.py` | 遍历常用波特率探测 PN532 HSU |
| `test_candidate_commands.py` | 候选下行指令探测 |
| `test_patterns.py` | 发送特征字节模式并观察响应 |
| `test_protocol_commands.py` | AA BB 协议指令集联调 |
| `test_pn532.py` | PN532 基础命令与 ACK 握手测试 |
| `test_reset_and_boot.py` | 复位、唤醒与启动时序验证 |

## 监听与集成

| 脚本 | 用途 |
| --- | --- |
| `passive_listener.py` | 被动监听广播器 UID 上报 |
| `interactive_sniffer.py` | 交互式串口收发/嗅探终端 |
| `pn532_integration.py` | PN532 适配器端到端读写联调 |
| `pn532_worker_integration.py` | `SerialWorker` + PN532 异步链路联调 |

## 维护工具

| 脚本 | 用途 |
| --- | --- |
| `restore_lines.py` | 文本/日志行恢复辅助脚本 |

## 回归测试

这些脚本用于实物联调，不参与 `tests/run_tests.py` 的自动化套件。修改核心协议或适配器后，仍应以全量自动化测试为准：

```bash
python tests/run_tests.py
```
