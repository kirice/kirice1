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

from gui.splash_screen import run_with_splash

def main():
    run_with_splash()

if __name__ == "__main__":
    main()