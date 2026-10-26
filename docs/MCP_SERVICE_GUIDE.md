# PyMifareTool MCP 对外服务集成与操作指南

## 1. 概述

`PyMifareTool MCP (Model Context Protocol) Server` 是为 `PyMifareTool` 智能卡上位机打造的标准对外协议接口。通过该服务，任何支持 MCP 协议的外部 AI Agent（如 Claude Desktop、Cursor、Cline、Gemini Antigravity 等）或自动化系统，均能以结构化 JSON-RPC 工具调用的方式安全操控本上位机的全部底层软硬件功能。

### 核心特性

- **官方标准支持**：采用官方推荐的标准 Python MCP SDK (`FastMCP`) 构建。
- **全异步执行架构**：底层 I/O 操作均通过 `asyncio.to_thread` 调度并受全局异步独占锁保护，确保 13.56MHz 半双工射频时序安全。
- **全功能覆盖**：覆盖硬件链路、M1 经典卡、魔术卡、密码学字典暴力破解、二代身份证物理读取、CPU 卡/APDU/交通联合、Dump 镜像管理、SQLite 档案库以及外部工具链等 **35 个核心 MCP Tools**。
- **全中文文档化**：所有 MCP 工具及其入参均配备纯中文详细描述与用法说明。
- **高度可配置**：支持配置文件 `mcp_server_config.json` 动态裁剪功能分类、指定传输模式（stdio / sse）、监听 IP 与端口、控制安全写入阈值。

---

## 2. 快速上手

### 2.1 依赖安装

已在项目环境安装 `mcp<2` (基于 `mcp 1.30.0` 兼容版本)：

```bash
pip install "mcp>=1.3.0,<2.0"
```

### 2.2 启动方式

#### 方式 A：标准输入输出模式 (stdio，推荐 Agent 嵌入)

```bash
python mcp_server.py
```

#### 方式 B：网络 HTTP/SSE 模式 (适用于远程局域网或微服务调用)

```bash
python mcp_server.py --transport sse --host 0.0.0.0 --port 8000
```

#### 方式 C：查看当前就绪的全部工具列表

```bash
python mcp_server.py --list-tools
```

---

## 3. 服务配置说明 (`mcp_server_config.json`)

服务启动时默认加载工作区根目录的 `mcp_server_config.json`：

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

### 配置项解析

| 字段名 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `server_name` | string | `"PyMifareTool-MCP"` | MCP 注册服务标识名 |
| `transport_mode` | string | `"stdio"` | 传输模式，可选 `"stdio"` 或 `"sse"` |
| `host` | string | `"127.0.0.1"` | SSE 模式绑定的 IP 地址 |
| `port` | int | `8000` | SSE 模式监听的 HTTP 端口 |
| `default_port` | string | `"COM3"` | 读写器默认串口名 |
| `default_baudrate` | int | `115200` | 读写器默认通信波特率 |
| `enabled_categories` | array | 全分类 | 动态加载的功能分类列表，不在其中的模块不会注册到 MCP 工具集 |
| `disabled_tools` | array | `[]` | 显式禁用的特定工具名称数组 |
| `allow_block0_write` | bool | `false` | 是否全局允许普通写入工具向 Block 0 写入（保护性开关） |

---

## 4. MCP 工具分类与字典

PyMifareTool 当前共对外提供 **35 个专用工具**：

### 1. 服务与硬件 (`hardware`)
- `get_mcp_service_status`：查询服务运行概况与已激活模块。
- `list_serial_ports`：枚举物理与 USB 虚拟串口。
- `connect_reader`：连接读写器并初始化设备。
- `disconnect_reader`：安全断开硬件释放资源。
- `get_device_status`：查询读卡器当前参数、固件与缓存 UID。
- `probe_capabilities`：全面探测设备软硬件能力与外部工具链。

### 2. 寻卡与卡号转换 (`card`)
- `poll_card`：执行一次射频寻卡，返回 UID/ATQA/SAK/ATS/卡型推断及 8H10D/WG26/WG34 编码。
- `is_card_present`：原位在位探测。
- `convert_uid_formats`：离线执行 UID 常见门禁编码与大小端十六进制换算。

### 3. Mifare Classic 核心读写 (`m1`)
- `authenticate_sector`：扇区密钥认证（Key A / Key B）。
- `read_block`：读取单块数据（可前置认证）。
- `write_block`：写入单块数据（带 Block 0 防写拦截）。
- `read_sector`：整扇区读取并解析尾块控制字 (Access Bits)。
- `write_magic_block0`：改写 CUID / GEN1A / UFUID 魔术卡 Block 0。
- `lock_ufuid_card`：永久固化锁死 UFUID 魔术卡为普通卡。

### 4. 字典与密钥恢复 (`cracking`)
- `list_key_dictionaries`：列出工作区 `keys/` 目录下全部字典文件。
- `parse_key_dictionary_file`：解析指定字典文件并提取有效十六进制密钥。
- `save_custom_keys`：向用户自定义字典 `custom.keys` 追加密钥。
- `get_card_known_keys`：从本地 SQLite 中查询指定卡片已恢复的已知密钥。
- `crack_card_keys`：针对在位卡片执行高阶字典恢复（支持 `fast`/`both`/`a`/`b` 策略）。

### 5. 二代居民身份证 (`id_card`)
- `read_id_card`：执行 ISO14443-B 非标握手读取 8 字节 GUID，并在结束后严格复位 Type A 寄存器。

### 6. CPU 智能卡与 APDU (`cpu_card`)
- `send_apdu`：向 CPU 卡发送原生 7816 APDU，遇 `61xx` 自动取回完整数据，遇 `6Cxx` 自动重发修正 Le。
- `read_cpu_card_public_info`：一键读取交通联合/银联卡卡号、有效期、电子钱包余额及多笔消费明细。
- `scan_cpu_card_filesystem`：遍历探测卡内目录与文件结构 (DF/EF)。

### 7. Dump 镜像文件管理 (`dump`)
- `load_dump_file`：载入 `.dump`/`.bin`/`.mct`/`.eml`/`.json`/`.txt` 镜像。
- `save_dump_file`：导出当前内存镜像。
- `get_dump_summary`：获取当前内存 Dump 全景统计。
- `verify_and_repair_dump`：校验 BCC 异或位与控制字补码，支持自动纠错修复。
- `compare_dumps`：对比两个 Dump 文件的扇区与块级差异。

### 8. 卡片档案与刷卡审计 (`database`)
- `query_card_profile`：查询卡片持卡人、卡类型、门禁换算号、刷卡次数与建档时间。
- `upsert_card_profile`：建档或更新卡片管理信息。
- `list_registered_cards`：列出已登记建档的全部卡片。
- `get_swipe_history`：分页查询刷卡审计流水日志。
- `record_swipe_log`：手动或被动记录刷卡流水。

### 9. 外部攻击工具链 (`external_tools`)
- `get_external_tools_status`：探测本地工作区 `tools/m1t/nfc-bin` 下 `mfoc`, `mfcuk`, `libnfc_hardnested` 的就绪状态。

---

## 5. 常见第三方 MCP 客户端配置示例

### 5.1 Claude Desktop 配置示例 (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "PyMifareTool": {
      "command": "python",
      "args": [
        "D:\\Workspace\\Works\\Other\\PyMifareTool\\mcp_server.py"
      ]
    }
  }
}
```

### 5.2 Antigravity IDE 配置示例

在 Antigravity 插件配置或 `.agents/plugins/pymifare-mcp/mcp_config.json` 中配置：

```json
{
  "mcpServers": {
    "pymifare": {
      "command": "python",
      "args": [
        "mcp_server.py"
      ]
    }
  }
}
```
