# -*- coding: utf-8 -*-
# 将 115200 下采样的位流按 38400 bps 解码

raw = bytes([0xE0, 0x1C, 0xFC, 0xFC, 0x00, 0x1C, 0xFC, 0x1C, 0xE0, 0x1C, 0xFC, 0xFC, 0x1C, 0xFC])

# 重建物理线电平序列
bits = []
for b in raw:
    bits.append(0) # Start bit
    for i in range(8):
        bits.append((b >> i) & 1)
    bits.append(1) # Stop bit

# 以 3 为基准采样时钟寻找最佳相位 (0, 1, 2)
for phase in [0, 1, 2]:
    downsampled = []
    i = phase
    while i < len(bits):
        downsampled.append(bits[i])
        i += 3
    
    # 尝试按 8N1 解析 downsampled
    # 寻找 Start bit (0)
    pos = 0
    decoded_bytes = []
    while pos + 10 <= len(downsampled):
        # 寻找下一个 0 (Start bit)
        if downsampled[pos] == 0:
            val = 0
            for b in range(8):
                val |= (downsampled[pos + 1 + b] << b)
            stop = downsampled[pos + 9]
            decoded_bytes.append((val, stop))
            pos += 10
        else:
            pos += 1
            
    print(f"\n--- Phase {phase} ---")
    print(f"Decoded bytes count: {len(decoded_bytes)}")
    hex_str = " ".join(f"{v:02X}" for v, s in decoded_bytes)
    print(f"HEX: {hex_str}")
    asc_str = "".join(chr(v) if 32 <= v <= 126 else "." for v, s in decoded_bytes)
    print(f"ASC: {asc_str}")
