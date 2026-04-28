import os
import sys
import time
import cv2
import mss
import numpy as np
import pyautogui
import keyboard

# ==============================================================================
# ✅ БЕЗОПАСНЫЙ ИМПОРТ (чтобы бот грузился даже если torch сломан)
# ==============================================================================
TORCH_AVAILABLE = False
ULTRALYTICS_AVAILABLE = False
try:
    import torch
    import torch.nn as nn
    from torchvision import models
    TORCH_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Torch не загрузился: {e}")
    TORCH_AVAILABLE = False

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Ultralytics не загрузился: {e}")
    ULTRALYTICS_AVAILABLE = False

# ==============================================================================
# WalkingAI (Загрузка модели ходьбы)
# ==============================================================================
if TORCH_AVAILABLE:
    class WalkingAI:
        def __init__(self, monitor, log_callback=None, map_name="lizard_dungeon"):
            self.monitor = monitor
            self.log = log_callback or (lambda msg: print(f"[WalkingAI] {msg}"))
            self.map_name = map_name
            
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.model_path = os.path.join(project_root, "maps", f"{map_name}.pth")
            
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            self.build_model()
            self.load_model()

        def build_model(self):
            self.model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
            self.model.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3, bias=False)
            self.model.fc = nn.Sequential(
                nn.Dropout(0.5),
                nn.Linear(512, 128),
                nn.ReLU(),
                nn.Linear(128, 2)
            )
            self.model.to(self.device)

        def load_model(self):
            if os.path.exists(self.model_path):
                try:
                    self.model.load_state_dict(torch.load(self.model_path, map_location=self.device))
                    self.model.eval()
                    self.log("✅ Модель ходьбы загружена")
                    return True
                except Exception as e:
                    self.log(f"❌ Ошибка загрузки модели: {e}")
                    return False
            else:
                self.log(f"❌ Файл модели не найден: {self.model_path}")
                return False

        def predict_click(self):
            with mss.mss() as sct:
                img = np.array(sct.grab(self.monitor))
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                img = cv2.resize(img, (224, 224)).astype(np.float32) / 255.0
                img = np.transpose(img, (2, 0, 1))
                X = torch.FloatTensor(img).unsqueeze(0).to(self.device)
                self.model.eval()
                with torch.no_grad():
                    dx, dy = self.model(X).cpu().numpy()[0] * 300
                screen_x = int(self.monitor["left"] + self.monitor["width"] // 2 + dx)
                screen_y = int(self.monitor["top"] + self.monitor["height"] // 2 + dy)
                return screen_x, screen_y
else:
    class WalkingAI:
        def __init__(self, *a, **kw):
            self.log = lambda msg: print(msg)
        def load_model(self): return False
        def predict_click(self): return 100, 100

# ==============================================================================
# ГЛАВНЫЙ КЛАСС БОТА
# ==============================================================================
class RunBot:
    available_commands = [
        "enable_auto_walk",
        "disable_auto_walk",
        "enable_heal_only",
        "disable_heal_only"
    ]

    def __init__(self, hwnd, log_callback=None, map_name="lizard_dungeon"):
        self.hwnd = hwnd
        self.log = log_callback or (lambda msg: print(f"[RunBot] {msg}"))
        self.map_name = map_name
        self.running = True
        self.paused = False

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        models_dir = os.path.join(project_root, "models")
        maps_dir = os.path.join(project_root, "maps")
        
        self.MODEL_PATH = os.path.join(models_dir, "lizard1_5.pt")
        
        self.CONF_THRESHOLD = 0.1
        self.KEY_ATTACK = '7'
        self.KEY_HP_POTION = '5'
        self.KEY_MP_POTION = '6'
        self.HP_PIXEL_COORD = (920, 140)
        self.MANA_PIXEL_COORD = (920, 170)
        self.LOW_COLOR = (107, 105, 107)
        self.POTION_COOLDOWN = 1.0
        self.ATTACK_COOLDOWN = 1.0
        self.CHECK_INTERVAL = 0.1
        self.last_potion_time = 0
        self.last_attack_time = 0
        
        # ✅ НОВОЕ: Настройки для поиска 8.png
        self.last_8_press_time = 0
        self.KEY_8_COOLDOWN = 0.3  # Задержка между нажатиями (сек)
        self.IMG_8_THRESHOLD = 0.8 # Порог совпадения (0.0 - 1.0)
        self.template_8 = None
        self.load_8_template()

        self.MONITOR = {"top": 126, "left": 596, "width": 1300, "height": 731}

        self.model = None
        self.load_yolo()

        if TORCH_AVAILABLE:
            self.walking_ai = WalkingAI(self.MONITOR, log_callback=self.log, map_name=map_name)
            self.WALK_ENABLED = False
            self.last_walk_click = 0
            self.WALK_INTERVAL = 0.3
        else:
            self.walking_ai = None
            self.WALK_ENABLED = False
            self.log("⚠️ PyTorch не доступен — ходьба отключена")

        self.HEAL_ONLY_MODE = False
        self.setup_hotkeys()

    def setup_hotkeys(self):
        def toggle_pause():
            self.paused = not self.paused
            self.log("⏸️ Пауза активирована" if self.paused else "▶️ Бот возобновлен")
        
        def stop_bot():
            self.stop()
            self.log("🛑 Бот остановлен по Ctrl+Shift")
            
        def toggle_heal_only():
            if self.HEAL_ONLY_MODE:
                self.disable_heal_only()
            else:
                self.enable_heal_only()
                
        try:
            keyboard.add_hotkey('F9', toggle_pause)
            keyboard.add_hotkey('ctrl+shift', stop_bot)
            keyboard.add_hotkey('F10', toggle_heal_only)
        except Exception as e: 
            self.log(f"⚠️ Не удалось установить хоткеи: {e}")

    def load_yolo(self):
        if ULTRALYTICS_AVAILABLE and os.path.exists(self.MODEL_PATH):
            try:
                self.model = YOLO(self.MODEL_PATH)
                self.log("✅ Модель YOLO загружена")
            except Exception as e:
                self.log(f" Ошибка загрузки YOLO: {e}")
        else:
            self.log("⚠️ YOLO модель не найдена или ultralytics не установлен")

    # ✅ НОВОЕ: Загрузка шаблона 8.png
    def load_8_template(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        img_path = os.path.join(project_root, "assets", "8.png")
        if os.path.exists(img_path):
            self.template_8 = cv2.imread(img_path)
            if self.template_8 is not None:
                # Приводим к 3 каналам, если скриншот сохранён с альфа-каналом
                if self.template_8.shape[2] == 4:
                    self.template_8 = cv2.cvtColor(self.template_8, cv2.COLOR_BGRA2BGR)
                self.log("✅ Шаблон 8.png успешно загружен")
            else:
                self.log("❌ Ошибка чтения файла 8.png")
        else:
            self.log(f"❌ Файл не найден: {img_path}")

    def get_pixel_color(self, coords):
        try:
            return pyautogui.screenshot(region=(*coords, 1, 1)).getpixel((0, 0))
        except Exception as e:
            self.log(f"Ошибка чтения пикселя: {e}")
            return (0, 0, 0)

    def use_health_potion(self):
        if self.paused or keyboard.is_pressed('shift'):
            return
        current_time = time.time()
        if current_time - self.last_potion_time >= self.POTION_COOLDOWN:
            color = self.get_pixel_color(self.HP_PIXEL_COORD)
            if np.allclose(color, self.LOW_COLOR, atol=10):
                self.log("💊 Здоровье низкое! Пью зелье (5)")
                pyautogui.press(self.KEY_HP_POTION)
                self.last_potion_time = current_time

    def use_mana_potion(self):
        if self.paused or keyboard.is_pressed('shift'):
            return
        current_time = time.time()
        if current_time - self.last_potion_time >= self.POTION_COOLDOWN:
            color = self.get_pixel_color(self.MANA_PIXEL_COORD)
            if np.allclose(color, self.LOW_COLOR, atol=10):
                self.log(" Мана низкая! Пью зелье (6)")
                pyautogui.press(self.KEY_MP_POTION)
                self.last_potion_time = current_time

    def detect_and_attack(self):
        if self.HEAL_ONLY_MODE:
            return
        if not self.model or self.paused or keyboard.is_pressed('shift'):
            return
        with mss.mss() as sct:
            frame = np.array(sct.grab(self.MONITOR))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            results = self.model(frame, imgsz=320, conf=self.CONF_THRESHOLD, verbose=False)
            found_any = False
            detected_classes = []
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = self.model.names[cls_id]
                    detected_classes.append(cls_name)
                    found_any = True
            if found_any:
                unique_classes = set(detected_classes)
                self.log(f"👀 Найдены объекты: {', '.join(unique_classes)}")
            current_time = time.time()
            if found_any and (current_time - self.last_attack_time) > self.ATTACK_COOLDOWN:
                pyautogui.press(self.KEY_ATTACK)
                self.last_attack_time = current_time
                self.log("🔥 Обнаружен персонаж! Атака (7)")

    def auto_walk(self):
        if not self.WALK_ENABLED or self.paused or keyboard.is_pressed('shift'):
            return
        if not self.walking_ai:
            return
        current_time = time.time()
        if current_time - self.last_walk_click > self.WALK_INTERVAL:
            try:
                x, y = self.walking_ai.predict_click()
                pyautogui.click(x, y)
                self.last_walk_click = current_time
                self.log(f"👣 Клик в ({x}, {y})")
            except Exception as e:
                self.log(f"❌ Ошибка клика: {e}")

    def enable_auto_walk(self):
        if not TORCH_AVAILABLE:
            self.log("❌ Не хватает зависимостей (PyTorch)")
            return
        if hasattr(self, 'walking_ai') and self.walking_ai and self.walking_ai.load_model():
            self.WALK_ENABLED = True
            self.log("✅ Автоход включён")
        else:
            self.log("❌ Не удалось загрузить модель ходьбы")

    def disable_auto_walk(self):
        self.WALK_ENABLED = False
        self.log("🛑 Автоход остановлен")

    def enable_heal_only(self):
        self.HEAL_ONLY_MODE = True
        self.log("️ Режим 'Только лечение' включён (атака отключена)")

    def disable_heal_only(self):
        self.HEAL_ONLY_MODE = False
        self.log("⚔️ Режим 'Только лечение' выключён (атака включена)")

    # ✅ НОВОЕ: Поиск картинки и нажатие 8
    def detect_and_press_8(self):
        if self.paused or keyboard.is_pressed('shift') or self.template_8 is None:
            return
        
        current_time = time.time()
        if current_time - self.last_8_press_time < self.KEY_8_COOLDOWN:
            return

        with mss.mss() as sct:
            frame = np.array(sct.grab(self.MONITOR))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # Сопоставление шаблона
            res = cv2.matchTemplate(frame, self.template_8, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if max_val >= self.IMG_8_THRESHOLD:
                x, y = max_loc
                h, w = self.template_8.shape[:2]
                center_x, center_y = x + w // 2, y + h // 2
                self.log(f"🖼️ Найдено 8.png! Координаты центра: ({center_x}, {center_y})")
                pyautogui.press('8')
                self.last_8_press_time = current_time

    def run(self):
        self.log("🟢 Бот запущен: лечение, атака, ходьба, поиск 8.png")
        self.log("ℹ️ Подсказка: удерживай Shift — бот остановится. F9 — пауза/продолжить. Ctrl+Shift — выключить. F10 — режим только лечения")
        while self.running:
            if self.paused or keyboard.is_pressed('shift'):
                time.sleep(0.1)
                continue
            self.use_health_potion()
            self.use_mana_potion()
            self.detect_and_attack()
            self.auto_walk()
            self.detect_and_press_8()  # ✅ НОВОЕ
            time.sleep(self.CHECK_INTERVAL)

    def stop(self):
        self.running = False
        self.log("🛑 Бот остановлен")