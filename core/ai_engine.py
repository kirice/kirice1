import os
import time
import cv2
import mss
import numpy as np
import pickle

# Опциональные импорты
ONNX_AVAILABLE = False
TORCH_AVAILABLE = False
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except: pass
try:
    import torch
    import torch.nn as nn
    from torch.utils.data import Dataset, DataLoader
    from torchvision import models
    TORCH_AVAILABLE = True
except: pass

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
            detections.append({"bbox": (x1, y1, x2, y2), "confidence": conf, "class_id": cls_id})
    except Exception as e:
        print(f"Ошибка в parse_yolo_onnx_output: {e}")
    return detections

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

class WalkingAI:
    def __init__(self, monitor, log_callback=None, map_name="lizard_dungeon"):
        self.monitor = monitor
        self.log = log_callback or (lambda m: print(f"[WalkingAI] {m}"))
        self.map_name = map_name
        
        # Пути к моделям (относительно корня проекта)
        from .utils import get_project_root
        root = get_project_root()
        maps_dir = os.path.join(root, "maps")
        os.makedirs(maps_dir, exist_ok=True)
        
        self.model_pth = os.path.join(maps_dir, f"{map_name}.pth")
        self.model_onnx = os.path.join(maps_dir, f"{map_name}.onnx")
        self.dataset_path = os.path.join(maps_dir, f"{map_name}.pkl")
        
        self.recording = False
        self.clicks = []
        self.frames = []
        self.dataset = []
        self.onnx_runner = None
        
        self.device = "cuda" if TORCH_AVAILABLE and torch.cuda.is_available() else "cpu"
        if TORCH_AVAILABLE:
            self.model = self._build_torch_resnet(self.device)
            try:
                from pynput import mouse
                self.mouse_listener = mouse.Listener(on_click=self.on_click)
                self.mouse_listener.start()
            except:
                self.log("⚠️ pynput не доступен")
        else:
            if ONNX_AVAILABLE and os.path.exists(self.model_onnx):
                self.onnx_runner = ONNXWalking(self.model_onnx, monitor, log=self.log)
        
        self.load_dataset()

    def _build_torch_resnet(self, device):
        if not TORCH_AVAILABLE:
            return None
        model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        model.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3, bias=False)
        model.fc = nn.Sequential(nn.Dropout(0.5), nn.Linear(512, 128), nn.ReLU(), nn.Linear(128, 2))
        model.to(device)
        return model

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
        self.dataset.extend(new_data)
        self.log(f"✅ Добавлено {len(new_data)} примеров")

    def save_dataset(self):
        os.makedirs(os.path.dirname(self.dataset_path), exist_ok=True)
        with open(self.dataset_path, "wb") as f:
            pickle.dump(self.dataset, f)
        self.log(f"💾 Датасет сохранён: {self.dataset_path}")

    def load_dataset(self):
        if os.path.exists(self.dataset_path) and os.path.getsize(self.dataset_path) > 0:
            try:
                with open(self.dataset_path, "rb") as f:
                    loaded = pickle.load(f)
                self.dataset.extend(loaded)
                self.log(f"📂 Загружено {len(loaded)} примеров")
            except Exception as e:
                self.log(f"⚠ Ошибка чтения датасета: {e}")

    def train(self, epochs=50, batch_size=32, lr=1e-4):
        if not TORCH_AVAILABLE:
            self.log("❌ PyTorch не доступен — обучение невозможно")
            return
        if not self.dataset:
            self.log("❌ Нет данных для обучения")
            return
        class ClickDataset(Dataset):
            def __init__(self, data): self.data = data
            def __len__(self): return len(self.data)
            def __getitem__(self, idx): return torch.FloatTensor(self.data[idx][0]), torch.FloatTensor(self.data[idx][1])
        
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
        if ONNX_AVAILABLE and self.onnx_runner is not None:
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