from ultralytics import YOLO
import os

# Имя модели (должно совпадать с файлом в папке)
MODEL_NAME = "lizard1_5"

# Проверяем наличие .pt файла
pt_file = f"{MODEL_NAME}.pt"
if not os.path.exists(pt_file):
    raise FileNotFoundError(f"❌ Не найден файл модели: {pt_file}")

print(f"✅ Найдена модель: {pt_file}")

# Загружаем модель
print("🔄 Загружаю модель YOLO...")
model = YOLO(pt_file)

# Экспортируем в ONNX
print("🚀 Экспортирую в ONNX...")

model.export(
    format="onnx",
    opset=13,
    dynamic=True,           # позволяет разный размер батча и изображения
    imgsz=640,              # размер входного изображения (можешь изменить, если обучался на другом)
    device=0 if os.getenv("CUDA_AVAILABLE", "1") == "1" else "cpu",  # использовать GPU, если есть
)

# ultralytics сохранит как {MODEL_NAME}.onnx
onnx_file = f"{MODEL_NAME}.onnx"
if os.path.exists(onnx_file):
    print(f"✅ Успешно экспортировано: {onnx_file}")
else:
    print(f"❌ Ошибка: файл {onnx_file} не был создан.")