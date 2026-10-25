# -*- coding: utf-8 -*-
"""
PyMifareTool - 蓝牙低功耗 (BLE) 设备智能分类与特征解析中枢
根据 BLE 广播名称、Service UUID、厂商标识 (Manufacturer Data)、Appearance 及信号强度，
实现对周围蓝牙设备（耳机、游戏手柄、键鼠外设、智能穿戴、手机电脑及目标 NFC 读写器）的精准识别与分类。
"""

from typing import Dict, Any, List, Optional, Tuple

# 知名厂商标识 (Bluetooth SIG Assigned Numbers - Company Identifiers)
KNOWN_MANUFACTURERS: Dict[int, str] = {
    0x004C: "Apple",
    0x0006: "Microsoft",
    0x0157: "Huami/Xiaomi",
    0x027D: "Huawei",
    0x0075: "Samsung",
    0x000F: "Broadcom",
    0x000A: "Qualcomm",
    0x0059: "Nordic Semi",
    0x02B0: "Espressif",
    0x07D7: "WCH",  # 南京沁恒
    0x0087: "Garmin",
    0x0001: "Sony",
    0x00D2: "Dialog Semi",
    0x00E0: "Google",
    0x05A7: "Sonos",
    0x0002: "Intel",
}

# 目标 NFC / RFID 读写器关键字与服务
READER_KEYWORDS = [
    "minicopy", "pn532", "pcr532", "ch59", "rfid", "nfc", "mifare",
    "acr122", "reader", "smartcard", "proxmark", "nfc-ble"
]

READER_SERVICES = [
    "0000ff00-0000-1000-8000-00805f9b34fb",
    "0000ae00-0000-1000-8000-00805f9b34fb",
    "0000fee7-0000-1000-8000-00805f9b34fb",
]

# 音频设备 (耳机 / 耳麦 / 音箱) 关键字与服务
AUDIO_KEYWORDS = [
    "buds", "airpods", "freebuds", "headphone", "headset", "earphone",
    "earbuds", "audio", "speaker", "sound", "jbl", "bose", "sony",
    "soundcore", "ows", "beats", "wh-", "wf-", "edifier", "fiio", "hifi",
    "galaxy buds", "airpods pro", "airpods max", "tws"
]

AUDIO_SERVICES = [
    "0000110a", "0000110b", "00001108", "0000110e", "0000111e", "00001200"
]

# 游戏手柄 / 控制器关键字
GAMEPAD_KEYWORDS = [
    "controller", "gamepad", "xbox", "dualsense", "dualshock", "switch",
    "joy-con", "joycon", "8bitdo", "flydigi", "gamesir", "betop",
    "pro controller", "game controller", "joystick"
]

# 蓝牙键盘关键字
KEYBOARD_KEYWORDS = [
    "keyboard", "keychron", "ikbc", "filco", "ducky", "k380", "k480",
    "k780", "k855", "typing", "kbd", "nuphy", "hhkb", "leopold", "varmilo"
]

# 蓝牙鼠标 / 触控板关键字
MOUSE_KEYWORDS = [
    "mouse", "trackpad", "touchpad", "magic mouse", "master 2", "master 3",
    "anywhere", "pebble", "logi mouse", "razer mouse", "stylus"
]

# 智能穿戴 (手表 / 手环) 关键字与服务
WEARABLE_KEYWORDS = [
    "watch", "band", "fitbit", "garmin", "pace", "smart watch", "gt 2",
    "gt 3", "gt 4", "gt 5", "mi band", "honor band", "amazfit"
]

# 手机 / 平板电脑关键字
PHONE_KEYWORDS = [
    "iphone", "ipad", "xiaomi", "redmi", "galaxy", "pixel", "huawei",
    "honor", "oppo", "vivo", "oneplus", "phone", "pad", "tablet"
]

# 电脑主机关键字
PC_KEYWORDS = [
    "pc", "laptop", "desktop", "macbook", "imac", "mac mini", "mac studio",
    "surface", "thinkpad", "desktop-", "laptop-"
]


class BleClassifier:
    """BLE 设备特征解析与类别推断器"""

    @classmethod
    def classify(
        cls,
        name: Optional[str] = None,
        address: str = "",
        rssi: Optional[int] = None,
        service_uuids: Optional[List[str]] = None,
        manufacturer_data: Optional[Dict[int, bytes]] = None,
        details: Any = None,
    ) -> Dict[str, Any]:
        """
        对 BLE 广播设备进行全维度多源特征识别
        返回: 结构化分类信息字典
        """
        service_uuids = [u.lower() for u in (service_uuids or [])]
        mfg_dict = manufacturer_data or {}
        address_str = (address or "").strip().upper()
        raw_name = (name or "").strip()
        lower_name = raw_name.lower()

        # 1. 厂商信息提取
        mfg_names = []
        for mfg_id in mfg_dict.keys():
            if mfg_id in KNOWN_MANUFACTURERS:
                mfg_names.append(KNOWN_MANUFACTURERS[mfg_id])
            else:
                mfg_names.append(f"0x{mfg_id:04X}")
        mfg_desc = ", ".join(mfg_names) if mfg_names else ""

        # 2. 类别推断与打分判定
        # 优先级 0: 目标 NFC/RFID 读写器
        is_reader = False
        if any(k in lower_name for k in READER_KEYWORDS):
            is_reader = True
        elif any(any(s in u for s in ["0000ff00", "0000ae00", "0000fee7"]) for u in service_uuids):
            is_reader = True

        if is_reader:
            friendly_name = raw_name or "NFC/RFID 读卡器"
            category_id = "reader"
            category_name = "NFC读写器"
            icon = "💳"
            priority = 0
            tag = "[读写器]"
        # 优先级 1: 音频/耳机
        elif any(k in lower_name for k in AUDIO_KEYWORDS) or any(any(s in u for s in AUDIO_SERVICES) for u in service_uuids):
            friendly_name = raw_name or "蓝牙耳机/音响"
            category_id = "audio"
            category_name = "音频/耳机"
            icon = "🎧"
            priority = 10
            tag = "[音频/耳机]"
        # 优先级 2: 游戏手柄
        elif any(k in lower_name for k in GAMEPAD_KEYWORDS):
            friendly_name = raw_name or "游戏手柄"
            category_id = "gamepad"
            category_name = "游戏手柄"
            icon = "🎮"
            priority = 15
            tag = "[游戏手柄]"
        # 优先级 3: 蓝牙键盘
        elif any(k in lower_name for k in KEYBOARD_KEYWORDS):
            friendly_name = raw_name or "蓝牙键盘"
            category_id = "keyboard"
            category_name = "蓝牙键盘"
            icon = "⌨️"
            priority = 20
            tag = "[蓝牙键盘]"
        # 优先级 4: 蓝牙鼠标/触控板
        elif any(k in lower_name for k in MOUSE_KEYWORDS):
            friendly_name = raw_name or "蓝牙鼠标"
            category_id = "mouse"
            category_name = "蓝牙鼠标"
            icon = "🖱️"
            priority = 25
            tag = "[蓝牙鼠标]"
        # 优先级 5: 智能穿戴
        elif any(k in lower_name for k in WEARABLE_KEYWORDS) or any("0000180d" in u for u in service_uuids):
            friendly_name = raw_name or "智能手环/手表"
            category_id = "wearable"
            category_name = "手环/手表"
            icon = "⌚"
            priority = 30
            tag = "[手环/手表]"
        # 优先级 6: 电脑主机
        elif any(k in lower_name for k in PC_KEYWORDS) or (0x0006 in mfg_dict and ("desktop" in lower_name or "pc" in lower_name)):
            friendly_name = raw_name or "电脑设备"
            category_id = "pc"
            category_name = "电脑设备"
            icon = "💻"
            priority = 35
            tag = "[电脑主机]"
        # 优先级 7: 手机/平板
        elif any(k in lower_name for k in PHONE_KEYWORDS):
            friendly_name = raw_name or "手机/平板"
            category_id = "phone"
            category_name = "手机/平板"
            icon = "📱"
            priority = 40
            tag = "[手机/平板]"
        # 优先级 8: Apple 生态未命名广播
        elif 0x004C in mfg_dict and not raw_name:
            friendly_name = "Apple 广播设备"
            category_id = "apple"
            category_name = "Apple设备"
            icon = "🍎"
            priority = 50
            tag = "[Apple设备]"
        # 优先级 9: Microsoft 未命名电脑广播
        elif 0x0006 in mfg_dict and not raw_name:
            friendly_name = "Windows 电脑设备"
            category_id = "pc"
            category_name = "Windows设备"
            icon = "💻"
            priority = 52
            tag = "[Windows设备]"
        # 优先级 10: 通用 HID 外设
        elif any("00001812" in u for u in service_uuids):
            friendly_name = raw_name or "蓝牙人机外设"
            category_id = "peripheral"
            category_name = "蓝牙外设"
            icon = "🔌"
            priority = 60
            tag = "[蓝牙外设]"
        # 优先级 11: 有具体名字的其它设备
        elif raw_name:
            friendly_name = raw_name
            category_id = "generic"
            category_name = "蓝牙设备"
            icon = "📟"
            priority = 70
            tag = "[蓝牙设备]"
        # 优先级 12: 纯未知匿名设备
        else:
            friendly_name = "未知蓝牙设备"
            category_id = "unknown"
            category_name = "未知设备"
            icon = "❓"
            priority = 90
            tag = "[未知设备]"

        # 3. 信号质量与强度评估
        rssi_val = rssi if rssi is not None else -100
        if rssi_val >= -60:
            signal_quality = "极佳"
            signal_icon = "🟢"
        elif rssi_val >= -75:
            signal_quality = "良好"
            signal_icon = "🟡"
        elif rssi_val >= -85:
            signal_quality = "一般"
            signal_icon = "🟠"
        else:
            signal_quality = "较弱"
            signal_icon = "🔴"

        rssi_str = f"{rssi_val} dBm" if rssi is not None else "未知"

        # 4. 组装下拉选项显示文本 (单行格式清晰，包含图标、类型标签、名称、完整地址及信号)
        recommend_suffix = " ★推荐" if is_reader else ""
        display_text = f"{icon} {tag:<8} {friendly_name} [{address_str}] ({rssi_str}){recommend_suffix}"

        # 5. 组装多行富文本悬停 ToolTip 说明
        tooltip_lines = [
            f"<b>【设备名称】</b>: {raw_name or friendly_name}",
            f"<b>【设备分类】</b>: {icon} {category_name} {recommend_suffix}",
            f"<b>【MAC 地址】</b>: <font color='#38BDF8'>{address_str}</font>",
            f"<b>【信号强度】</b>: {signal_icon} {rssi_str} ({signal_quality})",
        ]
        if mfg_desc:
            tooltip_lines.append(f"<b>【厂商标识】</b>: {mfg_desc}")
        if service_uuids:
            uuids_preview = ", ".join(u[:8] + "..." for u in service_uuids[:3])
            tooltip_lines.append(f"<b>【广播服务】</b>: {uuids_preview}")
        if is_reader:
            tooltip_lines.append("<i>✨ 目标 NFC 读写器，采用 BLE GATT 透明传输，免系统配对即可直连</i>")

        tooltip = "<br/>".join(tooltip_lines)

        return {
            "name": raw_name or friendly_name,
            "raw_name": raw_name,
            "address": address_str,
            "rssi": rssi_val,
            "rssi_str": rssi_str,
            "signal_quality": signal_quality,
            "signal_icon": signal_icon,
            "category_id": category_id,
            "category_name": category_name,
            "icon": icon,
            "tag": tag,
            "friendly_name": friendly_name,
            "display_text": display_text,
            "tooltip": tooltip,
            "priority": priority,
            "is_reader": is_reader,
            "service_uuids": service_uuids,
            "manufacturer": mfg_desc,
        }
