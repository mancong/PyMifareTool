# -*- coding: utf-8 -*-
"""
PyMifareTool - ISO/IEC 7816-4 APDU 协议与 CPU 智能卡解析中枢
纯无状态编解码层，提供：
1. 标准 APDU 构造、校验与拆包
2. SW1/SW2 状态字全网标准释义字典
3. PBOC (中国金融集成电路卡) / 交通联合 (T-Union) / 城市公交卡公共信息与交易流水解析
"""

from typing import Dict, Any, List, Optional, Tuple

# 常用标准应用标识符 AID (Application Identifier)
AID_PPSE = bytes.fromhex("325041592E5359532E4444463031")        # 非接触式支付系统目录 2PAY.SYS.DDF01 (PPSE)
AID_MOT_T_EP = bytes.fromhex("A000000632010105535A4B5700000531")  # 交通运输部全国交通联合专用应用 (MOT_T_EP)
AID_T_UNION = bytes.fromhex("A000000333010101")                   # 交通运输部旧版全国交通一卡通 (互联互通)
AID_PBOC_CASH = bytes.fromhex("A00000000386980701")               # PBOC 电子现金 / 电子钱包应用
AID_PBOC_DEBIT = bytes.fromhex("A0000000031010")                  # PBOC 借记应用
AID_PBOC_CREDIT = bytes.fromhex("A0000000032010")                 # PBOC 贷记应用
AID_CITY_UNION = bytes.fromhex("A00000000386980701")              # 住建部城市互联互通

# 中国主流银行 BIN 码前缀映射字典 (用于从卡号智能推导发卡行与卡种)
BANK_BIN_MAP: Dict[str, str] = {
    # 招商银行 (CMB)
    "621483": "招商银行 (一卡通 IC 普卡)",
    "621485": "招商银行 (一卡通 IC 金卡)",
    "621486": "招商银行 (一卡通 金葵花卡)",
    "621488": "招商银行 (一卡通借记卡)",
    "622588": "招商银行 (一卡通)",
    "622580": "招商银行 (一卡通)",
    "622575": "招商银行",
    "622576": "招商银行",
    "622577": "招商银行",
    "622578": "招商银行",
    "622579": "招商银行",
    "621286": "招商银行",
    # 中国工商银行 (ICBC)
    "622202": "中国工商银行 (牡丹借记卡)",
    "622200": "中国工商银行",
    "622208": "中国工商银行",
    "621225": "中国工商银行",
    "621226": "中国工商银行",
    # 中国农业银行 (ABC)
    "622848": "中国农业银行 (金穗借记卡)",
    "622846": "中国农业银行",
    "622845": "中国农业银行",
    "622841": "中国农业银行",
    # 中国建设银行 (CCB)
    "622700": "中国建设银行 (龙卡借记卡)",
    "621700": "中国建设银行",
    "621722": "中国建设银行",
    "621723": "中国建设银行",
    # 中国银行 (BOC)
    "622908": "中国银行 (长城借记卡)",
    "621661": "中国银行",
    "621662": "中国银行",
    # 交通银行 (BOCOM)
    "622262": "交通银行 (太平洋借记卡)",
    "622260": "交通银行",
    # 中国邮政储蓄银行 (PSBC)
    "622188": "中国邮政储蓄银行 (邮储绿卡)",
    "622150": "中国邮政储蓄银行",
    "622151": "中国邮政储蓄银行",
    "621798": "中国邮政储蓄银行",
    "621799": "中国邮政储蓄银行",
    "621797": "中国邮政储蓄银行",
    "621098": "中国邮政储蓄银行",
    # 主流股份制商业银行
    "622609": "中国民生银行",
    "622615": "中信银行",
    "622622": "中国光大银行",
    "622630": "华夏银行",
    "622660": "广发银行",
    "622670": "平安银行",
    "622680": "上海浦东发展银行",
    "622988": "北京银行",
    "622998": "上海银行",
    # 基础银联兜底
    "6214": "招商银行 / 银联一卡通借记卡",
    "62": "中国银联标准卡 (China UnionPay)",
}

# ISO/IEC 7816-4 标准状态字 (SW1 SW2) 释义字典
COMMON_EF_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "0001": {"name": "应用主账号/磁道文件", "type": "record", "sfi": 0x01, "desc": "PBOC 磁道 2 等效数据与主账号"},
    "0002": {"name": "应用基本数据/卡号文件", "type": "record", "sfi": 0x02, "desc": "PBOC 主账号、卡片有效期与发行参数"},
    "0003": {"name": "风险管理控制参数文件", "type": "record", "sfi": 0x03, "desc": "PBOC CDOL1/CDOL2 风险管理数据"},
    "000B": {"name": "PBOC 金融交易明细记录", "type": "record", "sfi": 0x0B, "desc": "中国金融集成电路卡循环交易日志文件 (PBOC标准)"},
    "0015": {"name": "公共信息基本文件", "type": "binary", "sfi": 0x15, "desc": "发卡机构代码、卡面卡号、启用日期与有效期"},
    "0005": {"name": "持卡人扩展信息文件", "type": "binary", "sfi": 0x05, "desc": "持卡人个人公开档案、证件类型与身份标记"},
    "0012": {"name": "互联互通控制参数", "type": "binary", "sfi": 0x12, "desc": "全国交通互联互通跨区路网与行业控制字"},
    "0014": {"name": "复合消费扩展文件", "type": "binary", "sfi": 0x14, "desc": "异地刷卡进出站与换乘复合消费数据"},
    "0016": {"name": "脱机累计金额文件", "type": "binary", "sfi": 0x16, "desc": "脱机连续消费累计金额与安全门限"},
    "0017": {"name": "联机充值交易记录", "type": "record", "sfi": 0x17, "desc": "充值/圈存交易历史明细"},
    "0018": {"name": "电子钱包消费记录", "type": "record", "sfi": 0x18, "desc": "脱机消费循环流水明细 (PBOC/T-Union标准)"},
    "0019": {"name": "复合消费记录文件", "type": "record", "sfi": 0x19, "desc": "轨道交通/长途客运进出站行程记录"},
    "001A": {"name": "进站状态标记文件", "type": "binary", "sfi": 0x1A, "desc": "当前进站状态、站点编码与车次标记"},
}

SW_DESCRIPTIONS: Dict[int, str] = {
    0x9000: "操作成功 (Normal execution)",
    0x6100: "成功，后续尚有数据可读 (使用 GET RESPONSE 获取)",
    0x6200: "警告: 状态未改变",
    0x6281: "警告: 返回数据可能有错",
    0x6282: "警告: 读到文件末尾之前，文件长度小于 Le",
    0x6283: "警告: 选中的文件无效/失效",
    0x6300: "警告: 认证失败",
    0x6400: "执行错误: 状态标志未改变",
    0x6581: "内存故障 / 写入 EEPROM 错误",
    0x6700: "指令长度错误 (Wrong length)",
    0x6800: "不支持的功能",
    0x6900: "命令不能执行",
    0x6981: "命令与文件结构不兼容",
    0x6982: "安全状态不满足 (需要 PIN 码或外部认证密钥)",
    0x6983: "认证方法锁定 / 密码尝试次数超限",
    0x6984: "引用数据无效",
    0x6985: "使用条件不满足",
    0x6986: "不满足无当前 EF 文件的条件",
    0x6988: "安全报文数据项不正确",
    0x6A80: "数据域参数不正确",
    0x6A81: "不支持该功能",
    0x6A82: "文件或应用未找到 (File/Application not found)",
    0x6A83: "记录未找到 (Record not found)",
    0x6A84: "文件没有足够的空间",
    0x6A86: "参数 P1 P2 不正确",
    0x6A88: "引用数据 (数据对象) 未找到",
    0x6B00: "参数 P1 P2 偏移量超出文件范围",
    0x6C00: "Le 长度错误 (SW2 提示正确的期望长度)",
    0x6D00: "不支持该指令代码 (INS 不支持)",
    0x6E00: "不支持该类别 (CLA 错误)",
    0x6F00: "未知的内部系统错误",
}


class APDUProtocol:
    """ISO/IEC 7816-4 APDU 协议编解码与解析器 (无状态纯函数)"""

    @staticmethod
    def get_sw_description(sw1: int, sw2: int) -> str:
        """根据 SW1 SW2 状态字返回中文释义"""
        sw = ((sw1 & 0xFF) << 8) | (sw2 & 0xFF)
        if sw in SW_DESCRIPTIONS:
            return SW_DESCRIPTIONS[sw]
        if sw1 == 0x61:
            return f"操作成功，有 {sw2} 字节数据等待读取 (可用 00 C0 00 00 {sw2:02X} 取回)"
        if sw1 == 0x6C:
            return f"Le 长度错误，正确的响应长度为 0x{sw2:02X} ({sw2} 字节)"
        if (sw & 0xFFF0) == 0x63C0:
            remaining = sw & 0x0F
            return f"认证失败，PIN/密码尚余 {remaining} 次重试机会"
        return f"未知状态码 (0x{sw:04X})"

    @staticmethod
    def build_select_apdu(aid_or_fid: bytes, by_name: bool = True) -> bytes:
        """
        构建 SELECT FILE / APPLICATION 指令
        by_name=True: 按应用名称/AID 选择 (00 A4 04 00 Lc [AID])
        by_name=False: 按文件标识符 FID 选择 (00 A4 00 00 02 [FID])
        """
        if by_name:
            # CLA=00, INS=A4, P1=04 (Select by DF name), P2=00 (First or only occurrence)
            return bytes([0x00, 0xA4, 0x04, 0x00, len(aid_or_fid)]) + aid_or_fid
        else:
            # CLA=00, INS=A4, P1=00 (Select by FID), P2=00
            return bytes([0x00, 0xA4, 0x00, 0x00, len(aid_or_fid)]) + aid_or_fid

    @staticmethod
    def build_read_binary_apdu(sfi: Optional[int] = None, offset: int = 0, length: int = 0) -> bytes:
        """
        构建 READ BINARY 指令 (读取透明定长二进制文件)
        sfi: 5-bit 短文件标识符 (若提供，P1 最高位为 1)
        offset: 文件内字节偏移量
        length: 读取字节数 (0 表示读取 256 字节)
        """
        if sfi is not None:
            p1 = 0x80 | (sfi & 0x1F)
            p2 = offset & 0xFF
        else:
            p1 = (offset >> 8) & 0xFF
            p2 = offset & 0xFF
        return bytes([0x00, 0xB0, p1, p2, length & 0xFF])

    @staticmethod
    def build_read_record_apdu(record_num: int, sfi: int, mode: int = 0x04) -> bytes:
        """
        构建 READ RECORD 指令 (读取定长/循环记录文件，如流水明细)
        record_num: 记录号 (1~255)
        sfi: 短文件标识符 (例如交易明细文件通常为 0x18，sfi=24，P2 = (sfi << 3) | mode)
        """
        p1 = record_num & 0xFF
        p2 = ((sfi & 0x1F) << 3) | (mode & 0x07)
        return bytes([0x00, 0xB2, p1, p2, 0x00])

    @staticmethod
    def build_get_balance_apdu(cash_type: int = 0x00) -> bytes:
        """
        构建电子现金/电子钱包 GET BALANCE 余额查询指令
        P1=00, P2=02 (电子钱包余额，PBOC/交通一卡通规范: 80 5C 00 02 04)
        """
        return bytes([0x80, 0x5C, cash_type & 0xFF, 0x02, 0x04])

    @staticmethod
    def build_get_challenge_apdu(length: int = 8) -> bytes:
        """构建取随机数指令 (Get Challenge: 00 84 00 00 Le)"""
        return bytes([0x00, 0x84, 0x00, 0x00, length & 0xFF])

    @staticmethod
    def build_get_response_apdu(le: int = 0) -> bytes:
        """构建 ISO 7816-4 GET RESPONSE 指令 (00 C0 00 00 Le)，用于取回 61xx 暂存数据"""
        return bytes([0x00, 0xC0, 0x00, 0x00, le & 0xFF])

    @staticmethod
    def parse_balance(data: bytes) -> Optional[float]:
        """
        解析 GET BALANCE 返回的 4 字节大端整数余额 (单位: 分)
        返回: 元 (浮点数)
        """
        if len(data) >= 4:
            cents = int.from_bytes(data[:4], byteorder="big", signed=True)
            return round(cents / 100.0, 2)
        return None

    @staticmethod
    def parse_ppse_response(fci_bytes: bytes) -> Optional[Dict[str, Any]]:
        """
        从 2PAY.SYS.DDF01 (PPSE) 应答报文中提取目标卡片支持的所有应用 (Tag 0x4F / Tag 0x50)
        并智能优选全国互联互通电子钱包应用 (MOT_T_EP)
        """
        if not fci_bytes or len(fci_bytes) < 6:
            return None

        entries = []
        idx = 0
        n = len(fci_bytes)

        while True:
            pos = fci_bytes.find(b"\x4F", idx)
            if pos == -1 or pos + 1 >= n:
                break
            l = fci_bytes[pos + 1]
            if 5 <= l <= 16 and pos + 2 + l <= n:
                aid = fci_bytes[pos + 2 : pos + 2 + l]
                # 寻找紧随其后的 Tag 50 (Application Label)
                label = ""
                pos50 = fci_bytes.find(b"\x50", pos + 2 + l)
                if pos50 != -1 and pos50 - (pos + 2 + l) <= 6:
                    l50 = fci_bytes[pos50 + 1]
                    if pos50 + 2 + l50 <= n:
                        label = fci_bytes[pos50 + 2 : pos50 + 2 + l50].decode("ascii", errors="ignore")
                entries.append({
                    "aid": aid,
                    "aid_hex": aid.hex().upper(),
                    "label": label or "全国交通联合 (MOT_T_EP)",
                })
                idx = pos + 2 + l
            else:
                idx = pos + 1

        if not entries:
            return None

        # 智能优选:
        # 1. 优先选择 label 包含 MOT_T_EP 或 AID 前缀为 A000000632010105 的全国交通联合互通电子钱包应用
        best_entry = None
        for e in entries:
            aid_h = e["aid_hex"]
            lbl = e.get("label", "").upper()
            if "MOT_T_EP" in lbl or aid_h.startswith("A000000632010105"):
                best_entry = e
                break

        if not best_entry:
            best_entry = entries[0]

        lbl = best_entry.get("label")
        if not lbl:
            aid_h = best_entry.get("aid_hex", "")
            if aid_h.startswith("A0000000031010"):
                lbl = "中国金融 PBOC 借记卡"
            elif aid_h.startswith("A0000000032010"):
                lbl = "中国金融 PBOC 贷记卡"
            elif aid_h.startswith("A00000000386980701"):
                lbl = "中国金融 PBOC 电子现金"
            elif aid_h.startswith("A000000632"):
                lbl = "全国交通联合 (MOT_T_EP)"
            else:
                lbl = "全国交通联合 (MOT_T_EP)"

        return {
            "aid": best_entry["aid"],
            "aid_hex": best_entry["aid_hex"],
            "label": lbl,
            "app_name": lbl,
            "entries": entries,
        }

    @staticmethod
    def parse_t_union_card_info(data: bytes) -> Dict[str, Any]:
        """
        解析交通部全国交通一卡通 (T-Union) / PBOC 0x15 公共信息文件 (00 B0 95 00 1E)
        返回: 发卡机构代码、卡号、启用日期、有效日期等
        """
        res: Dict[str, Any] = {
            "issuer_code": "",
            "card_number": "",
            "start_date": "",
            "end_date": "",
            "raw_hex": data.hex().upper(),
        }
        if len(data) < 20:
            return res

        try:
            # 字节 0~7: 发卡机构代码 (8 字节 BCD)
            issuer_raw = data[0:8].hex().upper()
            res["issuer_code"] = issuer_raw.rstrip("F")

            # 字节 10~19: 应用卡号 (10 字节 20 位 BCD 码)
            card_no_raw = data[10:20].hex().upper()
            # 清洗尾部 F 填充 (如 1234567890123456FFFF -> 1234567890123456)
            card_no_clean = card_no_raw.rstrip("F")
            # 交通卡标准: 19 位卡号首位若为 0 且清洗后长度为 20，去掉前导 0
            if card_no_clean.startswith("0") and len(card_no_clean) == 20:
                card_no_clean = card_no_clean[1:]
            res["card_number"] = card_no_clean

            # 字节 20~23: 启用日期 (YYYYMMDD, 4 字节 BCD)
            if len(data) >= 24:
                d_str = data[20:24].hex().upper()
                if len(d_str) == 8 and d_str.isdigit() and d_str not in ("00000000", "FFFFFFFF"):
                    res["start_date"] = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
                elif d_str.isdigit() and d_str not in ("00000000", "FFFFFFFF"):
                    res["start_date"] = d_str

            # 字节 24~27: 有效截止日期 (YYYYMMDD, 4 字节 BCD)
            if len(data) >= 28:
                d_str = data[24:28].hex().upper()
                if len(d_str) == 8 and d_str.isdigit() and d_str not in ("00000000", "FFFFFFFF"):
                    res["end_date"] = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}"
                elif d_str.isdigit() and d_str not in ("00000000", "FFFFFFFF"):
                    res["end_date"] = d_str
        except Exception:
            pass

        return res

    @staticmethod
    def parse_tlv(data: bytes) -> Dict[str, bytes]:
        """
        解析标准 BER-TLV 二进制报文，提取所有顶层与嵌套 TLV 标签
        返回: 标签十六进制字符串 (大写) -> 对应原始数据字节
        例如: {'5A': b'...', '5F24': b'...', '5F25': b'...', '57': b'...', '4F': b'...'}
        """
        res: Dict[str, bytes] = {}
        idx = 0
        n = len(data)
        while idx < n:
            b = data[idx]
            idx += 1
            if b in (0x00, 0xFF):
                continue

            tag = b
            if (tag & 0x1F) == 0x1F:
                tag_bytes = [tag]
                while idx < n:
                    b2 = data[idx]
                    idx += 1
                    tag_bytes.append(b2)
                    if not (b2 & 0x80):
                        break
                tag_int = 0
                for tb in tag_bytes:
                    tag_int = (tag_int << 8) | tb
            else:
                tag_int = tag

            if idx >= n:
                break

            len_byte = data[idx]
            idx += 1
            if len_byte & 0x80:
                num_len_bytes = len_byte & 0x7F
                if idx + num_len_bytes > n:
                    break
                length = int.from_bytes(data[idx:idx + num_len_bytes], "big")
                idx += num_len_bytes
            else:
                length = len_byte

            if idx + length > n:
                break

            val = data[idx:idx + length]
            idx += length
            tag_hex = f"{tag_int:X}".upper()
            res[tag_hex] = val

            # 递归解析复合标签 (Constructed) 或常见 EMV 容器模板
            if (tag_int & 0x20) or tag_hex in ("70", "77", "6F", "A5", "BF0C", "E1", "E2"):
                try:
                    sub_tlvs = APDUProtocol.parse_tlv(val)
                    res.update(sub_tlvs)
                except Exception:
                    pass
        return res

    @classmethod
    def get_bank_name_by_bin(cls, pan: str) -> str:
        """根据卡号前缀 (BIN 号) 智能推导发卡银行与卡种描述"""
        if not pan:
            return "中国银联标准卡"
        clean_pan = pan.replace(" ", "").strip()
        for length in (6, 4, 2):
            if len(clean_pan) >= length:
                prefix = clean_pan[:length]
                if prefix in BANK_BIN_MAP:
                    return BANK_BIN_MAP[prefix]
        if clean_pan.startswith("62"):
            return "中国银联标准卡 (China UnionPay)"
        return "银联金融借记卡"

    @classmethod
    def parse_pboc_card_info(cls, tlvs_or_bytes: Any) -> Dict[str, Any]:
        """
        从 PBOC / EMV 金融卡 TLV 字典或原始字节解析卡片核心公开信息
        支持提取：
        - 卡号 (PAN): Tag 5A 或 Tag 57 (磁道 2 等效数据)
        - 有效期截止: Tag 5F24 (YYMMDD) 或 Tag 57
        - 启用日期: Tag 5F25 (YYMMDD)
        - 发卡行代码/名称: 根据 PAN 前缀或 Tag 42 / 5F28 推导
        """
        res: Dict[str, Any] = {
            "card_number": "",
            "start_date": "",
            "end_date": "",
            "issuer_code": "",
            "issuer_name": "",
        }
        if not tlvs_or_bytes:
            return res

        tlvs = tlvs_or_bytes if isinstance(tlvs_or_bytes, dict) else cls.parse_tlv(tlvs_or_bytes)

        # 1. 优先从 Tag 5A (Application PAN) 获取主账号卡号
        if "5A" in tlvs:
            pan_hex = tlvs["5A"].hex().upper().rstrip("F")
            res["card_number"] = pan_hex

        # 2. 若无 Tag 5A，尝试从 Tag 57 (Track 2 Equivalent Data) 获取
        if not res["card_number"] and "57" in tlvs:
            t2_hex = tlvs["57"].hex().upper().rstrip("F")
            if "D" in t2_hex:
                pan_part, rest = t2_hex.split("D", 1)
                res["card_number"] = pan_part
                if not res["end_date"] and len(rest) >= 4:
                    yymm = rest[:4]
                    if yymm.isdigit():
                        res["end_date"] = f"20{yymm[:2]}-{yymm[2:4]}"

        # 3. 解析有效期截止日期 (Tag 5F24: 3 字节 YYMMDD)
        if "5F24" in tlvs:
            d_hex = tlvs["5F24"].hex().upper()
            if len(d_hex) == 6 and d_hex.isdigit():
                res["end_date"] = f"20{d_hex[:2]}-{d_hex[2:4]}-{d_hex[4:6]}"

        # 4. 解析启用日期 (Tag 5F25: 3 字节 YYMMDD)
        if "5F25" in tlvs:
            d_hex = tlvs["5F25"].hex().upper()
            if len(d_hex) == 6 and d_hex.isdigit():
                res["start_date"] = f"20{d_hex[:2]}-{d_hex[2:4]}-{d_hex[4:6]}"

        # 5. 根据卡号 BIN 前缀推导发卡银行
        c_num = res["card_number"]
        if c_num:
            bank_name = cls.get_bank_name_by_bin(c_num)
            res["issuer_name"] = bank_name
            res["issuer_code"] = bank_name

        return res

    @staticmethod
    def parse_transaction_record(record_bytes: bytes, index: int = 1) -> Optional[Dict[str, Any]]:
        """
        解析交通卡 / 金融 IC 卡一条循环交易记录
        支持：
        1. PBOC 金融 IC 卡 45 字节标准交易记录 (SFI=0x0B / Tag 9F4D)
        2. 全国交通一卡通 (T-Union) / 城市公交卡 23 字节循环记录 (SFI=0x18)
        """
        if len(record_bytes) < 23:
            return None

        # 过滤未写入的空记录槽 (全 0x00 或全 0xFF)
        if record_bytes.count(0x00) == len(record_bytes) or record_bytes.count(0xFF) == len(record_bytes):
            return None

        # ── 模式 1: PBOC 金融卡标准 45 字节循环交易记录 ──
        if len(record_bytes) >= 40:
            try:
                # 字节 0~2: 交易日期 (YYMMDD BCD)
                d_hex = record_bytes[0:3].hex()
                # 字节 3~5: 交易时间 (HHMMSS BCD)
                t_hex = record_bytes[3:6].hex()
                if len(d_hex) == 6 and len(t_hex) == 6 and d_hex.isdigit() and t_hex.isdigit():
                    dt_str = f"20{d_hex[:2]}-{d_hex[2:4]}-{d_hex[4:6]} {t_hex[:2]}:{t_hex[2:4]}:{t_hex[4:6]}"
                else:
                    dt_str = f"{d_hex} {t_hex}"

                # 字节 6~11: 授权金额 (6 字节 BCD, 单位: 分)
                amt_hex = record_bytes[6:12].hex()
                amt_val = round(int(amt_hex) / 100.0, 2) if amt_hex.isdigit() else 0.0

                # 字节 22~41: 商户/机具名称 (20 字节)
                raw_merchant = record_bytes[22:42].strip(b"\x00").strip()
                merchant = ""
                if raw_merchant:
                    try:
                        merchant = raw_merchant.decode("gbk").strip()
                    except Exception:
                        try:
                            merchant = raw_merchant.decode("utf-8", errors="replace").strip()
                        except Exception:
                            pass
                if not merchant:
                    merchant = "银行网点 / ATM机具"

                # 字节 42: 交易类型代码
                t_type = record_bytes[42] if len(record_bytes) > 42 else 0
                if t_type == 0x01:
                    t_desc = "现金取款 / ATM"
                elif t_type == 0x00:
                    t_desc = "消费 / 刷卡支付"
                elif t_type == 0x20:
                    t_desc = "退款 / 冲正"
                elif t_type in (0x02, 0x17):
                    t_desc = "转账 / 圈存"
                else:
                    t_desc = f"金融交易 (0x{t_type:02X})"

                # 字节 43~44: 应用交易计数器 (ATC)
                atc = int.from_bytes(record_bytes[43:45], "big") if len(record_bytes) >= 45 else index

                return {
                    "index": index,
                    "seq": atc or index,
                    "amount": amt_val,
                    "type_byte": t_type,
                    "type_desc": t_desc,
                    "terminal": merchant,
                    "datetime": dt_str,
                    "raw_hex": record_bytes.hex().upper(),
                }
            except Exception:
                pass

        # ── 模式 2: T-Union 全国交通一卡通 23 字节交易记录 ──
        try:
            trans_seq = int.from_bytes(record_bytes[0:2], "big")
            amount_cents = int.from_bytes(record_bytes[5:9], "big")
            amount_yuan = round(amount_cents / 100.0, 2)
            trans_type_byte = record_bytes[9]

            # 交易日期时间: [4B YYYYMMDD BCD] [3B HHMMSS BCD]
            date_str = record_bytes[16:20].hex().upper()
            time_str = record_bytes[20:23].hex().upper()

            # 过滤全零或未初始化的无效记录
            if trans_seq == 0 and amount_cents == 0 and trans_type_byte == 0 and set(date_str) <= {"0", "F"}:
                return None

            # 交易类型: 0x06=消费, 0x09=复合消费, 0x02=圈存/充值
            if trans_type_byte in (0x06, 0x09):
                trans_type_desc = "公共交通/脱机消费"
            elif trans_type_byte == 0x02:
                trans_type_desc = "电子现金圈存/充值"
            else:
                trans_type_desc = f"其它业务 (0x{trans_type_byte:02X})"

            terminal_id = record_bytes[10:16].hex().upper()

            if len(date_str) == 8 and len(time_str) == 6 and date_str.isdigit() and time_str.isdigit():
                datetime_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
            else:
                datetime_formatted = f"{date_str} {time_str}"

            return {
                "index": index,
                "seq": trans_seq,
                "amount": amount_yuan,
                "type_byte": trans_type_byte,
                "type_desc": trans_type_desc,
                "terminal": terminal_id,
                "datetime": datetime_formatted,
                "raw_hex": record_bytes.hex().upper(),
            }
        except Exception:
            return None

    @staticmethod
    def format_hex_ascii_dump(data: bytes, width: int = 16) -> List[str]:
        """将二进制数据格式化为类似 Wireshark/xxd 的标准 Hex Dump + ASCII 对照视图"""
        if not data:
            return []
        lines = []
        for offset in range(0, len(data), width):
            chunk = data[offset : offset + width]
            # Hex 域 (8 字节一组，中间加双空格)
            hex_parts = []
            for i, b in enumerate(chunk):
                if i == 8:
                    hex_parts.append(" ")
                hex_parts.append(f"{b:02X}")
            hex_str = " ".join(hex_parts)
            # 补齐对齐宽度
            expected_len = width * 3 + 1
            if len(hex_str) < expected_len:
                hex_str = hex_str.ljust(expected_len)

            # ASCII 可视化域
            ascii_chars = []
            for i, b in enumerate(chunk):
                if i == 8:
                    ascii_chars.append(" ")
                ascii_chars.append(chr(b) if 0x20 <= b <= 0x7E else ".")
            ascii_str = "".join(ascii_chars)

            lines.append(f"{offset:04X}:  {hex_str} | {ascii_str}")
        return lines

    @staticmethod
    def explain_apdu_command(apdu: bytes) -> Dict[str, Any]:
        """解析一条发送的 APDU 指令，输出助记符、参数含义与解析结果"""
        if not apdu or len(apdu) < 4:
            return {"mnemonic": "UNKNOWN", "desc": "指令长度不足 (至少需 4 字节 Header)", "details": []}

        cla, ins, p1, p2 = apdu[0], apdu[1], apdu[2], apdu[3]
        cmd_key = f"{cla:02X}{ins:02X}"

        mnemonic = "CUSTOM APDU"
        desc = "通用或厂商私有 APDU 指令"
        details = []

        # 经典标准指令库
        if ins == 0xA4:  # SELECT FILE
            mnemonic = "SELECT FILE"
            if p1 == 0x04:
                desc = "选择应用目录 / 专用名 (By DF / AID)"
            elif p1 == 0x00:
                desc = "选择主文件目录 / 文件标识 (By FID)"
            else:
                desc = f"选择文件或应用 (P1=0x{p1:02X})"

            if len(apdu) > 5:
                lc = apdu[4]
                data = apdu[5 : 5 + lc]
                # 检查是否为已知知名 AID
                aid_hex = data.hex().upper()
                known_name = ""
                if "2PAY.SYS.DDF01" in data.decode("ascii", errors="ignore"):
                    known_name = "2PAY.SYS.DDF01 (PPSE 非接支付系统环境目录)"
                elif aid_hex.startswith("A000000632"):
                    known_name = "交通运输部全国交通联合电子钱包应用 (MOT_T_EP)"
                elif aid_hex.startswith("A000000333"):
                    known_name = "全国交通一卡通互联互通标准应用 (T-Union)"
                elif aid_hex.startswith("A00000000386980701"):
                    known_name = "中国银联 PBOC 电子现金应用 (qPBOC)"
                elif aid_hex == "3F00":
                    known_name = "主文件根目录 (MF - 3F00)"

                if known_name:
                    details.append(f"目标目录/AID: {known_name}")
                else:
                    details.append(f"目标数据 (Data): {data.hex().upper()}")

        elif ins == 0x84:  # GET CHALLENGE
            mnemonic = "GET CHALLENGE"
            le = apdu[4] if len(apdu) > 4 else 8
            desc = f"取硬件随机数 (期望长度: {le} 字节)"
            details.append(f"安全认证机制: 要求卡片生成并返回 {le} 字节强随机伪随机数")

        elif ins == 0xB0:  # READ BINARY
            mnemonic = "READ BINARY"
            # P1 的高 3 位为 100 时，低 5 位为 SFI
            if p1 & 0x80:
                sfi = p1 & 0x1F
                offset = p2
                desc = f"读取二进制文件 (SFI=0x{sfi:02X}, 偏移量=0x{offset:02X})"
            else:
                offset = (p1 << 8) | p2
                desc = f"读取当前二进制文件 (偏移量=0x{offset:04X})"

            le = apdu[4] if len(apdu) > 4 else 0
            if (p1, p2) == (0x95, 0x00):
                details.append("目标文件: 0015 公共信息文件 (包含发卡机构、卡号、启用日期与有效期)")
            elif (p1, p2) == (0x85, 0x00):
                details.append("目标文件: 0005 持卡人基础信息文件")
            details.append(f"期望读取长度 (Le): {le} 字节 {'(读至文件结尾)' if le == 0 else ''}")

        elif ins == 0xB2:  # READ RECORD
            mnemonic = "READ RECORD"
            rec_num = p1
            sfi = (p2 >> 3) & 0x1F
            mode = p2 & 0x07
            desc = f"读取记录文件 (第 {rec_num} 条记录, SFI=0x{sfi:02X})"
            details.append(f"记录索引: 第 {rec_num} 条 | 定位模式: {mode}")
            if sfi in (0x18, 0x10, 0x0B):
                details.append(f"文件用途: SFI=0x{sfi:02X} 循环交易流水记录明细文件")

        elif ins == 0x5C:  # GET BALANCE
            mnemonic = "GET BALANCE"
            desc = f"查询电子现金 / 电子钱包卡内余额 (P1=0x{p1:02X}, P2=0x{p2:02X})"
            details.append("查询目标: 电子现金余额 / 联机圈存脱机消费账户可用金额")

        elif ins == 0x20:  # VERIFY
            mnemonic = "VERIFY PIN"
            desc = f"校验 PIN 码 (P1=0x{p1:02X}, P2=0x{p2:02X})"
            details.append("安全操作: 向卡内安全芯片校验持卡人个人身份密码")

        elif ins == 0xD6:  # UPDATE BINARY
            mnemonic = "UPDATE BINARY"
            desc = f"更新写入二进制文件 (偏移量=0x{(p1<<8)|p2:04X})"

        elif ins == 0x88:  # INTERNAL AUTHENTICATE
            mnemonic = "INTERNAL AUTH"
            desc = "卡片内部认证 (非对称公钥/DES算法计算签名)"

        elif ins == 0xC0:  # GET RESPONSE
            mnemonic = "GET RESPONSE"
            le = apdu[4] if len(apdu) > 4 else 0
            desc = f"取回卡片待输出数据 (Le={le} 字节)"
            details.append("ISO 7816-4 规范: 取回前序指令 (如 61xx 状态) 暂存在卡内缓冲区的响应数据")

        elif ins == 0x82:  # EXTERNAL AUTHENTICATE
            mnemonic = "EXTERNAL AUTH"
            desc = "外部认证 (上位机向卡片发起安全会话认证)"

        return {
            "cla": cla,
            "ins": ins,
            "p1": p1,
            "p2": p2,
            "mnemonic": mnemonic,
            "desc": desc,
            "details": details,
        }

    @classmethod
    def dissect_apdu_response(cls, cmd_apdu: bytes, rx_data: bytes, sw1: int, sw2: int) -> Dict[str, Any]:
        """
        深度解析 APDU 交互响应
        根据下发的 APDU 结合收到的数据内容，智能推导其业务语义 (如余额、卡号、流水、FCI、随机数等)
        """
        sw_hex = f"{sw1:02X}{sw2:02X}"
        sw_desc = cls.get_sw_description(sw1, sw2)
        is_ok = (sw1 == 0x90 and sw2 == 0x00) or (sw1 == 0x61) or (sw1 == 0x9F)

        semantics = []
        parsed_fields = {}

        if is_ok and len(rx_data) > 0:
            ins = cmd_apdu[1] if len(cmd_apdu) >= 2 else 0x00

            # 1. 余额查询 (GET BALANCE 80 5C)
            if ins == 0x5C or (len(cmd_apdu) >= 4 and cmd_apdu[0] == 0x80 and cmd_apdu[1] == 0x5C):
                bal = cls.parse_balance(rx_data)
                if bal is not None:
                    cents = int.from_bytes(rx_data[:4], "big", signed=True)
                    semantics.append(f"★ 账户当前余额: ¥ {bal:.2f} 元 ({cents} 分 / 十六进制 0x{cents:08X})")
                    parsed_fields["balance_yuan"] = bal
                    parsed_fields["balance_cents"] = cents

            # 2. 读 0015 公共信息文件 (READ BINARY P1=95 或长度 >= 30 且包含卡号特征)
            elif ins == 0xB0 and len(rx_data) >= 28 and (len(cmd_apdu) >= 3 and cmd_apdu[2] == 0x95):
                card_info = cls.parse_t_union_card_info(rx_data)
                if card_info.get("card_number"):
                    semantics.append(f"• 应用卡号: {card_info.get('card_number')} (全国互通标准卡号)")
                if card_info.get("issuer_code"):
                    semantics.append(f"• 发卡机构代码: {card_info.get('issuer_code')}")
                if card_info.get("start_date") and card_info.get("end_date"):
                    semantics.append(f"• 有效期限: {card_info.get('start_date')} 至 {card_info.get('end_date')}")
                parsed_fields.update(card_info)

            # 3. 读循环交易记录 (READ RECORD 00 B2)
            elif ins == 0xB2 and len(rx_data) >= 23:
                rec_idx = cmd_apdu[2] if len(cmd_apdu) >= 3 else 1
                rec_info = cls.parse_transaction_record(rx_data, index=rec_idx)
                if rec_info:
                    semantics.append(f"• 交易序号: #{rec_info.get('seq')} (0x{rec_info.get('seq'):04X})")
                    semantics.append(f"• 业务类型: {rec_info.get('type_desc')} (代码: 0x{rec_info.get('type_byte'):02X})")
                    semantics.append(f"• 交易金额: ¥ {rec_info.get('amount'):.2f} 元")
                    semantics.append(f"• 交易时间: {rec_info.get('datetime')}")
                    semantics.append(f"• 终端机号: {rec_info.get('terminal')}")
                    parsed_fields.update(rec_info)

            # 4. 取随机数 (GET CHALLENGE 00 84)
            elif ins == 0x84:
                rand_hex = " ".join(f"{b:02X}" for b in rx_data)
                semantics.append(f"★ 芯片随机数 (Challenge): {rand_hex} ({len(rx_data)} 字节)")
                parsed_fields["challenge_hex"] = rand_hex

            # 5. 选择应用目录响应 (SELECT FILE 00 A4 返回 6F FCI 模板)
            elif ins == 0xA4 and rx_data[0] == 0x6F:
                semantics.append("• 响应模板: 6F (FCI File Control Information 结构)")
                ppse_info = cls.parse_ppse_response(rx_data)
                if ppse_info and ppse_info.get("aid"):
                    semantics.append(f"• 提取到目标 AID: {ppse_info.get('aid_hex')}")
                    semantics.append(f"• 应用名称/标签: {ppse_info.get('label')}")
                    parsed_fields["extracted_aid"] = ppse_info.get("aid_hex")
                    parsed_fields["extracted_label"] = ppse_info.get("label")

        # 生成格式化 Hex + ASCII Dump 视图
        dump_lines = cls.format_hex_ascii_dump(rx_data)

        return {
            "sw_hex": sw_hex,
            "sw_desc": sw_desc,
            "is_ok": is_ok,
            "length": len(rx_data),
            "semantics": semantics,
            "dump_lines": dump_lines,
            "parsed_fields": parsed_fields,
        }

