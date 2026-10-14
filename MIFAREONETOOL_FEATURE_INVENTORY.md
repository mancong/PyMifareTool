# MifareOneTool (xcicode/MifareOneTool) — evidence-based user-facing feature inventory

Research date: this session. All source-level evidence below was obtained by decoding the actual
repository files through the GitHub **contents API** (base64) and decoding the resources locally.

## Provenance / access notes (read this before trusting anything)

| Item | Status |
|---|---|
| `README.md` | Fetched. **100 bytes only**: "A GUI Mifare Classic tool on Windows" + "因作者事务繁忙，软件不再更新。" No feature docs. |
| Repo metadata | Fetched. `default_branch = dev`, `license = GPL-3.0`, topics `nfc`, `nfc-crack`, `nfc-reader`, `has_wiki = true`, created 2018-12-22, last push 2019-05-17. |
| File trees | Fetched for `master` and `dev` (recursive) + the `MifareOneTool/` subtree. Source file list below is complete. |
| Releases | Fetched all 13 release bodies (v1.0.0 … v1.7.0). Text is quoted below; the attached **PDF manuals could NOT be read** (assets are served from `github.com`, unreachable from my tool network). |
| Issues | Fetched (first ~100 KB of the list; the oldest issues may be missing). |
| `wiki` | **NOT FETCHED.** `https://github.com/xcicode/MifareOneTool/wiki` failed; `has_wiki=true` but no non-HTML wiki API exists. Wiki content is **unverified**. |
| Source files **fully read/decoded** | `Form1.cs` (**master** branch), `Form1.zh.resx` (dev, decoded to 72 216 / 119 324 bytes — all text entries are in that prefix), `FormHTool.resx` (dev, complete), `FormHardNes.resx` (dev, complete), `Properties/Resources.Designer.cs` (dev, complete → all 143 resource keys). |
| Source files **NOT read** | `ClassMifareS50.cs`, `FormHTool.cs`, `FormDiff.cs`, `FormHardNes.cs`, `FormMFF08.cs`, `GitHubUpdate.cs`, `SelectLanguage.cs`, `Program.cs`, `Form1.Designer.cs`, `MifareOneTool.csproj`. Their *user-visible effects* are covered by the decoded `.resx` files + `Form1.cs` + release notes, but their internal logic is **unverified**. |

### Architecture fact that drives everything
MifareOneTool is a **C# WinForms GUI wrapper (launcher) around prebuilt libnfc-family CLI binaries**.
No NFC protocol code exists in the repo. The binaries are **not in the repo** — they ship as the release
asset `nfc-bin.zip` (and `nfc-bin_CHN.zip`), to be unzipped into `nfc-bin/`
(release notes v1.0.0/v1.1.0/v1.6.0: "nfc-bin.zip内为nfc相关二进制程序，需放在程序目录下的nfc-bin文件夹中").

Exact programs executed (verbatim from `Form1.cs`, master):

| Program | Purpose |
|---|---|
| `nfc-bin/nfc-scan-device.exe` | enumerate readers |
| `nfc-bin/nfc-list.exe` | scan card / get UID (also `GetUID()`) |
| `nfc-bin/nfc-mfclassic.exe` | read / write / format Mifare Classic dumps |
| `nfc-bin/nfc-mfsetuid.exe` | magic-UID-card block-0 reset / full format / UFUID lock |
| `nfc-bin/mfoc.exe` | nested attack (`-O` output; launched via `cmd /T:0A …`) |
| `nfc-bin/mfdetect.exe` | encryption-detection (v1.5.0 note: "这个mfdetect就是个mfoc去掉了破解部分而已，所以-f -k什么的可以加上，测试自己的key") |
| `nfc-bin/mfcuk.exe` | darkside attack — `cmd /k mfcuk.exe -v 3 -C -R -1 -s 250 -S 250` |
| `nfc-bin/cropto1_bs.exe` | HardNested computation/collection (`crypto1_bs`) |
| `nfc-bin/collect.exe` | nonce collection (resource `nfc_bin_collect_exe` = `nfc-bin/collect.exe`) |
| `nfc-bin/nfcUID.exe` | UID display helper — `nfcUID.exe -device=1` |
| `cmd.exe` | "手动CLI" (manual CLI) |
| `libusb/libusbK-inf-wizard.exe` | driver installer for ACR122U (`button1_Click`) |

⇒ Backends are **libnfc-family command-line tools** (`nfc-*`, `mfoc`, `mfcuk`, `crypto1_bs`).
There is **no** nfcpy, **no** RFIDIOt, **no** Proxmark3 client, **no** direct `libnfc` P/Invoke
(other than the DLL file swap described below).

---

## 1. Hardware / reader support

- [x] **PN532 over UART (COM port)** — the primary, auto-detected reader. `Form1.cs` writes `libnfc.conf`
      with `device.name = "NFC Device"` / `device.connstring = "pn532_uart:COMx:115200"`, and detection is a
      regex: `Regex.Match(_e.Data, "pn532_uart:COM\\d+:115200")`. Also matches a `libnfc.conf` line starting
      `device.connstring = "pn532_uart:`.
- [x] **ACR122U (USB)** — supported through a **DLL swap**, not through real auto-detection
      (`buttonEnAcr122u_Click`): `File.Move("nfc-bin/libnfc.dll", "nfc-bin/libnfc(PN532Only).dll")` then
      `File.Move("nfc-bin/libnfc(ACR122U).dll", "nfc-bin/libnfc.dll")`. Strings: 正在打开ACR122U支持 /
      ACR122U支持已经打开过 / "同时打开ACR122U支持可能会引起操作速度下降_请确认是否".
      Requires the bundled libusb driver — release v1.6.4: "优化对ACR122U支持，请安装好压缩包内的驱动文件（122-libusb.zip）",
      and the app bundles a `libusb\libusbK-inf-wizard.exe` launcher.
- [x] **Manual reader selection** — after detection, readers populate `SetDeviceCombo`; the choice is written to
      `libnfc.conf` (已指定使用该NFC设备 / 将自动选择首个设备). Windows: `Form1.cs`.
- [x] Device troubleshooting messages: 没有发现任何有效的NFC设备, 请检查接线是否正确_驱动是否正常安装_设备电源是否已经打开_.
- [x] **Explicit support statement in the UI** (`Form1.zh.resx`, `buttonListDev.ToolTip`):
      "扫描已连接的NFC设备（目前支持PN532、ACR122U）" — **only PN532 and ACR122U**.
- [x] Manual CLI escape hatch (打开NFC命令行以进行高级操作) lets an expert drive any libnfc reader manually.
- [ ] **RDM880 / DenDen / Proxmark3 / PN532-I2C/SPI/USB / ARYGON / PCSC**: **no evidence anywhere** in
      `Form1.cs`, the decoded UI strings, the release notes, or the issue titles. Treat as unsupported
      (unverified negative: `nfc-scan-device.exe` is a stock libnfc tool, whose driver set is not limited by
      this GUI, but this GUI parses only `pn532_uart` connstrings).

## 2. Card types

- [x] **Mifare Classic 1K (S50) and 4K / S70** — the documented scope. Verified UI label (`Form1.zh.resx`,
      `label13`): **"本工具仅支持SAK=08/18/28的卡片复制。SAK28无一键解密。若要复制S70卡片，请在高级界面上取消勾选'数据写入保护'。"**
      (SAK 08 = Classic 1K, SAK 18 = Classic 4K, SAK 28 = the "hardened"/Plus-SL1-style variant that MFOC
      nested cannot crack automatically).
- [x] Mifare Classic **Mini** — never named; would only work incidentally through 1K tooling. **Unverified.**
- [x] Known limitation: release v1.6.2 — "检测加密不适用于SAK28卡片" (encryption detection does not work on SAK28).
- [x] Indonesian/generic "该卡种读取同普通卡" hint label exists for a card class read like a normal card.
- [x] UID/magic card family: **UID (Gen1a-type), CUID, FUID, UFUID** — see §5. Label text mentions 复旦 (Fudan)
      as the manufacturer written for UID cards.
- [ ] **Ultralight / NTAG / Mifare Plus / DESFire / ISO15693 / ICODE**: **no evidence** of support in code,
      UI strings, or release notes. This tool is Classic-only.

## 3. Card operations (Classic)

Dump model: 64 blocks × 16 bytes = 1024-byte image; the S50 class validates block counts
("文件内不是含有64个块数据_可能不完整或不兼容") and access bits.

- [x] **Scan card / read UID** — 手动扫描 (`buttonScanCard`), `nfc-list.exe`.
- [x] **Read whole card (dump all sectors)** — 读M1 (`buttonMfRead`) → `nfc-mfclassic r <keytype> u "<file>"`
      ("读取普通M1卡片（可能需要加载密钥文件）").
- [x] **Write whole card** — 写M1 (`buttonMfWrite`) → `nfc-mfclassic w <keytype> u "<file>"`
      ("写入普通M1卡（可能需要加载密钥文件）"); can append `"<keymfd>" f`.
- [x] **Format / erase card** — 清M1 (`buttonMfFormat`) → `nfc-mfclassic f <keytype> u "<file>"`
      ("格式化普通M1卡（必须加载密钥文件）").
- [x] **Key type selection per write/read**: KeyA (是) / KeyB (否) / no key ("不使用，用于全新白卡")
      → argument `A`, `B`, or `x`; plus **智能KeyABN** (`kt = "C"`, 正在使用智能KeyABN) which
      auto-negotiates A/B/none when a key file is loaded. (What the shipped `nfc-mfclassic` does with the
      literal `C` argument is **unverified** — it is a non-stock extension of the bundled binary.)
- [x] **Key file (key.mfd) load/unload** — 选择key.mfd (`buttonSelectKey`) /
      "加载含有正确读写卡密钥及正确控制位的MFD文件"; cancel to unload (v1.2.0 release note:
      "取消加载key.mfd").
- [x] **Auto-load key file by UID** — 自动加载uid.Key文件 (`checkBoxAutoLoadKey`); searches `auto_keys\*.mfd`
      for a file whose name starts with the card UID, preferring the newest (v1.6.6 fix).
- [x] **Sector trailer / access-bit handling** — the Hex editor exposes KeyA, KeyB and 4 access-bit
      permission selectors per sector, plus "检查全卡" / "检查并纠正全卡" and per-sector validation messages
      (该扇区访问控制位损坏/无效_写入将会损坏卡片_已重新设置, 该扇区UID校验值错误_已自动更正,
      当前扇区数据仍有错误_不能执行修改). **The tool fixes invalid AC bits before writing.**
- [x] **Write protection / pre-write validation** — 数据写入保护(建议) (`checkBoxWriteProtect` / `WriteCheck`):
      `writecheck(file)` loads the file into `S50` and refuses to write on error
      ("将要写入的文件存在错误_请用高级模式中的Hex工具打开查看").
- [x] Value-block operations (init/inc/dec/restore/transfer) as **explicit commands**: **no evidence**.
      The AC-bit combo boxes only *describe* the value-block permissions
      (e.g. "KeyAB读写及增减值", "KeyAB读及减值/KeyB写及增值"). No `nfc-mfclassic` value-block CLI is invoked,
      and no value-block button exists. ⇒ **Not supported as an operation.**

## 4. Key recovery / attacks  ← direct answer: YES, three families

| Attack | Present? | UI entry point | Backend |
|---|---|---|---|
| **Nested (mfoc)** | ✅ | MFOC读 `buttonMfoc` (tooltip 对半加密卡片进行Nested破解；**按住Ctrl点击可添加已知密钥** → `Interaction.InputBox`, remembered in `LastTryKey`); 一键解原卡 `buttonEMfoc` (copy-card wizard wrapper → same handler) | `nfc-bin/mfoc.exe` |
| **Nested with dictionary file** | ✅ | 字典测试 `buttonDictMfoc` ("导入字典文件进行Nested破解") | `mfoc.exe -f <dict>` |
| **Nested with known keys** | ✅ | 知n密 `buttonnKeysMfoc`, and 知一密破解 `buttonECmfoc` (wizard; prompts with default `FFFFFFFFFFFF`, output `Mfoc.tmp`) | `mfoc.exe -k …` |
| **Darkside (mfcuk)** | ✅ | 全加密爆破 `buttonMfcuk` (tooltip: **"对卡片执行Darkside工具（不一定成功）"**); v1.3.0 release note 加入MFCUK | `mfcuk.exe -v 3 -C -R -1 -s 250 -S 250` |
| **HardNested** | ✅ | HardNested dialog (`buttonHardNested` → `FormHardNes`), added in v1.6.2 "支持Hardnested解密"; dialog title 初始化HardNested解密, groups 目标卡-已知信息 / 目标扇区解密设置, inputs: 已知的Key (default `ffffffffffff`), 扇区号, 类型 (KeyA/KeyB), plus a second sector + KeyA/KeyB pair; `执行!` / `取消`; checkbox **只采集不计算**; warning label 连续工作时请注意设备散热！ | `nfc-bin/cropto1_bs.exe` (+ `nfc-bin/collect.exe`) |
| **Weak-PRNG / "random-number vulnerability" cards** | ✅ | Settings checkbox **单线程计算** (`checkBoxHardLowCost` / `HardLowCost`); release v1.6.5: "HardNested增加对抗随机数漏洞卡的识别" | HardNested path |
| **HardNested "cloud computing"** | ✅ (now dead) | After nonce collection the log says 您可以上传到云计算服务节点进行计算; resource `_Nonce收集完毕`. v1.6.5: "对接Hardnested云计算平台，解密更高效". Issues #13/#24/#29/#30 ask the author to publish the server-side program → the cloud service is **not** in the repo and is widely reported as offline. | author's server |
| **Encryption detection** | ✅ | 检加密 / 检测加密 `buttonCheckEncrypt` — "检测卡片加密情况" (Ctrl-click to add custom keys, v1.6.5) | `nfc-bin/mfdetect.exe` |
| Full 64-key recovery | ✅ implicitly | mfoc/mfdetect recover all sector keys; the Hex editor can then 列出全卡密钥 / 导出密钥字典 | — |
| Static-nested / darkside variants beyond mfcuk defaults | ❌ | — | — |
| Known-plaintext attack | ❌ | no evidence | — |

## 5. Magic-card ("UID卡") operations ← direct answer: YES, extensively

All via `nfc-bin/nfc-mfsetuid.exe` (block-0 image written as
`<uid4> + 2B + 08 + 0400 + 6263646566676869`, i.e. random/entered UID, BCC `0x2B`, SAK `0x08`,
ATQA `0x0400`, 8 manufacturer bytes; UI says the manufacturer is set to 复旦/Fudan).

- [x] **UID重置** (`buttonUidReset`) — reset block 0 with a **random** UID
      (`RNGCryptoServiceProvider`); "重置UID卡片0块，UID随机，厂商号为复旦".
- [x] **UID写号** (`buttonUidWrite`) — write a **user-specified** UID; prompt
      "请输入需要写入的UID卡号_共8位十六进制数_如E44A3B…", validated (`输入的UID号不合法`,
      `不恰当的4字节UID长度`).
- [x] **UID全格** (`buttonUidFormat`) — erase the whole card and re-initialise it
      (`nfc-mfsetuid.exe -f …`); tooltip: "将全卡清空并重新初始化。可用于ACbit损坏/KEY全部被改等情况的急救"
      (emergency rescue). Confirmation dialog: 该操作将会清空UID卡内全部数据_清空后不可恢复.
- [x] **锁UFUID / 锁Ufuid** (`buttonLockUfuid`, plus wizard `button4` 锁UFUID卡) —
      `nfc-mfsetuid.exe -q -l`; tooltip "锁死UFUID卡片0块数据（测试中）";
      warning 该操作将会锁死UFUID卡片_锁死后不可恢复_无法再次更改0块. v1.3.2 added it as a test feature,
      v1.6.4 "优化锁Ufuid"; user issue #32 discusses the `-l` semantics.
- [x] **UID-card read / write** (`buttonBmfRead` UID读 / `buttonBmfWrite` UID写) — `nfc-mfclassic`
      with **uppercase** modes `R A u "<file>"` / `W A u "<file>"`; wizard entries 从UID卡读回
      (`buttonEReadUID`) and 写(UF)UID卡 (`buttonEUIDWrite`) call the same handlers.
      (The uppercase R/W is a non-stock extension whose exact meaning is **unverified**; the surrounding
       UI semantics are "read/write the UID (magic) card, including block 0".)
- [x] **CUID / FUID write** (`buttonCmfWrite` 写CUID卡; wizard `buttonECuidWrite` 写C/FUID卡) —
      `nfc-mfclassic c <keytype> u "<file>"`; tooltip "写入CUID/FUID卡片（可能需要密钥文件）".
- [x] **CUID blank-card patch** — 写空卡补丁 (`checkBoxCuidKeyOver` / `CuidKeyOver`): if no key file is loaded,
      the tool builds `cuid_empty.kmf` from the card's own UID (`new S50(Utils.Hex2Block(uid,4))` →
      `ExportToMfd`) and uses it as the key file (已启用CUID空卡写入补丁; release v1.6.7 admits
      "尝试修复了CUID空卡写入少一块的bug，没有成功").
- [x] **MFF08 CUID修复** (wizard button, added v1.7.0 "加入MFF08工具") — opens `FormMFF08`
      (`buttonMFF08_Click`). Evidence of purpose: label `buttonMFF08.Text = "MFF08 CUID修复"` and resources
      无法找到MFF08程序文件_操作终止, 请选择最后一次写卡导致0块损坏的卡数据文件, and
      您没有给定最后一次写卡导致0块损坏的卡数据文件来作为写卡时的…, i.e. **repairs a CUID card whose
      block 0 was damaged by an earlier write, using the previously written dump; it requires an external
      "MFF08" program file.** The external program is not in the repo and its exact algorithm is **unverified**.
- [x] **Factory reset / unlock of a standard card**: only via UID全格 (magic cards) or 清M1 (needs keys).
      No separate "unlock command" feature.

## 6. Dump I/O, file formats, dump management

- [x] **Read full dump** and **write full dump** (see §3); 1024-byte, 64-block image.
- [x] **File extensions accepted/produced** (resource keys + filters):
      `.mfd` and `.dump` (`DUMP文件_dump_MFD文件_mfd`, `MFD文件_mfd_dump`, `MFD文件_mfd_DUMP文件_dump`) —
      v1.5.2: "全面兼容了dump文件后缀名";
      **`.mct`** MCT-format text (导入MCT格式 Ctrl+L / 导出为MCT格式 Ctrl+M, 已导出MCT文件, 请选择MCT_txt文件保存位置及文件名, `MCT格式`, `txt文件_txt`);
      **key dictionaries** `.dic` / `.txt` (字典文件_dic, 密钥字典文件_dic, 导出密钥字典).
- [ ] `.eml`, `.bin`, `.json`, `.hex`: **no evidence**.
- [x] **Auto-save with UID name** — 自动以UID名保存文件 (`checkBoxAutoSave`): saved as
      `auto_keys\<UID>_<yyyy-MM-dd_HH-mm-ss>.mfd` (已自动保存; 缓存文件异常 error path).
- [x] **Save/choose output file** — SaveFileDialog for MFD/dump/MCT/dictionary; "请选择需要写入的MFD文件".
- [x] **Dump validation** — `writecheck()` + `card.Verify()`; messages 该文件一切正常,
      该文件存在以下错误, 加载的S50卡文件大小异常, 加载的文件不存在, `_文件中的值错误`.
- [x] **Diff tool** — 差异比较 (`buttonDiffTool` → `FormDiff`), release v1.6.0 "加入差异工具",
      v1.6.1 "DiffTool增加不同块数目显示"; resource `_个块不同` ("N blocks differ");
      issue #16 complains the wording says "different rows" instead of "different sectors/blocks",
      so the diff granularity is per **block**.

## 7. Integrated Hex editor — "S50HTool-beta" (`FormHTool`)

Decoded in full from `FormHTool.resx` (dev):

- [x] Window title: **S50HTool-beta**; opening text "欢迎使用M1T的集成编辑器S50HTool！/ 打开文件请点左上角文件-打开或Ctrl+O".
- [x] Layout: `groupBox1` 扇区列表 (DataGridView, column 扇区) | `groupBox2` 扇区信息 | `groupBox3` 输出.
- [x] Per-sector editor: 第0块 / 第1块 / 第2块 hex text boxes, **KeyA**, **KeyB**, and four access-bit
      selectors: 0块权限 (comboBox4), 1块权限 (comboBox1), 2块权限 (comboBox2), Key/ACbits权限 (comboBox3).
- [x] **Access-bits calculation/decoding is a first-class feature**: 8 human-readable permission strings for
      data blocks ("KeyAB读写及增减值", "[只读]KeyAB读及减值/不可写及增值", "KeyB读写/不可增减值",
      "KeyAB读/KeyB写/不可增减值", "[只读]KeyB读/不可写及增减值", "KeyAB读及减值/KeyB写及增值",
      "[只读]锁死该扇区", …) and 8 trailer-permission strings for block 3/0
      ("[不可逆]KeyA:A写/AC:A只读/KeyB:A读写", … including one literally flagged "(重复了?)").
      Selecting a permission regenerates the AC bytes; invalid values are rejected
      (当前扇区数据仍有错误_不能执行修改).
- [x] 修改扇区(Enter) — commit the edited sector.
- [x] Menu 文件: 新建 (Ctrl+N) / 打开 (Ctrl+O) / 保存 (Ctrl+S) / 另存为 (Ctrl+Shift+S) / 退出 (Alt+X).
- [x] Menu 工具: **修改UID** (Ctrl+U), **检查全卡** (Ctrl+J), **检查并纠正全卡** (Ctrl+K),
      **导入MCT格式** (Ctrl+L), **导出为MCT格式** (Ctrl+M), **导出密钥字典** (Ctrl+N),
      **列出全卡密钥** (Ctrl+I).
- [x] Sector-level integrity: 该扇区一切正常 / 该扇区UID校验值错误_请点击打开扇区0来自动更正 /
      `_空扇区` / `_碎片扇区` / `_Sector` / `_计算得到BCC` / 已重置并新建卡 / 已更新扇区.

## 8. Dictionary (key dictionary) features

- [x] Dictionary-driven mfoc attack (字典测试) — import a `.dic`/`.txt` key list.
- [x] Built-in default dictionaries: **not present in the repo and not verified.** The tool relies on the
      user-supplied key file / dictionary and on `mfoc.exe`'s own default keys. No `keys.dic`/`*.keys` file
      exists in the file tree. (`auto_keys/` is an *output* folder for cracked dumps, not a key dictionary.)
- [x] **Key dictionary export** — 导出密钥字典 from the Hex editor (已导出密钥字典文件;
      "请选择密钥字典文件保存位置及文件名").
- [x] Key dictionary load — "请选择需要打开的密钥字典文件".
- [x] Known-key input for attacks — 知n密 / 知一密破解 / Ctrl+click on MFOC读; last input persisted
      (`Settings.LastTryKey`).
- [ ] Dictionary **editing/merging** as a dedicated editor: **no evidence** (the Hex editor only
      exports a dictionary; the generic `.dic` text file can be edited externally).

## 9. Copy-card wizard (复制卡模式) — "one-click" workflow

`tabPage2` 复制卡模式, groups: 从这里开始, [2]读取原卡, [3]写入新卡, 卡操作相关, UID/UFUID卡操作,
C/FUID卡操作, 破解工具, HardNested, 集成辅助工具. Labels 请放原卡 / 请放新卡 / 尝试一下是否成功 /
该卡种读取同普通卡 / 计时器. Buttons:

| Button | Text | Handler |
|---|---|---|
| `buttonEMfoc` | **一键解原卡** | → `buttonMfoc_Click` (verified wrapper) |
| `buttonEMfRead` | 已知密钥读 | wizard handler |
| `buttonEMfWrite` | 写入普通卡 | → `buttonMfWrite_Click` (verified) |
| `buttonEReadUID` | 从UID卡读回 | → `buttonBmfRead_Click` (verified) |
| `buttonEUIDWrite` | 写(UF)UID卡 | → `buttonBmfWrite_Click` (verified) |
| `buttonECuidWrite` | 写C/FUID卡 | → `buttonCmfWrite_Click` (verified) |
| `button4` | 锁UFUID卡 | → `buttonLockUfuid_Click` (verified) |
| `buttonECmfoc` | 知一密破解 | own handler (known-key mfoc, `Mfoc.tmp`) |
| `buttonECheckEncrypt` | 检测加密 | own handler |
| `buttonMFF08` | **MFF08 CUID修复** | opens `FormMFF08` |
| `buttonEScanCard` | 扫描卡片 | own handler |
| `buttonESelectKey` | 加载密钥… | own handler |
| `buttonEscan` | 检测连接 | → `buttonListDev_Click` (verified) |
| `buttonEStop` | 停止 | → `buttonKill_Click` (verified) |
| `button2` | (unlabeled in decoded prefix) | → `buttonMfRead_Click` (verified) |
| `buttonEAdv` | (→ advanced tab) | `tabControl1.SelectedIndex = 1` (verified) |

Tabs: `tabPage1` 高级操作模式, `tabPage2` 复制卡模式, `tabPage3` 软件设置.

## 10. Data-conversion utilities

- [x] **Access-bits (AC bits) calculation & decoding** — §7 (and `ClassMifareS50.cs` implements the model;
      `Utils.Hex2Block`, `S50.LoadFromMfd`, `S50.ExportToMfd`, `S50.Verify()` are all verified call sites in
      `Form1.cs`).
- [x] **UID input in hex** (8 hex digits), BCC handling (`_计算得到BCC`), UID ↔ dump naming.
- [ ] **UID decimal ↔ hex conversion utility**: **no evidence** (no such dialog/button/resource).
- [ ] **Wiegand 26/34 conversion**: **no evidence anywhere.**
- [ ] **Endianness / byte-order swap utility**: **no evidence.**
- [ ] **Sector/block calculator**: **no evidence** (the Hex editor simply shows sector/block structure).

## 11. Logging, records, UX, i18n, update, CLI

- [x] **Terminal/log pane** — `richTextBox1` ("Hello,cardman!"), 清终端 (clear), **存日志** (save) to
      **`m1t.log`** (`File.WriteAllText("m1t.log", logtext, Encoding.UTF8)`; 终端内容已保存至m1t_log文件).
- [x] **Terminal appearance settings** — 终端文字颜色 (`buttonCLIColor`, default display `#M1T#`) and
      终端文字大小 (`numericCLIFontSize`), persisted as `MainCLIColor` / `MainCLIFontSize`.
- [x] **Running-time timer + status bar** — `timer1_Tick`, `runTimeLabel` 计时器, `statusLabel` 就绪/运行中;
      window title reflects state (MifareOne Tool / 运行中 / 运行完毕 / 已取消 / 已终止).
- [x] **Stop a running operation** — 停运行 `buttonKill` (`_程序已被强制停止`).
- [x] **Single-instance / multi-open detection** — 您正在试图重复运行,
      您已经运行了MifareOne_Tool_打开多个本程序可能…; the 多实例运行模式 checkbox disables that check
      ("会禁用多开检测 请自行指定设备").
- [x] **Operation log prefix list** (resource keys) enumerates the supported operations:
      检测设备, 扫描卡片, 检测卡片加密, 读取卡片, 写入M1卡片, 格式化M1卡片, MFOC解密, 字典模式MFOC解密,
      全加密卡片爆破, HardNested收集数据, HardNested解密强化卡, UID卡片读取, UID卡片写入, UID卡片设定卡号,
      UID卡片全格, 重置UID卡片卡号, UFUID卡片锁定, CUID_FUID卡片写入.
- [x] **Multi-language** — 语言和地区 group, 选择界面语言 `comboBox1` with items **标准 (default/Chinese)** and
      **俄语 (Russian)**; satellite resources `Form1.ru.resx`, `Form1.zh.resx`, `Form*.ru.resx`,
      `Form*.zh.resx` + `SelectLanguage.cs` dialog. Release v1.1.1/v1.2.0 "汉化". **No English UI** —
      issues #38/#41 request it and it was never delivered.
- [x] **Update checking** — `toolStripCheckUpdate` 检查更新 + `GitHubUpdate.cs` + bundled
      `Newtonsoft.Json.dll` (queries the GitHub releases API); strings 本地版本 / `_软件版本`.
- [x] **GUI vs CLI** — GUI-first; 手动CLI opens a `cmd` in `nfc-bin` "以进行高级操作"; expert users can drive
      the bundled `nfc-*`, `mfoc`, `mfcuk`, `crypto1_bs`, `nfcUID` binaries directly.
- [ ] **Plugin system**: none. **Card-number database / records**: none (closest is `auto_keys\<UID>_*.mfd`).
- [x] **Preference persistence** — `Properties.Settings` (WriteCheck, AutoSave, AutoLoadUidKey, AutoABN,
      DefIsAdv, HardLowCost, NewScan, CuidKeyOver, MultiMode, Language, MainCLIColor, MainCLIFontSize,
      LastTryKey).

## 12. Release-timeline corroboration (features as delivered)

- v1.0.0 2018-12-22 基本功能完善; device auto-detection; split green/install editions.
- v1.1.0 停止运行 + UID写号. v1.1.1 汉化 of tool hints.
- v1.2.0 取消加载key.mfd / 不使用密钥文件 / 标题栏运行状态.
- v1.3.0 MFCUK + MFOC自定义密钥 (Ctrl+click) + 终端内显示软件版本.
- v1.3.1 fix MFCUK buffer/overwrite. v1.3.2 **CUID写入** + **UFUID锁定0块** + **清空M1卡**.
- v1.3.3 cache-file robustness.
- v1.4.0 **简单界面 (copy-card wizard)** + **ACR122U支持**.
- v1.5.0 **Hex编辑器** + **检测加密** + 运行计时.
- v1.5.2 S50HTool 检查并纠正 / 新建空文件 / MCT格式导出 / dump suffix compatibility / 写入保护.
- v1.6.0 MCT字典支持 + 差异工具 + MCT密钥字典导出 + 字典测试Key.
- v1.6.1 智能检测KeyABN + MCT text import/export + skip bad blocks and continue + DiffTool block count.
- v1.6.2 **HardNested解密**; known limitation 检测加密 incompatible with SAK28.
- v1.6.4 优化锁Ufuid, 自动载入key.mfd, 手动扫描自动显示UID卡, ACR122U/libubsb driver, 自动保存, 界面设置.
- v1.6.5 HardNested 对抗随机数漏洞卡识别 + **HardNested云计算平台** + 检测加密 Ctrl-click custom keys.
- v1.6.6 多设备支持 + 自动加载Key.mfd fix + terminal blue/white.
- v1.6.7 COM>9 fix + **CUID空卡写入少一块 bug attempted fix (unsuccessful)**.
- v1.7.0 2019-05-01 字典测试 bug fixes + **MFF08工具** + 默认打开自动检索Key (auto_keys doc).

Assets shipped: `M1T-Release.zip`, `M1T-Install.zip`, `M1T-v1.6.x.zip`, `nfc-bin.zip`, `nfc-bin_CHN.zip`,
`122-libusb.zip`, `M1T.Manual-v1.6.4-1.pdf`, `M1T-v1.6.2-1.pdf` (manuals not readable from my network).

---

## Bottom line for a "fully replicated?" comparison

**Must-have equivalents** if another tool claims parity with MifareOneTool:

1. PN532-UART auto-detect + ACR122U support (the app's only two advertised readers).
2. Classic 1K/4K (SAK 08/18/28) dump read/write/format with KeyA/KeyB/none and an "auto A/B/N" helper.
3. Magic-card suite: random UID reset, specified UID write, full erase/re-init, UFUID lock, UID-card
   R/W incl. block 0, CUID/FUID write, CUID-blank-card patch, and a CUID block-0 repair path.
4. Attacks: **nested (mfoc) incl. dictionary-file and known-key variants**, **darkside (mfcuk)**,
   **HardNested (crypto1_bs) with nonce collect-only mode and weak-PRNG card handling**, plus
   encryption detection (mfdetect).
5. Integrated S50 hex/dump editor with AC-bit pickers, whole-card check & auto-correct, UID modification,
   list-all-keys, and key-dictionary export.
6. MCT (.mct text) import/export, .mfd/.dump compatibility, auto-save named by UID + auto-load key by UID.
7. Diff tool (per-block), terminal with save-to-log, Russian+Chinese UI, GitHub update check,
   single-instance guard.

**Not in MifareOneTool** (so a replica does not need them for parity, and their presence is an *extra*):
value-block init/inc/dec/restore/transfer commands, Wiegand conversion, UID decimal/hex conversion,
endianness swap, `.eml`/`.bin`/`.json` dump formats, built-in default key dictionaries, a card database,
plugins, English localization, and any support for Ultralight/NTAG/Plus/DESFire/ISO15693 or non-PN532/ACR122U
readers such as Proxmark3, RDM880 or DenDen.
