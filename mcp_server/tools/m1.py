"""
PyMifareTool MCP Mifare Classic 1K/4K 核心操作工具集
"""

from typing import Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
from core.models.access_bits import AccessBitsDecoder
from mcp_server.context import McpContext


def register_m1_tools(mcp: FastMCP, ctx: McpContext) -> None:
    """注册 Mifare Classic 相关的 MCP 工具"""

    @mcp.tool(
        name="authenticate_sector",
        description="""对卡片指定扇区进行密钥认证（Key A 或 Key B）。
认证成功后，硬件射频状态机将保持在此扇区的会话状态中，允许后续对该扇区内的各数据块进行读写访问。
支持通过 key_type 指定 'A' 或 'B'，支持 12 位的十六进制密钥字符串（如 'FFFFFFFFFFFF'）。"""
    )
    async def authenticate_sector(
        sector: int,
        key_type: str = "A",
        key_hex: str = "FFFFFFFFFFFF",
        uid_hex: Optional[str] = None
    ) -> Dict[str, Any]:
        kt = key_type.upper().strip()
        kt_val = 0x61 if "B" in kt else 0x60
        cleaned_key = key_hex.replace(" ", "").strip()
        if len(cleaned_key) != 12:
            return {"success": False, "message": "密钥必须是 12 个十六进制字符（6 字节）"}

        try:
            key_bytes = bytes.fromhex(cleaned_key)
        except ValueError:
            return {"success": False, "message": "密钥包含非法十六进制字符"}

        target_uid_bytes = None
        if uid_hex:
            try:
                target_uid_bytes = bytes.fromhex(uid_hex.replace(" ", "").strip())
            except ValueError:
                return {"success": False, "message": "UID 包含非法十六进制字符"}
        elif ctx.current_card_info and ctx.current_card_info.get("uid"):
            try:
                target_uid_bytes = bytes.fromhex(ctx.current_card_info["uid"])
            except Exception:
                pass

        try:
            # 若无 UID，先执行一次 poll 保证底层激活并获取当前 UID
            if not target_uid_bytes:
                p = await ctx.call_adapter("poll_card")
                if not p or not p.get("uid"):
                    return {"success": False, "message": "未找到在位卡片，无法完成认证"}
                target_uid_bytes = bytes.fromhex(p["uid"])

            block_to_auth = sector * 4 if sector < 32 else 128 + (sector - 32) * 16

            ok = await ctx.call_adapter(
                "authenticate",
                block_to_auth,
                kt_val,
                key_bytes,
                target_uid_bytes
            )

            if ok:
                ctx.known_keys.setdefault(sector, {})["A" if kt_val == 0x60 else "B"] = cleaned_key.upper()
                return {
                    "success": True,
                    "sector": sector,
                    "block": block_to_auth,
                    "key_type": "A" if kt_val == 0x60 else "B",
                    "key": cleaned_key.upper(),
                    "message": f"扇区 {sector} 认证成功！"
                }
            else:
                return {
                    "success": False,
                    "sector": sector,
                    "block": block_to_auth,
                    "key_type": "A" if kt_val == 0x60 else "B",
                    "message": f"扇区 {sector} 密钥 {'A' if kt_val == 0x60 else 'B'} 认证失败"
                }
        except Exception as e:
            return {"success": False, "message": f"认证异常: {e}"}

    @mcp.tool(
        name="read_block",
        description="""读取指定块号的 16 字节数据。
若当前尚未对该块所属扇区认证，可设置 authenticate_first=True 并提供密钥和密钥类型自动完成前置认证。"""
    )
    async def read_block(
        block: int,
        authenticate_first: bool = False,
        key_type: str = "A",
        key_hex: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            if authenticate_first and key_hex:
                sector = block // 4 if block < 128 else 32 + (block - 128) // 16
                auth_res = await authenticate_sector(sector=sector, key_type=key_type, key_hex=key_hex)
                if not auth_res.get("success"):
                    return {"success": False, "message": f"前置认证扇区 {sector} 失败"}

            data = await ctx.call_adapter("read_block", block)
            if data is None or len(data) != 16:
                return {
                    "success": False,
                    "block": block,
                    "message": f"读取块 {block} 失败（可能未认证或物理超时）"
                }

            hex_str = data.hex().upper()
            spaced = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
            ascii_repr = "".join(chr(b) if 32 <= b <= 126 else "." for b in data)

            ctx.current_dump.set_block(block, data)

            return {
                "success": True,
                "block": block,
                "data_hex": hex_str,
                "data_spaced": spaced,
                "ascii": ascii_repr
            }
        except Exception as e:
            return {"success": False, "block": block, "message": f"读取块异常: {e}"}

    @mcp.tool(
        name="write_block",
        description="""向指定数据块写入 16 字节数据。
注意：
1. 写入前卡片对应扇区必须已经过成功认证。
2. 绝对安全保护：Block 0（厂商块/物理卡号）默认严禁写入！如确实需向魔术卡写入 0 块，请使用专用 write_magic_block0 工具或显式传参 allow_block0_write=True。"""
    )
    async def write_block(
        block: int,
        data_hex: str,
        allow_block0_write: bool = False
    ) -> Dict[str, Any]:
        cleaned_data = data_hex.replace(" ", "").strip()
        if len(cleaned_data) != 32:
            return {"success": False, "message": f"数据长度必须为 16 字节（32 个十六进制字符），当前长度: {len(cleaned_data)}"}

        if block == 0 and not allow_block0_write:
            return {
                "success": False,
                "message": "安全防护拦截：普通 Mifare 卡的 Block 0 为只读硬件块，强行写入可能导致卡片报废！如确认是魔术卡请调用 write_magic_block0 工具或开启 allow_block0_write。"
            }

        try:
            payload = bytes.fromhex(cleaned_data)
        except ValueError:
            return {"success": False, "message": "写入数据包含无效的十六进制字符"}

        try:
            ok = await ctx.call_adapter("write_block", block, payload)
            if ok:
                ctx.current_dump.set_block(block, payload)
                return {
                    "success": True,
                    "block": block,
                    "data_hex": cleaned_data.upper(),
                    "message": f"块 {block} 写入成功！"
                }
            else:
                return {
                    "success": False,
                    "block": block,
                    "message": f"块 {block} 写入失败（可能未认证或卡片拒绝写入）"
                }
        except Exception as e:
            return {"success": False, "block": block, "message": f"写块异常: {e}"}

    @mcp.tool(
        name="read_sector",
        description="""完整读取指定扇区内的所有块，并解析控制字（Access Bits）与权限定义。
调用前请确保已完成认证或在参数中直接提供已知有效密钥。"""
    )
    async def read_sector(
        sector: int,
        key_type: str = "A",
        key_hex: str = "FFFFFFFFFFFF"
    ) -> Dict[str, Any]:
        auth_res = await authenticate_sector(sector=sector, key_type=key_type, key_hex=key_hex)
        if not auth_res.get("success"):
            return {
                "success": False,
                "sector": sector,
                "message": f"读取扇区前认证失败: {auth_res.get('message')}"
            }

        start_block = sector * 4 if sector < 32 else 128 + (sector - 32) * 16
        block_count = 4 if sector < 32 else 16
        blocks_data = []

        try:
            for b in range(start_block, start_block + block_count):
                d = await ctx.call_adapter("read_block", b)
                if d and len(d) == 16:
                    ctx.current_dump.set_block(b, d)
                    blocks_data.append({
                        "block": b,
                        "data_hex": d.hex().upper(),
                        "ascii": "".join(chr(x) if 32 <= x <= 126 else "." for x in d)
                    })
                else:
                    blocks_data.append({"block": b, "data_hex": None, "error": "读取失败"})
        except Exception as e:
            return {"success": False, "sector": sector, "message": f"扇区读取异常: {e}"}

        trailer_block_idx = start_block + block_count - 1
        trailer_item = next((item for item in blocks_data if item["block"] == trailer_block_idx), None)
        access_analysis = {}
        if trailer_item and trailer_item.get("data_hex"):
            try:
                t_bytes = bytes.fromhex(trailer_item["data_hex"])
                access_bytes = t_bytes[6:10]
                decoder = AccessBitsDecoder(access_bytes)
                access_analysis = {
                    "raw_access_hex": access_bytes.hex().upper(),
                    "valid": decoder.is_valid(),
                    "description": decoder.describe()
                }
            except Exception as e:
                access_analysis = {"error": f"控制字解析异常: {e}"}

        return {
            "success": True,
            "sector": sector,
            "start_block": start_block,
            "block_count": block_count,
            "blocks": blocks_data,
            "access_control": access_analysis
        }

    @mcp.tool(
        name="write_magic_block0",
        description="""针对魔术卡（UID / CUID / UFUID / GEN1A 等）改写 Block 0（厂商块/物理卡号/BCC）。
支持通过 magic_type 指定魔术卡类型：
- 'CUID': 普通指令后门卡，需先以 0 扇区密钥认证后直接写 Block 0；
- 'GEN1A': 传统后门卡，通过特殊解锁指令 (0x40/0x43) 绕过密钥强写；
- 'UFUID': 支持普通指令改写，写完后可锁死为普通卡。"""
    )
    async def write_magic_block0(
        block0_hex: str,
        magic_type: str = "CUID"
    ) -> Dict[str, Any]:
        cleaned = block0_hex.replace(" ", "").strip()
        if len(cleaned) != 32:
            return {"success": False, "message": f"Block 0 数据必须为 16 字节（32个十六进制字符），当前为 {len(cleaned)}"}

        try:
            b0_bytes = bytes.fromhex(cleaned)
        except ValueError:
            return {"success": False, "message": "数据包含非法十六进制字符"}

        mtype = magic_type.upper().strip()
        if mtype not in ("CUID", "GEN1A", "UFUID"):
            return {"success": False, "message": f"不支持的魔术卡类型: '{magic_type}'，仅支持 CUID, GEN1A, UFUID"}

        try:
            ok = await ctx.call_adapter("write_magic_block0", b0_bytes, mtype, 0.8)
            if ok:
                ctx.current_dump.set_block(0, b0_bytes)
                return {
                    "success": True,
                    "magic_type": mtype,
                    "block0_hex": cleaned.upper(),
                    "message": f"魔术卡 ({mtype}) Block 0 改写成功！新卡号将在重新寻卡后生效。"
                }
            else:
                return {
                    "success": False,
                    "magic_type": mtype,
                    "message": f"魔术卡 ({mtype}) Block 0 改写失败，请确认卡片芯片类型与摆放位置。"
                }
        except Exception as e:
            return {"success": False, "message": f"改写 Block 0 异常: {e}"}

    @mcp.tool(
        name="lock_ufuid_card",
        description="""固化锁死 UFUID 魔术卡（高危操作，绝对不可逆！）。
向卡片发送 UFUID 固化指令，使 UFUID 芯片永久关闭后门指令，彻底变为普通只读 UID 的 M1 卡，以应对门禁系统的高级魔术卡探测防复印机制。
参数 confirm 必须显式传入 True 才能执行。"""
    )
    async def lock_ufuid_card(confirm: bool = False) -> Dict[str, Any]:
        if not confirm:
            return {
                "success": False,
                "message": "安全防护拦截：UFUID 锁死为绝对不可逆的单向硬件操作，锁死后该卡将永久无法再次修改 UID！如确认锁死，请在调用参数中传入 confirm=True。"
            }

        try:
            ok = await ctx.call_adapter("lock_ufuid_card", 0.8)
            if ok:
                return {
                    "success": True,
                    "message": "UFUID 锁死成功！该卡已永久固化为普通 M1 芯片，UID 无法再次改写。"
                }
            else:
                return {
                    "success": False,
                    "message": "UFUID 锁死指令发送未成功，可能卡片并非处于可锁死状态或已锁死。"
                }
        except Exception as e:
            return {"success": False, "message": f"锁死 UFUID 异常: {e}"}
