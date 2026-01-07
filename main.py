import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QLoggingCategory
from src.ui.main_window import MainWindow

# Suppress annoying Qt warnings
QLoggingCategory.setFilterRules("qt.gui.imageio.jpeg.warning=false")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
