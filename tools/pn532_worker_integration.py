# -*- coding: utf-8 -*-
"""
PyMifareTool - 真实运行时链路联调脚本 (SerialWorker + CardOperationWorker)
用法: python tools/pn532_worker_integration.py [COM3] [read|crack]
走 main.py 相同的 QThread 异步路径，验证后台轮询/独占/读卡/破解的真实集成。
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from core.services.serial_worker import SerialWorker
from core.services.card_worker import CardOperationWorker, DEFAULT_KEYS_HEX
from core.models.dump import BlockState


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
    op_arg = sys.argv[2] if len(sys.argv) > 2 else "read"
    op = {"read": "read_card", "crack": "crack_keys"}.get(op_arg, op_arg)

    app = QApplication(sys.argv)
    sw = SerialWorker(port=port, baudrate=115200, device_type="pn532")
    if os.environ.get("LOGDEBUG") == "1":
        sw.set_debug_logging(True)
    if os.environ.get("AUTOPOLL") == "1":
        sw.set_auto_poll(True)
    if os.environ.get("AUTOPOLL") == "1":
        sw.set_auto_poll(True)
        sw.set_poll_interval(500)
    state = {"card_seen": None, "worker": None, "done": False, "tx": 0, "rx": 0, "frame": 0}

    def on_raw(direction, msg):
        if direction == "TX":
            state["tx"] += 1
        elif direction == "RX":
            state["rx"] += 1
        elif direction == "FRAME":
            state["frame"] += 1

    def log(m):
        print(f"  [log] {m}", flush=True)

    def on_connected(p, b):
        print(f"[SIG] connected: {p} @ {b}", flush=True)
        QTimer.singleShot(1200, start_op)

    def on_identified(name, fw):
        print(f"[SIG] identified: {name} | {fw}", flush=True)

    def on_swiped(info):
        if not state["card_seen"]:
            state["card_seen"] = info
            print(f"[SIG] card_swiped UID={info.get('uid_hex') or info.get('uid_bytes', b'').hex().upper()} "
                  f"SAK={info.get('sak')}", flush=True)

    def on_removed():
        print("[SIG] card_removed", flush=True)

    def start_op():
        if not state["card_seen"]:
            print("[WARN] 后台轮询未捕获卡片，仍尝试操作", flush=True)
        cw = CardOperationWorker(sw, op, custom_keys=DEFAULT_KEYS_HEX, concurrency=4)
        state["worker"] = cw
        cw.sig_log.connect(log)
        cw.sig_sector_cracked.connect(lambda s, a, b: print(f"  [crack] S{s:02d} A={a} B={b}", flush=True))
        cw.sig_finished.connect(on_finished)
        print(f"==== 启动 CardOperationWorker op={op} ====", flush=True)
        cw.start()

    def on_finished(ok, msg, data):
        print(f"[FINISHED] ok={ok} | {msg}", flush=True)
        if op == "read" and data is not None and hasattr(data, "block_count"):
            ok_blocks = sum(1 for b in range(data.block_count)
                            if data.get_block_state(b) == BlockState.READ_OK)
            print(f"  dump.block_count={data.block_count} | READ_OK 块数={ok_blocks}", flush=True)
            print(f"  Block0={data.get_block(0).hex().upper()}", flush=True)
        elif op == "crack" and isinstance(data, dict):
            solved = sum(1 for v in data.values() if v.get("key_a") != "未破解")
            print(f"  成功扇区数={solved}/{len(data)}", flush=True)
        print(f"  raw_log 统计: TX={state['tx']} RX={state['rx']} FRAME={state['frame']}", flush=True)
        QTimer.singleShot(300, finish)

    def finish():
        sw.stop()
        app.quit()

    sw.sig_connected.connect(on_connected)
    sw.sig_device_identified.connect(on_identified)
    sw.sig_card_swiped.connect(on_swiped)
    sw.sig_card_removed.connect(on_removed)
    sw.sig_raw_log.connect(on_raw)
    print(f"# 端口 {port} 运行时链路联调 (device_type=pn532)", flush=True)
    sw.start()

    QTimer.singleShot(45000, finish)
    app.exec()


if __name__ == "__main__":
    main()
