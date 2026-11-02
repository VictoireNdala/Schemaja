"""Schémaja — installeur de polices en masse pour Windows et Linux (PySide6).

Usage :
    python gui.py
"""
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

ICON_PATH = Path(__file__).parent / "assets" / "icon.ico"


def main() -> None:
    # sys.stdout est None en build PyInstaller --windowed (pas de console).
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8")

    if sys.platform not in ("win32", "linux"):
        print("Cet outil est pris en charge sous Windows et Linux.")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
