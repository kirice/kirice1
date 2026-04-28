import sys
import os

# Исправление путей для работы после сборки в .exe
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
    if os.path.exists(os.path.join(application_path, 'config.json')):
        os.chdir(application_path)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, application_path)

from PyQt5.QtWidgets import QApplication
from gui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()