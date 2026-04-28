import os
import time
import cv2
import mss
import numpy as np
import pyautogui
import keyboard
import pickle
import threading

# ==============================================================================
# Проверка зависимостей
# ==============================================================================
ONNX_AVAILABLE = False
TORCH_AVAILABLE = False
ULTRALYTICS_AVAILABLE = False

try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except Exception:
    ONNX_AVAILABLE = False

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    from torchvision import models
    TORCH_AVAILABLE = True
except Exception:
    TORCH_AVAILABLE = False

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except Exception:
    ULTRALYTICS_AVAILABLE = False

# ==============================================================================
# Утилиты
# ==============================================================================
def parse_yolo_onnx_output(outputs, img_width, img_height, conf_threshold=0.5):
    detections = []
    if isinstance(outputs, list):
        outputs = outputs[0]
    try:
        if not isinstance(outputs, np.ndarray):
            outputs = np.array(outputs)
        if len(outputs.shape) == 3:
            outputs = outputs[0]
        elif len(outputs.shape) == 6:
            outputs = outputs.reshape(-1, outputs.shape[-2])
        
        for det in outputs:
            x, y, w, h, conf = float(det[0]), float(det[1]), float(det[2]), float(det[3]), float(det[4])
            if conf < conf_threshold:
                continue
            cls_id = int(np.argmax(det[5:]))
            x1 = int((x - w / 2) * img_width)
            y1 = int((y - h / 2) * img_height)
            x2 = int((x + w / 2) * img_width)
            y2 = int((y + h / 2) * img_height)
            detections.append({
                "bbox": (x1, y1, x2, y2),
                "confidence": conf,
                "class_id": cls_id
            })
    except Exception as e:
        print(f"Ошибка в parse_yolo_onnx_output: {e}")
    return detections

# ==============================================================================
# PyTorch модели (если доступен)
# ==============================================================================
if TORCH_AVAILABLE:
    class ClickDataset(Dataset):
        def __init__(self, data):
            self.data = data
        def __len__(self):
            return len(self.data)
        def __getitem__(self, idx):
            return torch.FloatTensor(self.data[idx][0]), torch.FloatTensor(self.data[idx][1])

    def build_torch_resnet(device="cpu"):
        model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        model.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3, bias=False)
        model.fc = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(512, 128),
            nn.ReLU(),
            nn.Linear(128, 2)
        )
        model.to(device)
        return model

# ==============================================================================
# ONNX Walking (инференс)
# ==============================================================================
class ONNXWalking:
    def __init__(self, model_path, monitor, log=lambda s: print(s)):
        self.log = log
        self.monitor = monitor
        if not ONNX_AVAILABLE:
            raise RuntimeError("ONNXRuntime not available")
        if not os.path.exists(model_path):
            raise FileNotFoundError(model_path)
        self.sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_name = self.sess.get_inputs()[0].name
        self.output_name = self.sess.get_outputs()[0].name
        self.log(f"✅ Walking ONNX loaded: {model_path}")

    def predict_click(self):
        with mss.mss() as sct:
            arr = np.array(sct.grab(self.monitor))
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
        img = cv2.resize(arr, (224, 224)).astype(np.float32)/255.0
        img = np.transpose(img, (2,0,1))[None, :]
        out = self.sess.run([self.output_name], {self.input_name: img})[0]
        dx, dy = out[0] * 300.0
        screen_x = int(self.monitor["left"] + self.monitor["width"]//2 + dx)
        screen_y = int(self.monitor["top"] + self.monitor["height"]//2 + dy)
        return screen_x, screen_y

# ==============================================================================
# Walking AI (запись/обучение/экспорт)
# ==============================================================================
class WalkingAI:
    def __init__(self, monitor, log_callback=None, map_name="lizard_dungeon"):
        self.monitor = monitor
        self.log = log_callback or (lambda m: print(f"[WalkingAI] {m}"))
        self.map_name = map_name
        
        # ✅ Пути: bots/maps/
        base_dir = os.path.dirname(os.path.abspath(__file__))
        maps_dir = os.path.join(base_dir, "maps")
        os.makedirs(maps_dir, exist_ok=True)
        
        self.model_pth = os.path.join(maps_dir, f"{map_name}.pth")
        self.model_onnx = os.path.join(maps_dir, f"{map_name}.onnx")
        self.dataset_path = os.path.join(maps_dir, f"{map_name}.pkl")
        
        self.recording = False
        self.clicks = []
        self.frames = []
        self.dataset = []
        
        # ✅ Для таймера статистики
        self.recording_start_time = 0
        self.last_stats_time = 0
        self.stats_thread = None
        
        self.device = "cuda" if TORCH_AVAILABLE and torch.cuda.is_available() else "cpu"
        if TORCH_AVAILABLE:
            self.model = build_torch_resnet(self.device)
            try:
                from pynput import mouse
                self.mouse_listener = mouse.Listener(on_click=self.on_click)
                self.mouse_listener.start()
            except:
                self.log("⚠️ pynput не доступен")
        else:
            if ONNX_AVAILABLE and os.path.exists(self.model_onnx):
                self.onnx_runner = ONNXWalking(self.model_onnx, monitor, log=self.log)
            else:
                self.onnx_runner = None
        
        # ✅ Загружаем старые данные при старте (СЛИЯНИЕ)
        self.load_dataset()

    def on_click(self, x, y, button, pressed):
        if not self.recording or not pressed:
            return
        rel_x = x - self.monitor["left"]
        rel_y = y - self.monitor["top"]
        if 0 <= rel_x < self.monitor["width"] and 0 <= rel_y < self.monitor["height"]:
            self.clicks.append((time.time(), rel_x, rel_y))

    def record_step(self):
        with mss.mss() as sct:
            img = np.array(sct.grab(self.monitor))
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            self.frames.append((time.time(), img))

    def align_clicks(self):
        new_data = []
        for frame_time, frame in self.frames:
            past_clicks = [(t,x,y) for (t,x,y) in self.clicks if t <= frame_time]
            if not past_clicks:
                continue
            _, x, y = past_clicks[-1]
            cx, cy = self.monitor["width"]//2, self.monitor["height"]//2
            dx, dy = x-cx, y-cy
            if abs(dx) > 300 or abs(dy) > 300:
                continue
            img = cv2.resize(frame, (224,224)).astype(np.float32)/255.0
            img = np.transpose(img, (2,0,1))
            new_data.append((img, [dx/300.0, dy/300.0]))
        
        # ✅ ДОБАВЛЯЕМ к старым данным (не перезаписываем)
        self.dataset.extend(new_data)
        self.log(f"✅ Добавлено {len(new_data)} примеров. Всего в датасете: {len(self.dataset)}")

    def save_dataset(self):
        os.makedirs(os.path.dirname(self.dataset_path), exist_ok=True)
        with open(self.dataset_path, "wb") as f:
            pickle.dump(self.dataset, f)
        self.log(f"💾 Датасет сохранён: {self.dataset_path} (Записей: {len(self.dataset)})")

    def load_dataset(self):
        # ✅ ЗАГРУЖАЕМ старые данные и объединяем с текущими
        if os.path.exists(self.dataset_path) and os.path.getsize(self.dataset_path) > 0:
            try:
                with open(self.dataset_path, "rb") as f:
                    loaded = pickle.load(f)
                self.dataset.extend(loaded)
                self.log(f"📂 Загружено {len(loaded)} старых примеров. Всего: {len(self.dataset)}")
            except Exception as e:
                self.log(f"⚠ Ошибка чтения датасета: {e}")

    def clean_dataset(self, threshold=0.05):
        """
        ✅ АВТО-ОЧИСТКА: Удаляет записи, где персонаж почти не двигался (шум)
        threshold: порог удаления (0.05 = ~15 пикселей)
        """
        original_count = len(self.dataset)
        cleaned = []
        removed = 0
        
        for img, (dx, dy) in self.dataset:
            # Если смещение очень маленькое — это шум
            if abs(dx) < threshold and abs(dy) < threshold:
                removed += 1
            else:
                cleaned.append((img, [dx, dy]))
        
        self.dataset = cleaned
        self.log(f"🧹 Авто-очистка: удалено {removed} шумных записей ({removed/original_count*100:.1f}%)")
        self.log(f"✅ Осталось чистых записей: {len(self.dataset)}")

    def _stats_worker(self):
        """
        ✅ ФОНОВЫЙ ПОТОК: Вывод статистики раз в минуту во время записи
        """
        while self.recording:
            time.sleep(60)  # Ждём 1 минуту
            if self.recording:
                elapsed = time.time() - self.recording_start_time
                frames_count = len(self.frames)
                clicks_count = len(self.clicks)
                total_dataset = len(self.dataset)
                self.log(f"⏱️ Запись идёт {elapsed/60:.1f} мин | Кадров: {frames_count} | Кликов: {clicks_count} | Всего в базе: {total_dataset}")

    def start_recording(self):
        self.recording = True
        self.recording_start_time = time.time()
        self.last_stats_time = time.time()
        self.clicks = []
        self.frames = []
        
        # ✅ Запускаем поток статистики
        self.stats_thread = threading.Thread(target=self._stats_worker, daemon=True)
        self.stats_thread.start()
        self.log("🟢 Запись началась. Статистика будет каждую минуту.")

    def stop_recording(self):
        self.recording = False
        self.log("🔴 Остановка записи...")
        
        # Обрабатываем накопленные данные
        self.align_clicks()
        
        # ✅ АВТО-ОЧИСТКА перед сохранением
        self.clean_dataset(threshold=0.05)
        
        # Сохраняем (объединяя со старыми)
        self.save_dataset()

    def train(self, epochs=50, batch_size=32, lr=1e-4):
        if not TORCH_AVAILABLE:
            self.log("❌ PyTorch не доступен — обучение невозможно")
            return
        if not self.dataset:
            self.log("❌ Нет данных для обучения")
            return
        loader = DataLoader(ClickDataset(self.dataset), batch_size, shuffle=True)
        opt = torch.optim.Adam(self.model.parameters(), lr=lr)
        loss_fn = nn.MSELoss()
        self.model.train()
        for epoch in range(epochs):
            total = 0.0
            for X,Y in loader:
                X, Y = X.to(self.device), Y.to(self.device)
                opt.zero_grad()
                pred = self.model(X)
                loss = loss_fn(pred, Y)
                loss.backward()
                opt.step()
                total += loss.item()
            self.log(f"Epoch {epoch+1}/{epochs}, Loss: {total/len(loader):.4f}")
        torch.save(self.model.state_dict(), self.model_pth)
        self.log(f"✅ Модель сохранена: {self.model_pth}")

    def export_to_onnx(self):
        if not TORCH_AVAILABLE:
            self.log("❌ PyTorch не доступен — экспорт невозможен")
            return
        if not os.path.exists(self.model_pth):
            self.log("❌ .pth не найден — сначала train")
            return
        self.model.load_state_dict(torch.load(self.model_pth, map_location="cpu"))
        self.model.eval()
        dummy = torch.randn(1,3,224,224)
        try:
            torch.onnx.export(self.model, dummy, self.model_onnx,
                              input_names=["input"], output_names=["output"],
                              dynamic_axes={"input":{0:"batch"}, "output":{0:"batch"}},
                              opset_version=17)
            self.log(f"💾 Экспортировано в ONNX: {self.model_onnx}")
        except Exception as e:
            self.log(f"❌ Ошибка экспорта ONNX: {e}")

    def load_model(self):
        if ONNX_AVAILABLE and os.path.exists(self.model_onnx):
            self.onnx_runner = ONNXWalking(self.model_onnx, self.monitor, log=self.log)
            return True
        if TORCH_AVAILABLE and os.path.exists(self.model_pth):
            self.model.load_state_dict(torch.load(self.model_pth, map_location=self.device))
            self.model.eval()
            return True
        return False

    def predict_click(self):
        if ONNX_AVAILABLE and hasattr(self, "onnx_runner") and self.onnx_runner is not None:
            return self.onnx_runner.predict_click()
        if TORCH_AVAILABLE and hasattr(self, "model"):
            with mss.mss() as sct:
                arr = np.array(sct.grab(self.monitor))
                arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
            img = cv2.resize(arr, (224,224)).astype(np.float32)/255.0
            img = np.transpose(img, (2,0,1))
            X = torch.FloatTensor(img).unsqueeze(0).to(self.device)
            self.model.eval()
            with torch.no_grad():
                dx,dy = self.model(X).cpu().numpy()[0]*300.0
            sx = int(self.monitor["left"] + self.monitor["width"]//2 + dx)
            sy = int(self.monitor["top"] + self.monitor["height"]//2 + dy)
            return sx, sy
        return self.monitor["left"] + self.monitor["width"]//2, self.monitor["top"] + self.monitor["height"]//2

# ==============================================================================
# ГЛАВНЫЙ КЛАСС БОТА (имя должно совпадать с именем файла!)
# ==============================================================================
class test_bot:
    available_commands = [
        "start_recording_walk",
        "stop_recording_walk",
        "train_walking_ai",
        "export_walking_onnx",
        "enable_auto_walk",
        "disable_auto_walk"
    ]
    
    def __init__(self, hwnd=None, log_callback=None, map_name="lizard_dungeon"):
        self.hwnd = hwnd
        self.log = log_callback or (lambda m: print(f"[test_bot] {m}"))
        self.map_name = map_name
        self.running = True
        self.paused = False

        # Модели
        base_dir = os.path.dirname(os.path.abspath(__file__))
        models_dir = os.path.join(base_dir, "..", "models")
        self.YOLO_ONNX = os.path.join(models_dir, "lizard1_5.onnx")
        self.YOLO_PT = os.path.join(models_dir, "lizard1_5.pt")

        self.CONF_THRESHOLD = 0.3
        self.KEY_ATTACK = '7'
        self.KEY_HP_POTION = '5'
        self.KEY_MP_POTION = '6'
        self.HP_PIXEL_COORD = (920,140)
        self.MANA_PIXEL_COORD = (920,170)
        self.LOW_COLOR = (107,105,107)
        self.POTION_COOLDOWN = 1.0
        self.ATTACK_COOLDOWN = 1.0
        self.CHECK_INTERVAL = 0.1
        self.last_potion_time = 0
        self.last_attack_time = 0

        # Монитор
        self.MONITOR = {"top":126, "left":596, "width":1300, "height":731}

        # Walking AI
        self.walking_ai = WalkingAI(self.MONITOR, log_callback=self.log, map_name=map_name)
        self.WALK_ENABLED = False
        self.last_walk_click = 0
        self.WALK_INTERVAL = 0.5

        # YOLO
        self.yolo_session = None
        self.yolo_pt = None
        self.load_yolo()

        # Hotkeys
        self.setup_hotkeys()

    def setup_hotkeys(self):
        try:
            keyboard.add_hotkey('F9', lambda: self.toggle_pause())
            keyboard.add_hotkey('ctrl+shift', lambda: self.stop())
        except Exception as e:
            self.log(f"⚠️ Не удалось установить хоткеи: {e}")

    def toggle_pause(self):
        self.paused = not self.paused
        self.log("⏸️ Пауза" if self.paused else "▶️ Продолжено")

    def load_yolo(self):
        if ONNX_AVAILABLE and os.path.exists(self.YOLO_ONNX):
            try:
                self.yolo_session = ort.InferenceSession(self.YOLO_ONNX, providers=["CPUExecutionProvider"])
                self.log("✅ YOLO ONNX loaded")
            except Exception as e:
                self.log(f"❌ YOLO ONNX load error: {e}")
                self.yolo_session = None
        elif ULTRALYTICS_AVAILABLE and os.path.exists(self.YOLO_PT):
            try:
                self.yolo_pt = YOLO(self.YOLO_PT)
                self.log("✅ YOLO .pt loaded (ultralytics)")
            except Exception as e:
                self.log(f"❌ YOLO .pt load error: {e}")

    def get_pixel_color(self, coords):
        try:
            return pyautogui.screenshot(region=(*coords,1,1)).getpixel((0,0))
        except Exception as e:
            self.log(f"Ошибка чтения пикселя: {e}")
            return (0,0,0)

    def use_potions(self):
        now = time.time()
        if now - self.last_potion_time < self.POTION_COOLDOWN:
            return
        hp_color = self.get_pixel_color(self.HP_PIXEL_COORD)
        mp_color = self.get_pixel_color(self.MANA_PIXEL_COORD)
        if np.allclose(hp_color, self.LOW_COLOR, atol=10):
            pyautogui.press(self.KEY_HP_POTION)
            self.last_potion_time = now
            self.log("💊 Пью зелье HP")
        if np.allclose(mp_color, self.LOW_COLOR, atol=10):
            pyautogui.press(self.KEY_MP_POTION)
            self.last_potion_time = now
            self.log("💧 Пью зелье MP")

    def detect_and_attack(self):
        if self.paused:
            return
        with mss.mss() as sct:
            frame = np.array(sct.grab(self.MONITOR))
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        found_any = False
        if ONNX_AVAILABLE and self.yolo_session is not None:
            try:
                input_name = self.yolo_session.get_inputs()[0].name
                inp = cv2.resize(frame, (640,640)).astype(np.float32)/255.0
                inp = np.transpose(inp, (2,0,1))[None, :]
                out = self.yolo_session.run(None, {input_name: inp})
                detections = parse_yolo_onnx_output(out, frame.shape[1], frame.shape[0], conf_threshold=self.CONF_THRESHOLD)
                if detections and len(detections) > 0:
                    found_any = True
            except Exception as e:
                self.log(f"❌ YOLO ONNX detect error: {e}")
        elif ULTRALYTICS_AVAILABLE and self.yolo_pt is not None:
            try:
                res = self.yolo_pt(frame, imgsz=320, conf=self.CONF_THRESHOLD, verbose=False)
                boxes = []
                for r in res:
                    for box in r.boxes:
                        boxes.append(box)
                if boxes and len(boxes) > 0:
                    found_any = True
            except Exception as e:
                self.log(f"❌ ultralytics detect error: {e}")
        now = time.time()
        if found_any and (now - self.last_attack_time) > self.ATTACK_COOLDOWN:
            pyautogui.press(self.KEY_ATTACK)
            self.last_attack_time = now
            self.log("🔥 Атака (Test)")

    def start_recording_walk(self):
        if not TORCH_AVAILABLE:
            self.log("❌ PyTorch/pynput не установлены — запись невозможна")
            return
        self.log("🟢 Начинаю запись ходьбы")
        self.walking_ai.start_recording()

    def stop_recording_walk(self):
        if not TORCH_AVAILABLE:
            return
        self.walking_ai.stop_recording()

    def train_walking_ai(self):
        if not TORCH_AVAILABLE:
            self.log("❌ PyTorch не установлен")
            return
        self.log("🛠 Обучение ходьбы...")
        self.walking_ai.train()

    def export_walking_onnx(self):
        if not TORCH_AVAILABLE:
            self.log("❌ PyTorch не доступен")
            return
        self.walking_ai.export_to_onnx()

    def enable_auto_walk(self):
        if not ONNX_AVAILABLE and not TORCH_AVAILABLE:
            self.log("❌ Нет механизмов для предсказания ходьбы")
            return
        if self.walking_ai.load_model():
            self.WALK_ENABLED = True
            self.log("✅ Автоход включён")
        else:
            self.log("❌ Не удалось загрузить модель ходьбы")

    def disable_auto_walk(self):
        self.WALK_ENABLED = False
        self.log("🛑 Автоход выключен")

    def run(self):
        self.log("🟢 test_bot запущен")
        while self.running:
            if self.paused:
                time.sleep(0.1)
                continue
            try:
                self.use_potions()
                self.detect_and_attack()
                if self.WALK_ENABLED:
                    x,y = self.walking_ai.predict_click()
                    pyautogui.click(x,y)
                    time.sleep(self.WALK_INTERVAL)
                if self.walking_ai.recording:
                    self.walking_ai.record_step()
            except Exception as e:
                self.log(f"❌ Ошибка в цикле test_bot: {e}")
            time.sleep(self.CHECK_INTERVAL)

    def stop(self):
        self.running = False
        if hasattr(self.walking_ai, "recording"):
            self.walking_ai.recording = False
        self.log("🛑 test_bot остановлен")