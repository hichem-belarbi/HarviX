import sys
from PyQt5.QtWidgets import QApplication, QSplashScreen
from PyQt5.QtGui import QPixmap
import os
from main_window import MainWindow
from utils.styles import STYLE_APP

if __name__ == "__main__":
    app = QApplication(sys.argv)
    icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    splash = QSplashScreen(QPixmap(os.path.join(icons_dir, "splash.png")).scaled(960, 540))
    splash.show()
    app.processEvents()

    app.setStyle("Fusion")
    app.setStyleSheet(STYLE_APP)

    window = MainWindow()

    splash.finish(window)

    window.show()
    sys.exit(app.exec_())