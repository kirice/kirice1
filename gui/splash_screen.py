import sys
import os
import time
from PyQt5.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QRectF
from PyQt5.QtWidgets import QSplashScreen, QLabel, QVBoxLayout, QWidget, QGraphicsOpacityEffect, QApplication
from PyQt5.QtGui import QFont, QColor, QLinearGradient, QRadialGradient, QBrush, QPainter, QPixmap, QPainterPath

# Добавляем корень проекта в путь
def get_project_root():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

project_root = get_project_root()
sys.path.insert(0, project_root)

from gui.main_window import MainWindow


class AnimatedLabel(QLabel):
    """Анимированная надпись с градиентом"""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.setStyleSheet("color: #ffffff;")
        self.gradient_offset = 0
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Создаем градиентный текст
        gradient = QLinearGradient(0, 0, self.width(), 0)
        colors = [
            QColor("#00C9FF"),
            QColor("#92FE9D"),
            QColor("#00C9FF"),
        ]
        
        for i, color in enumerate(colors):
            gradient.setColorAt(i / (len(colors) - 1), color)
        
        painter.setPen(gradient)
        painter.drawText(self.rect(), Qt.AlignCenter, self.text())


class LoadingDots(QWidget):
    """Анимация точек загрузки"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 30)
        self.dot_positions = [0.0, 0.0, 0.0]
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(150)
        self.phase = 0
        
    def update_animation(self):
        self.phase += 1
        for i in range(3):
            offset = (self.phase + i * 3) % 9
            if offset < 3:
                self.dot_positions[i] = offset / 3.0
            elif offset < 6:
                self.dot_positions[i] = 1.0 - ((offset - 3) / 3.0)
            else:
                self.dot_positions[i] = 0.0
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        for i in range(3):
            x = 20 + i * 30
            y = 15
            radius = 4 + 6 * self.dot_positions[i]
            
            gradient = QRadialGradient(x, y, radius)
            gradient.setColorAt(0, QColor("#00C9FF"))
            gradient.setColorAt(1, QColor("#00C9FF").lighter(150))
            
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(x - radius), int(y - radius), int(radius * 2), int(radius * 2))


class LoadingBar(QWidget):
    """Кастомный прогресс бар с градиентом"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0
        self.setFixedHeight(4)
        
    def setProgress(self, value):
        self.progress = max(0, min(100, value))
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Фон
        painter.setBrush(QColor("#333333"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 2, 2)
        
        # Заполнение с градиентом
        if self.progress > 0:
            width = int(self.width() * self.progress / 100)
            gradient = QLinearGradient(0, 0, width, 0)
            gradient.setColorAt(0, QColor("#00C9FF"))
            gradient.setColorAt(1, QColor("#92FE9D"))
            
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(0, 0, width, self.height(), 2, 2)


class ModernSplashScreen(QSplashScreen):
    """Современный экран загрузки с анимациями"""
    
    loading_complete = pyqtSignal()
    
    def __init__(self, pixmap=None):
        if pixmap is None:
            pixmap = QPixmap(500, 350)
            pixmap.fill(QColor("#1e1e1e"))
        
        super().__init__(pixmap)
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Главный контейнер
        self.container = QWidget(self)
        self.container.setGeometry(0, 0, 500, 350)
        self.container.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #1a1a2e, stop:0.5 #16213e, stop:1 #1a1a2e);
            border-radius: 20px;
        """)
        
        # Эффект прозрачности для плавного появления
        self.opacity_effect = QGraphicsOpacityEffect(self.container)
        self.container.setGraphicsEffect(self.opacity_effect)
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(500)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        
        # Логотип/Заголовок
        self.title_label = QLabel("🤖 Rucoy Bot AI", self.container)
        self.title_label.setGeometry(50, 60, 400, 50)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(QFont("Segoe UI", 24, QFont.Bold))
        self.title_label.setStyleSheet("""
            color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #00C9FF, stop:1 #92FE9D);
            background: transparent;
        """)
        
        # Подзаголовок
        self.subtitle_label = QLabel("Интеллектуальный бот для Rucoy Online", self.container)
        self.subtitle_label.setGeometry(50, 110, 400, 30)
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setFont(QFont("Segoe UI", 11))
        self.subtitle_label.setStyleSheet("color: #888888; background: transparent;")
        
        # Анимированная надпись "Загрузка..."
        self.loading_label = AnimatedLabel("Инициализация системы...", self.container)
        self.loading_label.setGeometry(50, 180, 400, 40)
        
        # Точки загрузки
        self.loading_dots = LoadingDots(self.container)
        self.loading_dots.move(200, 230)
        
        # Прогресс бар (кастомный)
        self.progress_bar = LoadingBar(self.container)
        self.progress_bar.setGeometry(75, 280, 350, 4)
        
        # Статус бар
        self.status_label = QLabel("Готово: 0%", self.container)
        self.status_label.setGeometry(50, 310, 400, 20)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setStyleSheet("color: #666666; background: transparent;")
        
        # Этапы загрузки
        self.loading_stages = [
            "Проверка зависимостей...",
            "Загрузка конфигурации...",
            "Инициализация GUI...",
            "Подготовка модулей...",
            "Запуск системы...",
        ]
        self.current_stage = 0
        
    def showEvent(self, event):
        super().showEvent(event)
        self.fade_anim.start()
        
    def update_progress(self, progress, status_text=None):
        """Обновление прогресса загрузки"""
        progress = max(0, min(100, progress))
        
        # Обновление прогресс бара
        self.progress_bar.setProgress(progress)
        
        # Обновление текста статуса
        if status_text:
            self.loading_label.setText(status_text)
        elif self.current_stage < len(self.loading_stages):
            stage_index = int(progress / 20)
            if stage_index < len(self.loading_stages):
                self.loading_label.setText(self.loading_stages[stage_index])
                self.current_stage = stage_index
        
        self.status_label.setText(f"Готово: {progress}%")
        
    def finish_with_animation(self, widget_to_show):
        """Плавное завершение экрана загрузки"""
        self.fade_anim.setDirection(QPropertyAnimation.Backward)
        self.fade_anim.finished.connect(lambda: self._on_fade_out(widget_to_show))
        self.fade_anim.start()
        
    def _on_fade_out(self, widget_to_show):
        self.close()
        if widget_to_show:
            widget_to_show.show()
        self.loading_complete.emit()


def create_splash_screen():
    """Фабричная функция для создания экрана загрузки"""
    return ModernSplashScreen()


def run_with_splash():
    """Запуск приложения с экраном загрузки"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Создаем и показываем splash screen
    splash = create_splash_screen()
    splash.show()
    
    # Имитация загрузки с прогрессом
    def load_step_1():
        splash.update_progress(20, "Проверка зависимостей...")
        QTimer.singleShot(400, load_step_2)
    
    def load_step_2():
        splash.update_progress(40, "Загрузка конфигурации...")
        QTimer.singleShot(400, load_step_3)
    
    def load_step_3():
        splash.update_progress(60, "Инициализация GUI...")
        QTimer.singleShot(400, load_step_4)
    
    def load_step_4():
        splash.update_progress(80, "Подготовка модулей...")
        QTimer.singleShot(400, load_step_5)
    
    def load_step_5():
        splash.update_progress(100, "Запуск системы...")
        # Создаем главное окно
        window = MainWindow()
        # Завершаем splash с анимацией
        QTimer.singleShot(500, lambda: splash.finish_with_animation(window))
    
    # Запускаем первую стадию загрузки
    QTimer.singleShot(500, load_step_1)
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    run_with_splash()
