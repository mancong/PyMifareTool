"""
PyMifareTool MCP 密钥字典与密码恢复工具集
"""

from typing import Dict, Any, Optional, List
import asyncio
from mcp.server.fastmcp import FastMCP
from core.services.key_manager import KeyManager
from mcp_server.context import McpContext


def register_cracking_tools(mcp: FastMCP, ctx: McpContext) -> None:
    """注册密钥字典管理与 M1 密码恢复相关的 MCP 工具"""

    @mcp.tool(
        name="list_key_dictionaries",
        description="""查询并列出当前工作区 keys/ 目录下所有可用的 M1 密钥字典文件。
返回每个字典的文件名、标题、描述、包含密钥数量以及是否为默认启用字典。"""
    )
    async def list_key_dictionaries() -> Dict[str, Any]:
        files_info = await asyncio.to_thread(KeyManager.list_available_files)
        return {
            "success": True,
            "keys_directory": KeyManager.get_keys_dir(),
            "count": len(files_info),
            "dictionaries": files_info
        }

    @mcp.tool(
        name="parse_key_dictionary_file",
        description="""解析指定字典文件并提取其中的 12 字符十六进制有效密钥。
可指定 keys/ 目录下的字典文件名（例如 'std.keys', 'hotel-std.keys', 'custom.keys'）。"""
    )
    async def parse_key_dictionary_file(filename: str) -> Dict[str, Any]:
        keys_dir = KeyManager.get_keys_dir()
        import os
        full_path = os.path.join(keys_dir, filename)
        if not os.path.exists(full_path):
            return {
                "success": False,
                "message": f"字典文件不存在: {filename}"
            }

        keys = await asyncio.to_thread(KeyManager.parse_key_file, full_path)
        return {
            "success": True,
            "filename": filename,
            "key_count": len(keys),
            "keys_sample": keys[:50],  # 避免过多输出导致 context 臃肿
            "truncated": len(keys) > 50
        }

    @mcp.tool(
        name="save_custom_keys",
        description="""向用户自定义密钥字典 (custom.keys) 中追加或批量保存新的 12 位十六进制密钥。
支持自动去重与格式校验。"""
    )
    async def save_custom_keys(keys: List[str]) -> Dict[str, Any]:
        saved_count = await asyncio.to_thread(KeyManager.save_custom_keys, keys)
        return {
            "success": True,
            "saved_count": saved_count,
            "message": f"成功保存 {saved_count} 个有效密钥至 custom.keys"
        }

    @mcp.tool(
        name="get_card_known_keys",
        description="""从本地 SQLite 数据库中查询目标卡片历史上已恢复或保存的所有扇区已知密钥（Key A 和 Key B）。
如果未显式提供 uid，将默认使用当前射频感应区活跃卡片。"""
    )
    async def get_card_known_keys(uid: Optional[str] = None) -> Dict[str, Any]:
        target_uid = uid
        if not target_uid and ctx.current_card_info:
            target_uid = ctx.current_card_info.get("uid")

        if not target_uid:
            return {
                "success": False,
                "message": "请提供目标卡片 UID 或确保感应区有已寻到的活跃卡片"
            }

        cleaned_uid = target_uid.replace(" ", "").upper()
        db = ctx.get_db()
        keys_map = await asyncio.to_thread(db.get_card_keys, cleaned_uid)
        return {
            "success": True,
            "uid": cleaned_uid,
            "cracked_sectors_count": len(keys_map),
            "keys": keys_map
        }

    @mcp.tool(
        name="crack_card_keys",
        description="""针对在位卡片执行高阶字典密钥恢复与暴力破解。
参数说明：
- start_sector: 起始扇区（默认 0）
- end_sector: 结束扇区（默认 15，对 1K 卡为 0~15，对 4K 卡最大为 39）
- dictionary_files: 可选的字典文件名列表，默认采用 ['std.keys', 'hotel-std.keys']
- crack_mode: 破解模式，支持 'fast'（任一 Key 命中即过）、'both'（同时尝试恢复 Key A 和 Key B）、'a'（仅 Key A）、'b'（仅 Key B）
恢复出的有效密钥将自动归档至本地 SQLite 数据库中。"""
    )
    async def crack_card_keys(
        start_sector: int = 0,
        end_sector: int = 15,
        dictionary_files: Optional[List[str]] = None,
        crack_mode: str = "fast"
    ) -> Dict[str, Any]:
        try:
            card = await ctx.call_adapter("poll_card")
        except Exception as e:
            return {"success": False, "message": f"连接或寻卡异常: {e}"}

        if not card or not card.get("uid"):
            return {"success": False, "message": "射频区未找到在位卡片，无法执行破解"}

        uid_hex = card["uid"].upper()
        uid_bytes = bytes.fromhex(uid_hex)

        # 加载字典
        dict_files = dictionary_files or ["std.keys", "hotel-std.keys"]
        keys_to_test = await asyncio.to_thread(
            KeyManager.load_combined_keys,
            selected_files=dict_files,
            include_defaults_fallback=True
        )

        # 插入 DB 中已知密钥作为最前置最高优先级的试探密钥
        db = ctx.get_db()
        db_known = await asyncio.to_thread(db.get_card_keys, uid_hex)
        prioritized_keys = []
        for sec_data in db_known.values():
            if isinstance(sec_data, dict):
                ka = sec_data.get("key_a")
                kb = sec_data.get("key_b")
                if ka and ka not in prioritized_keys:
                    prioritized_keys.append(ka)
                if kb and kb not in prioritized_keys:
                    prioritized_keys.append(kb)

        for k in keys_to_test:
            if k not in prioritized_keys:
                prioritized_keys.append(k)

        mode = crack_mode.lower()
        results = {}
        total_cracked = 0

        # 逐扇区扫描
        for sector in range(start_sector, end_sector + 1):
            block = sector * 4 if sector < 32 else 128 + (sector - 32) * 16
            sector_result = {"key_a": None, "key_b": None}

            need_a = mode in ("fast", "both", "a")
            need_b = mode in ("both", "b")

            for key_str in prioritized_keys:
                k_bytes = bytes.fromhex(key_str)

                # 尝试 Key A
                if need_a and not sector_result["key_a"]:
                    try:
                        ok_a = await ctx.call_adapter("authenticate", block, 0x60, k_bytes, uid_bytes)
                        if ok_a:
                            sector_result["key_a"] = key_str
                            if mode == "fast":
                                break
                    except Exception:
                        pass

                # 尝试 Key B
                if need_b and not sector_result["key_b"]:
                    try:
                        ok_b = await ctx.call_adapter("authenticate", block, 0x61, k_bytes, uid_bytes)
                        if ok_b:
                            sector_result["key_b"] = key_str
                            if mode == "fast":
                                break
                    except Exception:
                        pass

                if (not need_a or sector_result["key_a"]) and (not need_b or sector_result["key_b"]):
                    break

                if sector_result["key_a"] or sector_result["key_b"]:
                    total_cracked += 1
                    # 存入数据库
                    await asyncio.to_thread(
                        db.save_sector_keys,
                        uid_hex,
                        sector,
                        sector_result["key_a"],
                        sector_result["key_b"]
                    )
                    ctx.known_keys[sector] = {
                        k: v for k, v in [("A", sector_result["key_a"]), ("B", sector_result["key_b"])] if v
                    }

                results[sector] = sector_result

            return {
                "success": True,
                "uid": uid_hex,
                "sectors_scanned": end_sector - start_sector + 1,
                "sectors_cracked": total_cracked,
                "results": results,
                "message": f"完成扫描 {end_sector - start_sector + 1} 个扇区，成功恢复 {total_cracked} 个扇区密码"
            }
