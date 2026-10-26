"""
PyMifareTool MCP ISO/IEC 14443-4 CPU 智能卡与 APDU 工具集
"""

from typing import Dict, Any
from mcp.server.fastmcp import FastMCP
from mcp_server.context import McpContext


def register_cpu_card_tools(mcp: FastMCP, ctx: McpContext) -> None:
    """注册 CPU 智能卡与 APDU 相关的 MCP 工具"""

    @mcp.tool(
        name="send_apdu",
        description="""向当前已建立 ISO/IEC 14443-4 协议连接的 CPU 智能卡发送原生 7816 APDU 指令。
支持智能状态协商：
- 当卡片返回 61xx 状态码时，自动执行 00 C0 00 00 [xx] (GET RESPONSE) 取回完整响应体；
- 当卡片返回 6Cxx 状态码时，自动提取正确的期望返回长度 Le 并重发 APDU。
返回解析后的状态字 SW、HEX 载荷以及标准中文含义解释。"""
    )
    async def send_apdu(
        apdu_hex: str,
        auto_get_response: bool = True
    ) -> Dict[str, Any]:
        cleaned = apdu_hex.replace(" ", "").strip()
        try:
            apdu_bytes = bytes.fromhex(cleaned)
        except ValueError:
            return {"ok": False, "message": f"无效的十六进制 APDU 格式: '{apdu_hex}'"}

        if len(apdu_bytes) < 4:
            return {"ok": False, "message": f"APDU 长度至少为 4 字节 (CLA INS P1 P2)，当前为 {len(apdu_bytes)} 字节"}

        try:
            res = await ctx.call_adapter(
                "send_apdu",
                apdu_bytes,
                timeout=0.6,
                auto_get_response=auto_get_response
            )
            return res
        except Exception as e:
            return {
                "ok": False,
                "error": f"发送 APDU 发生异常: {e}",
                "sw_desc": "执行异常"
            }

    @mcp.tool(
        name="read_cpu_card_public_info",
        description="""一键读取在位 CPU 卡（如全国交通联合卡/城市公交一卡通/银联闪付金融卡等）的公开信息。
自动遍历 AID（交通联合、深圳通、岭南通、上海公共交通、北京互通、PBOC 电子现金等），
解析返回卡号、发卡机构代码、有效期、电子钱包余额以及最近多笔刷卡消费/充值交易流水。"""
    )
    async def read_cpu_card_public_info() -> Dict[str, Any]:
        try:
            res = await ctx.call_adapter("read_cpu_card_public_info", timeout=0.8)
            # 过滤 logs 以免 token 占用过大，仅保留前 10 条日志
            logs = res.get("logs", [])
            truncated_logs = logs[:10]
            clean_res = dict(res)
            clean_res["logs"] = truncated_logs
            clean_res["logs_total"] = len(logs)
            return clean_res
        except Exception as e:
            return {
                "error": f"读取 CPU 卡公开信息异常: {e}",
                "app_name": "未知应用",
                "card_number": "-",
                "balance_str": "--",
                "transactions": []
            }

    @mcp.tool(
        name="scan_cpu_card_filesystem",
        description="""遍历并探测 CPU 卡内的标准目录与文件结构 (DF / EF)。
依次探测常见 Master File (MF 3F00)、Dedicated File (DF 1001, 2001, PSE, PPSE) 以及基本文件 (EF 0015, 0016, 0018 等)，生成文件树。"""
    )
    async def scan_cpu_card_filesystem(max_depth: int = 2) -> Dict[str, Any]:
        try:
            if hasattr(ctx.get_adapter(), "scan_cpu_card_tree"):
                res = await ctx.call_adapter("scan_cpu_card_tree", max_depth=max_depth)
                return {"success": True, "tree": res}
            else:
                return {"success": False, "message": "当前读卡器适配器未实现 CPU 卡文件树扫描"}
        except Exception as e:
            return {"success": False, "message": f"扫描 CPU 卡文件结构异常: {e}"}
