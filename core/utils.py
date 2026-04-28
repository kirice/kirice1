import sys
import os
import mss
import cv2
import numpy as np

def get_project_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_monitor_region(hwnd=None):
    # Заглушка, можно расширить для получения координат окна
    return {"top": 126, "left": 596, "width": 1300, "height": 731}

def capture_screen(monitor):
    with mss.mss() as sct:
        arr = np.array(sct.grab(monitor))
        return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)