# -*- coding: utf-8 -*-
# 分析捕获到的 14 字节波形与位时序

raw = bytes([0xE0, 0x1C, 0xFC, 0xFC, 0x00, 0x1C, 0xFC, 0x1C, 0xE0, 0x1C, 0xFC, 0xFC, 0x1C, 0xFC])

# 还原 UART 物理线上真实的电平序列 (Start=0, 8 data bits LSB first, Stop=1)
bits = []
for b in raw:
    bits.append(0) # Start bit
    for i in range(8):
        bits.append((b >> i) & 1)
    bits.append(1) # Stop bit

print(f"总位流长度: {len(bits)} bits (@ 115200 bps)")

# 计算每个高电平和低电平连续保持的时钟周期数 (Run-Length Encoding)
rle = []
curr = bits[0]
count = 0
for bit in bits:
    if bit == curr:
        count += 1
    else:
        rle.append((curr, count))
        curr = bit
        count = 1
rle.append((curr, count))

print("\n连续电平保持周期 (电平, 持续115200时钟数):")
print(rle)

# 寻找最小脉冲宽度 (基准位宽度)
widths = [count for val, count in rle]
print(f"\n脉冲宽度集合: {sorted(set(widths))}")
