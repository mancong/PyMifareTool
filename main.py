# -*- coding: utf-8 -*-
"""
PyMifareTool - 主程序启动入口
运行方式: python main.py
"""

import sys
import os
import tempfile

# 避免 Matplotlib 在受限 Windows 主目录下创建缓存报 [WinError 5] 拒绝访问
if "MPLCONFIGDIR" not in os.environ:
    os.environ["MPLCONFIGDIR"] = os.path.join(tempfile.gettempdir(), "matplotlib")

# 确保当前项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 针对 Windows 任务栏独立图标绑定专属 AppUserModelID (防止任务栏显示 Python 默认图标)
if sys.platform.startswith("win"):
    try:
        import ctypes
        app_id = "PyMifareTool.RFID.NFC.DesktopApp.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow


def main():
    # 针对 Windows 高分辨率屏幕 (High DPI) 开启自适应平滑缩放
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    if hasattr(Qt.HighDpiScaleFactorRoundingPolicy, "PassThrough"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)

    app.setApplicationName("PyMifareTool")
    app.setApplicationVersion("1.0.0")

    # 全局设置应用图标 (窗口左上角与系统任务栏图标)
    icon_png = os.path.join(project_root, "ui", "resources", "app_icon.png")
    icon_ico = os.path.join(project_root, "ui", "resources", "app_icon.ico")
    icon_file = icon_ico if (sys.platform.startswith("win") and os.path.exists(icon_ico)) else icon_png
    if os.path.exists(icon_file):
        app.setWindowIcon(QIcon(icon_file))

    font = app.font()
    if font.pointSizeF() <= 0 and font.pixelSize() <= 0:
        font.setPointSize(10)
        app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
