"""
PyMifareTool MCP M1 卡 Dump 内存镜像与文件管理工具集
"""

import os
from typing import Dict, Any
import asyncio
from mcp.server.fastmcp import FastMCP
from core.models.dump import MifareDump, BlockState
from core.models.access_bits import AccessBitsDecoder
from mcp_server.context import McpContext


def register_dump_tools(mcp: FastMCP, ctx: McpContext) -> None:
    """注册 M1 Dump 文件与内存镜像相关的 MCP 工具"""

    @mcp.tool(
        name="load_dump_file",
        description="""从本地文件系统中载入 Mifare Classic 卡片 Dump 文件至当前会话内存。
支持格式：.dump, .mfd, .bin (二进制), .mct (MCT文本), .eml (Proxmark3/行文本), .json (带元数据结构), .txt。
自动识别 1K (S50, 16扇区) 或 4K (S70, 40扇区) 卡型。"""
    )
    async def load_dump_file(filepath: str) -> Dict[str, Any]:
        abs_path = os.path.abspath(filepath)
        if not os.path.exists(abs_path):
            return {"success": False, "message": f"文件不存在: {abs_path}"}

        dump = MifareDump()
        ok = await asyncio.to_thread(dump.load_from_file, abs_path)
        if not ok:
            return {
                "success": False,
                "message": f"载入 Dump 文件失败: {dump.load_error_message or '文件格式解析错误'}"
            }

        ctx.current_dump = dump
        read_ok_count = sum(1 for s in dump.block_states if s == BlockState.READ_OK)
        return {
            "success": True,
            "filepath": abs_path,
            "is_4k": dump.is_4k,
            "sector_count": dump.sector_count,
            "block_count": dump.block_count,
            "valid_blocks": read_ok_count,
            "uid": dump.get_uid().hex().upper() if dump.get_uid() else "",
            "message": f"成功载入 Dump 文件 ({'4K' if dump.is_4k else '1K'}, {read_ok_count}/{dump.block_count} 块有效)"
        }

    @mcp.tool(
        name="save_dump_file",
        description="""将当前内存会话中的 Dump 数据导出并保存至本地文件。
支持导出扩展名：.dump / .bin (二进制), .mct (MCT 纯文本格式), .eml (每行一块), .json (JSON 结构化格式), .txt。"""
    )
    async def save_dump_file(filepath: str) -> Dict[str, Any]:
        abs_path = os.path.abspath(filepath)
        dump = ctx.current_dump

        dir_name = os.path.dirname(abs_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        ok = await asyncio.to_thread(dump.save_to_file, abs_path)
        if ok:
            return {
                "success": True,
                "filepath": abs_path,
                "file_size": os.path.getsize(abs_path) if os.path.exists(abs_path) else 0,
                "message": f"成功保存 Dump 数据至 {abs_path}"
            }
        else:
            return {"success": False, "message": f"保存 Dump 失败，请检查路径权限与格式后缀"}

    @mcp.tool(
        name="get_dump_summary",
        description="""获取当前会话内存中 Dump 的全景摘要统计。
包含：1K/4K 芯片规格、总扇区数、总块数、已读成功块数、失败/未读块数、UID 以及各扇区已知 Key A/Key B 概览。"""
    )
    async def get_dump_summary() -> Dict[str, Any]:
        dump = ctx.current_dump
        read_ok = sum(1 for s in dump.block_states if s == BlockState.READ_OK)
        read_failed = sum(1 for s in dump.block_states if s == BlockState.READ_FAILED)
        unread = sum(1 for s in dump.block_states if s == BlockState.UNREAD)

        sectors_overview = []
        for s in range(dump.sector_count):
            info = dump.get_sector_info(s)
            t_block = dump.get_sector_trailer_block(s)
            trailer_bytes = dump.get_block(t_block)
            key_a = trailer_bytes[:6].hex().upper() if trailer_bytes else ""
            key_b = trailer_bytes[10:16].hex().upper() if trailer_bytes else ""
            sectors_overview.append({
                "sector": s,
                "blocks": f"{dump.get_sector_first_block(s)}..{t_block}",
                "key_a": key_a,
                "key_b": key_b
            })

        return {
            "is_4k": dump.is_4k,
            "sector_count": dump.sector_count,
            "block_count": dump.block_count,
            "stats": {
                "read_ok": read_ok,
                "read_failed": read_failed,
                "unread": unread
            },
            "uid": dump.get_uid().hex().upper() if dump.get_uid() else "",
            "sectors": sectors_overview
        }

    @mcp.tool(
        name="verify_and_repair_dump",
        description="""对当前内存中的 Dump 进行结构合法性验证与修复。
检测项目包括：Block 0 的 UID 与 BCC 校验字节异或匹配、扇区尾块控制字 (Access Bits) 补码逻辑合法性。
可选开启 repair=True 自动修复损坏的 BCC 校验位与异常控制字。"""
    )
    async def verify_and_repair_dump(repair: bool = False) -> Dict[str, Any]:
        dump = ctx.current_dump
        issues = []

        # 1. 校验 Block 0 BCC
        b0 = dump.get_block(0)
        if b0 and len(b0) == 16:
            uid4 = b0[:4]
            bcc = b0[4]
            calc_bcc = uid4[0] ^ uid4[1] ^ uid4[2] ^ uid4[3]
            if bcc != calc_bcc:
                issues.append({
                    "type": "BCC_MISMATCH",
                    "detail": f"Block 0 BCC 校验失败: 实际 0x{bcc:02X}, 计算值 0x{calc_bcc:02X}"
                })
                if repair:
                    b0[4] = calc_bcc
                    dump.set_block(0, bytes(b0))

        # 2. 校验各扇区控制字
        for s in range(dump.sector_count):
            t_idx = dump.get_sector_trailer_block(s)
            t_data = dump.get_block(t_idx)
            if t_data and len(t_data) == 16:
                access_bytes = t_data[6:10]
                decoder = AccessBitsDecoder(access_bytes)
                if not decoder.is_valid():
                    issues.append({
                        "type": "INVALID_ACCESS_BITS",
                        "sector": s,
                        "trailer_block": t_idx,
                        "detail": f"扇区 {s} 控制字非法: {access_bytes.hex().upper()}"
                    })
                    if repair:
                        # 修复为标准出厂默认值 FF 07 80 69
                        fixed = bytearray(t_data)
                        fixed[6:10] = bytes([0xFF, 0x07, 0x80, 0x69])
                        dump.set_block(t_idx, bytes(fixed))

        return {
            "success": True,
            "repaired": repair,
            "issue_count": len(issues),
            "issues": issues,
            "message": "Dump 结构验证完毕" + (f"，已自动修复 {len(issues)} 处异常" if repair and issues else "")
        }

    @mcp.tool(
        name="compare_dumps",
        description="""对比两个外部 Dump 文件之间的扇区与块级数据差异。
输出发生变化的块号、原数据 vs 新数据十六进制对比。"""
    )
    async def compare_dumps(dump_a_path: str, dump_b_path: str) -> Dict[str, Any]:
        path_a = os.path.abspath(dump_a_path)
        path_b = os.path.abspath(dump_b_path)

        if not os.path.exists(path_a):
            return {"success": False, "message": f"文件 A 不存在: {path_a}"}
        if not os.path.exists(path_b):
            return {"success": False, "message": f"文件 B 不存在: {path_b}"}

        dump_a = MifareDump()
        dump_b = MifareDump()

        ok_a = await asyncio.to_thread(dump_a.load_from_file, path_a)
        ok_b = await asyncio.to_thread(dump_b.load_from_file, path_b)

        if not ok_a or not ok_b:
            return {"success": False, "message": "读取或解析对比文件失败"}

        diff_blocks = []
        max_blocks = max(dump_a.block_count, dump_b.block_count)
        for b in range(max_blocks):
            d_a = dump_a.get_block(b) if b < dump_a.block_count else b""
            d_b = dump_b.get_block(b) if b < dump_b.block_count else b""
            if d_a != d_b:
                diff_blocks.append({
                    "block": b,
                    "sector": b // 4 if b < 128 else 32 + (b - 128) // 16,
                    "dump_a": d_a.hex().upper() if d_a else "",
                    "dump_b": d_b.hex().upper() if d_b else ""
                })

        return {
            "success": True,
            "dump_a_path": path_a,
            "dump_b_path": path_b,
            "total_differences": len(diff_blocks),
            "differences": diff_blocks
        }
