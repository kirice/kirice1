import threading
import time
from abc import ABC, abstractmethod

class BaseBot(ABC):
    def __init__(self, hwnd, log_callback, config):
        self.hwnd = hwnd
        self.log = log_callback
        self.config = config
        self._stop_flag = False
        self._thread = None
        self._paused = False

    @abstractmethod
    def run_logic(self):
        pass

    def start(self):
        if self._thread and self._thread.is_alive():
            self.log("⚠️ Бот уже запущен")
            return
        self._stop_flag = False
        self._paused = False
        self._thread = threading.Thread(target=self._run_wrapper, daemon=True)
        self._thread.start()
        self.log("🟢 Бот запущен")

    def _run_wrapper(self):
        try:
            self.run_logic()
        except Exception as e:
            self.log(f"❌ Ошибка в боте: {e}")
        finally:
            self.log("🛑 Бот завершил работу")

    def stop(self):
        self.log("⏹️ Остановка бота...")
        self._stop_flag = True
        if self._thread:
            self._thread.join(timeout=2.0)

    def toggle_pause(self):
        self._paused = not self._paused
        self.log("⏸️ Пауза" if self._paused else "▶️ Продолжено")