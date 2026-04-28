import sys
import os
import subprocess
import win32gui
import win32con
import threading
import glob
import time
import psutil
import importlib
from PyQt5.QtCore import QTimer, pyqtSignal, QObject, Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QTextEdit,
    QVBoxLayout, QHBoxLayout, QWidget, QComboBox, QFrame,
    QLineEdit, QTabWidget
)
from PyQt5.QtGui import QFont

# ==============================================================================
# Определение корня проекта (работает и в .exe)
# ==============================================================================
def get_project_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

project_root = get_project_root()
sys.path.insert(0, project_root)

# ==============================================================================
# LogEmitter
# ==============================================================================
class LogEmitter(QObject):
    log = pyqtSignal(str)

# ==============================================================================
# MainWindow
# ==============================================================================
class MainWindow(QMainWindow):
    gui_ready = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Rucoy Online — Бот с ИИ-ходьбой")
        self.setMinimumSize(1000, 600)
        self.setStyleSheet("font-family: Arial; background: #1e1e1e; color: white;")

        self.hwnd = None
        self.bot = None
        self.bot_thread = None
        self.game_process = None
        self.game_pid = None
        self.bot_modules = {}

        self.log_emitter = LogEmitter()
        self.log_emitter.log.connect(self.update_console)

        self.init_ui()
        self.load_available_bots()
        self.load_available_maps()
        self.start_game()

        QTimer.singleShot(100, self.showMaximized)
        QTimer.singleShot(200, self.gui_ready.emit)

    def get_timestamp(self):
        return time.strftime("%H:%M:%S")

    def log(self, message):
        timestamp = self.get_timestamp()
        full_msg = f"[{timestamp}] {message}"
        self.log_emitter.log.emit(full_msg)
        print(full_msg)

    def update_console(self, message):
        is_game_action = any(kw in message.lower() for kw in [
            "атака", "зелье", "клик", "здоровье", "мана", "найдены",
            "пью", "обнаружен", "пополнение", "использую", "движение"
        ])
        if is_game_action:
            self.player_console.append(message)
            if self.tab_widget.currentWidget() == self.player_tab:
                self.player_console.verticalScrollBar().setValue(
                    self.player_console.verticalScrollBar().maximum()
                )
        else:
            self.dev_console.append(message)
            if self.tab_widget.currentWidget() == self.dev_tab:
                self.dev_console.verticalScrollBar().setValue(
                    self.dev_console.verticalScrollBar().maximum()
                )

    def init_ui(self):
        main_layout = QHBoxLayout()

        console_widget = QWidget()
        console_layout = QVBoxLayout()

        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabBar::tab { font-size: 10px; padding: 4px; }
            QTabWidget::pane { border: 1px solid #333; }
        """)

        self.player_console = QTextEdit()
        self.player_console.setReadOnly(True)
        self.player_console.setStyleSheet("""
            background-color: #000;
            color: #0f0;
            font-family: 'Courier New', monospace;
            font-size: 11px;
            border: 1px solid #333;
        """)
        self.player_tab = QWidget()
        QVBoxLayout(self.player_tab).addWidget(self.player_console)
        self.tab_widget.addTab(self.player_tab, "🎮 Игрок")

        self.dev_console = QTextEdit()
        self.dev_console.setReadOnly(True)
        self.dev_console.setStyleSheet("""
            background-color: #111;
            color: #0ff;
            font-family: 'Courier New', monospace;
            font-size: 11px;
            border: 1px solid #333;
        """)
        self.dev_tab = QWidget()
        QVBoxLayout(self.dev_tab).addWidget(self.dev_console)
        self.tab_widget.addTab(self.dev_tab, "👨‍💻 Dev")

        scroll_style = """
            QScrollBar:vertical { background: #2b2b2b; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #444; min-height: 20px; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #666; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """
        self.player_console.verticalScrollBar().setStyleSheet(scroll_style)
        self.dev_console.verticalScrollBar().setStyleSheet(scroll_style)

        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Введите команду (например: run_bot)...")
        self.cmd_input.setStyleSheet("""
            background: #2b2b2b; color: white; padding: 5px;
            border: 1px solid #444; border-radius: 4px;
        """)

        clear_btn = QPushButton("Очистить")
        clear_btn.setFixedWidth(80)
        clear_btn.setStyleSheet("""
            font-size: 9px; padding: 2px; background: #333;
            color: white; border: 1px solid #555; border-radius: 4px;
        """)

        console_layout.addWidget(self.tab_widget)
        console_layout.addWidget(self.cmd_input)
        console_layout.addWidget(clear_btn)
        console_widget.setLayout(console_layout)
 
        right_widget = QWidget()
        right_layout = QVBoxLayout()

        control_frame = QFrame()
        control_frame.setFixedHeight(30)
        control_frame.setStyleSheet("background: #2d2d2d; border-radius: 4px; padding: 0px;")
        control_layout = QHBoxLayout()
        control_layout.setSpacing(2)
        control_layout.setContentsMargins(4, 2, 4, 2)

        normal_style = "font-size: 10px; min-height: 20px; height: 20px; padding: 2px; margin: 0px;"
        label_style = "font-size: 10px; min-height: 20px; height: 20px; padding: 2px; margin: 0px; color: #ccc;"
        btn_style = "font-size: 9px; font-weight: bold; min-height: 20px; height: 20px; padding: 2px;"

        label_bot = QLabel("Бот:")
        label_bot.setStyleSheet(label_style)
        self.bot_combo = QComboBox()
        self.bot_combo.setStyleSheet("background: white; color: black;" + normal_style)

        label_map = QLabel("Карта:")
        label_map.setStyleSheet(label_style)
        self.map_combo = QComboBox()
        self.map_combo.setStyleSheet("background: white; color: black;" + normal_style)

        label_cmd = QLabel("Команда:")
        label_cmd.setStyleSheet(label_style)
        self.cmd_combo = QComboBox()
        self.cmd_combo.setStyleSheet("background: white; color: black;" + normal_style)

        self.start_btn = QPushButton("▶️ Запустить")
        self.stop_btn = QPushButton("⏹️ Остановить")
        self.send_cmd_btn = QPushButton("📤 Выполнить")
        self.start_btn.setStyleSheet("background: #4CAF50; color: white;" + btn_style)
        self.stop_btn.setStyleSheet("background: #f44336; color: white;" + btn_style)
        self.send_cmd_btn.setStyleSheet("background: #2196F3; color: white;" + btn_style)

        control_layout.addWidget(label_bot)
        control_layout.addWidget(self.bot_combo)
        control_layout.addWidget(label_map)
        control_layout.addWidget(self.map_combo)
        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addWidget(label_cmd)
        control_layout.addWidget(self.cmd_combo)
        control_layout.addWidget(self.send_cmd_btn)
        control_frame.setLayout(control_layout)

        self.game_container = QWidget()
        self.game_container.setStyleSheet("background-color: #333; border: 1px solid #555;")
        self.game_container.setMinimumSize(800, 600)

        right_layout.addWidget(control_frame)
        right_layout.addWidget(self.game_container)
        right_widget.setLayout(right_layout)

        main_layout.addWidget(console_widget, stretch=3)
        main_layout.addWidget(right_widget, stretch=7)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.start_btn.clicked.connect(self.on_start_bot)
        self.stop_btn.clicked.connect(self.on_stop_bot)
        self.send_cmd_btn.clicked.connect(self.on_send_command)
        self.cmd_input.returnPressed.connect(self.on_send_command_from_input)
        clear_btn.clicked.connect(self.clear_consoles)

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_game_window)
        self.update_command_list()

    def clear_consoles(self):
        self.player_console.clear()
        self.dev_console.clear()

    def update_command_list(self):
        base_commands = ["run_bot", "stop_bot", "restart_bot", "status", "help"]
        self.cmd_combo.clear()
        self.cmd_combo.addItems(base_commands)
        self.log(f"🔧 Загружены базовые команды: {', '.join(base_commands)}")
        if self.bot and hasattr(self.bot, 'available_commands'):
            bot_commands = [cmd for cmd in self.bot.available_commands if cmd not in base_commands]
            if bot_commands:
                self.log(f"🤖 Бот добавил команды: {', '.join(bot_commands)}")
                self.cmd_combo.addItems(bot_commands)

    def load_available_bots(self):
        bots_dir = os.path.join(project_root, "bots")
        if not os.path.exists(bots_dir):
            self.log("⚠️ Папка bots/ не найдена")
            return
        bot_files = [f for f in os.listdir(bots_dir) if f.endswith(".py") and f != "__init__.py"]
        available_bots = []
        for file in bot_files:
            module_name = file[:-3]
            module_path = os.path.join(bots_dir, file)
            try:
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, module_name):
                    available_bots.append(module_name)
                    self.bot_modules[module_name] = module
            except Exception as e:
                self.log(f"❌ Ошибка загрузки бота {module_name}: {e}")
        self.bot_combo.clear()
        self.bot_combo.addItems(sorted(available_bots))
        self.log(f"🤖 Найдено ботов: {len(available_bots)}")

    def load_available_maps(self):
        # ✅ ИСПРАВЛЕНО: Ищем в корне проекта (models/ и maps/)
        maps_dir = os.path.join(project_root, "maps")
        if not os.path.exists(maps_dir):
            os.makedirs(maps_dir, exist_ok=True)
            self.log("⚠️ Папка maps/ создана в корне проекта")
        pkl_files = glob.glob(os.path.join(maps_dir, "*.pkl"))
        pth_files = glob.glob(os.path.join(maps_dir, "*.pth"))
        onnx_files = glob.glob(os.path.join(maps_dir, "*.onnx"))
        all_files = pkl_files + pth_files + onnx_files
        map_names = sorted(set(os.path.splitext(os.path.basename(f))[0] for f in all_files))
        self.map_combo.clear()
        self.map_combo.addItems(map_names)
        self.log(f"📂 Найдено карт: {len(map_names)}")

    def start_game(self):
        self.log("🎮 Запускаю BlueStacks...")
        try:
            command = r'"C:\Program Files\BlueStacks_nxt\HD-Player.exe" --instance Pie64 --cmd launchAppWithBsx --package "com.mmo.android" --source desktop_shortcut'
            self.game_process = subprocess.Popen(command, shell=False)
            self.game_pid = self.game_process.pid
            self.log(f"✅ Игра запущена (PID: {self.game_pid})")
            self.timer.start(10000)
        except Exception as e:
            self.log(f"❌ Ошибка запуска игры: {e}")

    def find_game_window(self):
        def callback(hwnd, hwnds):
            text = win32gui.GetWindowText(hwnd)
            if "BlueStacks" in text or "Rucoy" in text:
                if win32gui.IsWindowVisible(hwnd):
                    hwnds.append(hwnd)
            return True
        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        return hwnds[0] if hwnds else None

    def check_game_window(self):
        hwnd = self.find_game_window()
        if hwnd:
            self.hwnd = hwnd
            self.timer.stop()
            self.embed_game_window()

    def embed_game_window(self):
        hwnd = self.hwnd
        if not hwnd:
            return
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 0, 0, 1333, 775, win32con.SWP_NOZORDER)
            container_id = int(self.game_container.winId())
            if container_id == 0:
                self.log("❌ Ошибка: winId() контейнера равен 0.")
                return
            win32gui.SetParent(hwnd, container_id)
            self.log("✅ Окно игры встроено в GUI")
        except Exception as e:
            self.log(f"❌ Ошибка встраивания окна: {e}")

    def on_start_bot(self):
        if not self.hwnd:
            self.log("❌ Окно игры не найдено!")
            return
        bot_name = self.bot_combo.currentText()
        map_name = self.map_combo.currentText()
        self.log(f"🤖 Запуск бота: <b>{bot_name}</b> | Карта: <b>{map_name}</b>")
        if self.bot_thread and self.bot_thread.is_alive():
            self.log("ℹ️ Бот уже работает.")
            return
        try:
            if bot_name not in self.bot_modules:
                self.log(f"❌ Бот '{bot_name}' не загружен.")
                return
            module = self.bot_modules[bot_name]
            BotClass = getattr(module, bot_name)
            self.bot = BotClass(self.hwnd, log_callback=self.log, map_name=map_name)
            target = getattr(self.bot, "run", None) or getattr(self.bot, "explore_current_zone", None)
            if not target:
                self.log(f"❌ У бота {bot_name} нет метода run или explore_current_zone")
                return
            self.bot_thread = threading.Thread(target=target, daemon=True)
            self.bot_thread.start()
            self.log("🟢 Бот успешно запущен в фоновом потоке.")
            self.update_command_list()
        except Exception as e:
            self.log(f"❌ Ошибка при запуске бота: {e}")

    def on_stop_bot(self):
        if self.bot:
            try:
                self.bot.stop()
                self.log("🛑 Бот остановлен.")
            except Exception as e:
                self.log(f"⚠️ Ошибка при остановке бота: {e}")
            self.bot = None
            self.bot_thread = None
        else:
            self.log("ℹ️ Бот не запущен.")

    def safe_execute(self, func):
        try:
            func()
        except Exception as e:
            self.log(f"❌ Ошибка при выполнении команды: {e}")

    def on_send_command(self):
        cmd = self.cmd_combo.currentText().strip()
        self.on_execute_command(cmd)

    def on_send_command_from_input(self):
        cmd = self.cmd_input.text().strip()
        self.cmd_input.clear()
        self.on_execute_command(cmd)

    def on_execute_command(self, cmd):
        if not cmd:
            return
        self.log(f"⚙️ Выполняю команду: <b>{cmd}</b>")
        if cmd == "help":
            self.log("📌 Доступные команды:")
            for i in range(self.cmd_combo.count()):
                c = self.cmd_combo.itemText(i)
                self.log(f"  • {c}")
            return
        if cmd == "status":
            self.log("✅ Бот запущен" if self.bot else "🔴 Бот не запущен")
            return
        if cmd == "run_bot":
            self.on_start_bot()
            return
        if cmd == "stop_bot":
            self.on_stop_bot()
            return
        if cmd == "restart_bot":
            self.on_stop_bot()
            self.on_execute_command("run_bot")
            return
        if not self.bot:
            self.log("❌ Нет активного бота. Сначала запустите бота.")
            return
        if hasattr(self.bot, cmd) and callable(getattr(self.bot, cmd)):
            method = getattr(self.bot, cmd)
            threading.Thread(target=self.safe_execute, args=(method,), daemon=True).start()
        else:
            self.log(f"❌ Неизвестная команда: {cmd}")

    def closeEvent(self, event):
        self.log("🛑 Закрытие приложения...")
        self.on_stop_bot()
        if self.game_pid:
            try:
                proc = psutil.Process(self.game_pid)
                proc.terminate()
                proc.wait(timeout=5)
                self.log("✅ BlueStacks закрыт.")
            except Exception as e:
                self.log(f"⚠️ Не удалось закрыть BlueStacks: {e}")
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()