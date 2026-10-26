# M1T 外部工具链（实验性）

本目录收录自 `M1T-v1.7` 的 libnfc / mfoc / mfcuk 工具，供 PyMifareTool 的
「外部攻击」页面调用。所有工具均为第三方二进制，行为与兼容性未经本项目完整验证，
仅建议在**自己拥有或已获授权**的卡片上使用。

## 目录

```text
tools/m1t/nfc-bin/
├── mfoc.exe / mfoc2.exe              # Nested 攻击
├── mfcuk.exe / mfcuk2.exe            # Darkside 盲破
├── mfdetect.exe                      # 卡片加密/漏洞探测
├── libnfc_hardnested.exe             # Hardnested（实验性 CLI）
├── libnfc_hardnestedlc.exe
├── nfc-list.exe / nfc-scan-device.exe
├── nfc-anticol.exe
├── nfc-mfclassic.exe                 # M1 读写
├── nfc-mfsetuid.exe                  # 魔术卡 UID
├── nfc-mfultralight.exe
├── pn53x-diagnose.exe
├── pn53x-sam.exe / pn53x-tamashell.exe
├── libnfc.dll                        # 默认 libnfc
├── libnfc(532).dll                   # PCR532/PN532 UART 版本
├── libnfc(ACR122Uslow).dll           # ACR122U 慢速版本
├── libusb0.dll
├── libgcc_s_dw2-1.dll
├── libwinpthread-1.dll
└── data/tmpls_fingerprints/*.mfd
```

## 使用前必须注意

1. **先断开 PyMifareTool 的串口连接**。libnfc 会独占 COM 口，不能与主程序同时打开。
   若在程序仍连接时直接运行 mfoc，会出现 `未找到NFC设备` / `No NFC device found`。
2. 推荐从 PyMifareTool 的「字典工具 → 外部攻击」页启动：程序会检查串口占用，
   自动设置 `NFC_DEVICE`、工作目录和输出绝对路径，并把 GBK/UTF-8 输出统一解码显示。
3. 外部工具通过 `libnfc.dll` 访问设备。PCR532/PN532 串口设备通常需要将
   `libnfc(532).dll` 复制/重命名为 `libnfc.dll`（原文件请先备份）。
4. ACR122U 使用 `libnfc(ACR122Uslow).dll`。
5. `libnfc_hardnested.exe` 的 CLI 参数与常见 hardnested 不完全一致，当前仅做实验性接入；
   若程序挂起，请在任务管理器中结束并改用 mfoc/mfcuk。
6. 标准 PCR532/PN532 HSU 固件不直接暴露 Crypto1 nonce 采集接口；能否运行
   darkside/nested/hardnested 取决于 libnfc 驱动与设备固件，需要上机实测。

## 设备连接示例（PowerShell）

```powershell
# 让 libnfc 使用 PN532 UART
$env:NFC_DEVICE = "pn532_uart:COM3:115200"

# 确认设备可见
.\nfc-scan-device.exe -v
.\nfc-list.exe

# Nested 攻击（需要至少一个已知密钥）
.\mfoc.exe -O dump.mfd

# Darkside 盲破（较慢，可能损伤卡片状态）
.\mfcuk.exe -v 3 -C -R -1 -s 250 -S 250 -d 0 -w 0 -O dump.mfd
```

也可以创建 `libnfc.conf`：

```ini
device.name = "PCR532 / PN532 UART"
device.connstring = "pn532_uart:COM3:115200"
```

然后在同一目录运行工具。

## 已实测：PCR532 / PN532 UART

在 Windows + CH340 + PCR532 上确认：

1. 将 `libnfc(532).dll` 覆盖为 `libnfc.dll` 后，`nfc-scan-device.exe -v` 能识别
   `pn532_uart:COM3:115200`，芯片显示 `PN532 v1.6`。
2. `nfc-list.exe` 能读到 ISO14443A 卡片 UID 与 SAK。
3. `mfoc.exe` 可读取已知密钥扇区；但对随机数强化/静态 nonce 卡，classic nested
   可能一直停留在 `distance 65439`，此时应改用 hardnested。
4. `libnfc_hardnested.exe` 用法：

```text
libnfc_hardnested.exe <known key> <known block> <A|B> <target block> <A|B>
```

示例（S00 Key A 已知为 FFFFFFFFFFFF，目标 S12 的尾块 51 Key A）：

```powershell
$env:NFC_DEVICE = "pn532_uart:COM3:115200"
.\libnfc_hardnested.exe FFFFFFFFFFFF 0 A 51 A
```

5. 如果输出 `Reader-answer transfer error`，优先检查已知密钥、块号、A/B 类型是否
   与该扇区实际一致；不要用未知密钥所在扇区做已知密钥。
6. hardnested 的 nonce 收集速度受 PN532 UART 限制，实测约 10-12 个/秒，
   可能需要数小时；运行期间会独占 COM3。

## 来源与版本

- 来源：`M1T-v1.7/nfc-bin` 随附工具集
- libnfc：1.7.1 系
- mfcuk：0.3.8
- 未收录 `winhex.exe`、日志与 `.bak` 备份文件
- 仅作互操作与学习用途；请遵守当地法律法规。
