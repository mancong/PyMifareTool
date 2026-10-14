# -*- coding: utf-8 -*-
"""
PyMifareTool - 主程序启动入口
运行方式: python main.py
"""

import sys
import os

# 确保当前项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow

def main():
    # 针对 Windows 高分辨率屏幕 (High DPI) 开启自适应平滑缩放
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    
    app = QApplication(sys.argv)
    if hasattr(Qt.HighDpiScaleFactorRoundingPolicy, "PassThrough"):
        app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app.setApplicationName("PyMifareTool")
    app.setApplicationVersion("1.0.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
