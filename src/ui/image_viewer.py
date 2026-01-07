from PyQt6.QtWidgets import (QMainWindow, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, 
                             QToolBar, QLabel, QPushButton, QWidget, QVBoxLayout, QApplication,
                             QSizePolicy, QSpinBox)
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QSize, QTimer
from PyQt6.QtGui import QPixmap, QAction, QIcon, QTransform, QWheelEvent, QPainter, QImageReader
import os

class ImageViewer(QMainWindow):
    """
    Enhanced Image Viewer with functionalities similar to Windows Image Viewer.
    Supports: Zoom, Pan, Rotate, Previous/Next Navigation, Slideshow.
    """
    
    def __init__(self, media_list=None, start_index=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Image Viewer")
        self.resize(1000, 700)
        
        # Data
        self.media_list = media_list if media_list else []
        self.current_index = start_index
        
        # Slideshow Timer
        self.slideshow_timer = QTimer(self)
        self.slideshow_timer.setInterval(3000) # 3 seconds
        self.slideshow_timer.timeout.connect(self.next_image)
        self.is_slideshow_active = False
        
        # UI Setup
        self.init_ui()
        
        # Load initial image
        if 0 <= self.current_index < len(self.media_list):
            self.load_image_by_index(self.current_index)
            
        # Start Maximized (Fit to Screen with window controls)
        self.showMaximized()
        
    def init_ui(self):
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Graphics View Setup
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setBackgroundBrush(Qt.GlobalColor.black)
        
        # Graphics Item
        self.pixmap_item = QGraphicsPixmapItem()
        self.pixmap_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.scene.addItem(self.pixmap_item)
        
        layout.addWidget(self.view)
        
        # Toolbar
        self.create_toolbar()
        
        # Styles
        self.setStyleSheet("""
            QMainWindow { background-color: #2b2b2b; color: white; }
            QToolBar { background-color: white; border-bottom: 1px solid #dedede; spacing: 10px; padding: 5px; }
            QToolButton { background-color: transparent; border: 1px solid transparent; border-radius: 4px; padding: 5px; color: #333333; }
            QToolButton:hover { background-color: #f0f0f0; border: 1px solid #cccccc; }
            QToolButton:pressed { background-color: #e0e0e0; }
            QLabel { color: #333333; font-family: monospace; font-weight: bold; }
        """)

    def create_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        
        # Actions
        # Zoom Out
        zoom_out_act = QAction("Zoom -", self)
        zoom_out_act.triggered.connect(self.zoom_out)
        toolbar.addAction(zoom_out_act)
        
        # Zoom In
        zoom_in_act = QAction("Zoom +", self)
        zoom_in_act.triggered.connect(self.zoom_in)
        toolbar.addAction(zoom_in_act)
        
        # Fit to Window
        fit_act = QAction("Fit", self)
        fit_act.triggered.connect(self.fit_to_window)
        toolbar.addAction(fit_act)
        
        # 1:1
        one_to_one_act = QAction("1:1", self)
        one_to_one_act.triggered.connect(self.reset_zoom)
        toolbar.addAction(one_to_one_act)
        
        toolbar.addSeparator()
        
        # Rotate Left
        rot_l_act = QAction("Rot L", self)
        rot_l_act.triggered.connect(lambda: self.rotate(-90))
        toolbar.addAction(rot_l_act)
        
        # Rotate Right
        rot_r_act = QAction("Rot R", self)
        rot_r_act.triggered.connect(lambda: self.rotate(90))
        toolbar.addAction(rot_r_act)
        
        toolbar.addSeparator()
        
        # Slideshow Speed
        speed_label = QLabel(" Speed(s): ")
        toolbar.addWidget(speed_label)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(3)
        self.interval_spin.setToolTip("Slideshow interval in seconds")
        self.interval_spin.valueChanged.connect(self.update_slideshow_speed)
        toolbar.addWidget(self.interval_spin)
        
        # Slideshow
        self.slideshow_act = QAction("Slideshow Play", self)
        self.slideshow_act.setCheckable(True)
        self.slideshow_act.triggered.connect(self.toggle_slideshow)
        toolbar.addAction(self.slideshow_act)
        
        # Fullscreen Toggle
        self.fs_act = QAction("Full Scr", self)
        self.fs_act.setCheckable(True)
        self.fs_act.setChecked(False) # Start normally (Maximized, not exclusive FS)
        self.fs_act.triggered.connect(self.toggle_fullscreen)
        toolbar.addAction(self.fs_act)
        
        toolbar.addSeparator()
        
        # Previous
        self.prev_act = QAction("<< Prev", self)
        self.prev_act.triggered.connect(self.prev_image)
        toolbar.addAction(self.prev_act)
        
        # Next
        self.next_act = QAction("Next >>", self)
        self.next_act.triggered.connect(self.next_image)
        toolbar.addAction(self.next_act)
        
        # Spacer
        empty = QWidget()
        empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(empty)
        
        # Info Label
        self.info_label = QLabel(" 0 / 0 ")
        toolbar.addWidget(self.info_label)

    def load_image_by_index(self, index):
        if not (0 <= index < len(self.media_list)):
            return
            
        data = self.media_list[index]
        # data structure assumed: (id, path, filename, extension, type, ...)
        path = data[1]
        
        if not os.path.exists(path):
            self.setWindowTitle(f"File not found: {path}")
            return
            
        # Use QImageReader to allow Large Images
        reader = QImageReader(path)
        reader.setAutoTransform(True) # Handle EXIF rotation automatically
        # 0 = block reading (actually limit, wait doc says 0 is reject all. Default is 256MB)
        # We should set it to very large. 1024 MB or more?
        # Actually some docs say 0 means unlimit in Qt6? 
        # Let's check Qt docs via search? No I can't.
        # Safe bet: 2048 MB
        reader.setAllocationLimit(2048) 
        
        image = reader.read()
        
        if image.isNull():
             # Instead of failing, create a placeholder so the slideshow can continue
             # and the user knows why it's blank/black
             pixmap = QPixmap(800, 600)
             pixmap.fill(Qt.GlobalColor.black)
             
             painter = QPainter(pixmap)
             painter.setPen(Qt.GlobalColor.white)
             font = painter.font()
             font.setPointSize(20)
             painter.setFont(font)
             painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, f"Cannot preview file:\n{os.path.basename(path)}")
             painter.end()
        else:
             pixmap = QPixmap.fromImage(image)

        # Reset View
        self.pixmap_item.setPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        
        # Reset transforms
        self.view.resetTransform()
        self.pixmap_item.setRotation(0)
        
        self.fit_to_window()
        
        self.current_index = index
        self.update_ui_state()
        self.setWindowTitle(f"{os.path.basename(path)} - Image Viewer")

    def update_ui_state(self):
        self.prev_act.setEnabled(self.current_index > 0)
        self.next_act.setEnabled(self.current_index < len(self.media_list) - 1)
        self.info_label.setText(f" {self.current_index + 1} / {len(self.media_list)} ")

    def fit_to_window(self):
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def reset_zoom(self):
        self.view.resetTransform()
        
    def zoom_in(self):
        self.view.scale(1.2, 1.2)
        
    def zoom_out(self):
        self.view.scale(0.8, 0.8)
        
    def rotate(self, angle):
        # Rotating the view feels more natural for "Viewer" behavior than rotating item
        self.view.rotate(angle)
        # Re-fit if wanted? usually rotation keeps zoom level or fits.
        # Let's keep zoom level but center
        
    def update_slideshow_speed(self, val):
        self.slideshow_timer.setInterval(val * 1000)

    def toggle_slideshow(self, checked):
        self.is_slideshow_active = checked
        if self.is_slideshow_active:
            self.slideshow_act.setText("Slideshow Stop")
            self.slideshow_timer.start()
        else:
            self.slideshow_act.setText("Slideshow Play")
            self.slideshow_timer.stop()
            
    def toggle_fullscreen(self, checked):
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()
            
    def next_image(self):
        if self.current_index < len(self.media_list) - 1:
            self.load_image_by_index(self.current_index + 1)
        elif self.is_slideshow_active:
             # Loop back to start if slideshow
             self.load_image_by_index(0)
            
    def prev_image(self):
        if self.current_index > 0:
            self.load_image_by_index(self.current_index - 1)
        elif self.is_slideshow_active:
             # Loop back to end
             self.load_image_by_index(len(self.media_list) - 1)
            
    # --- Event Overrides ---
    
    def wheelEvent(self, event: QWheelEvent):
        # Zoom on wheel
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # If Ctrl held, do standard zoom
            zoom_factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self.view.scale(zoom_factor, zoom_factor)
        else:
            # Just wheel -> Scroll or Zoom?
            # Windows viewer zooms on wheel by default usually
            zoom_factor = 1.1 if event.angleDelta().y() > 0 else 0.9
            self.view.scale(zoom_factor, zoom_factor)
            
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Right:
            self.next_image()
        elif event.key() == Qt.Key.Key_Left:
            self.prev_image()
        elif event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
                self.fs_act.setChecked(False)
            else:
                self.close()
        elif event.key() == Qt.Key.Key_Space:
            # Toggle slideshow manually
            self.slideshow_act.trigger() # Simulates click, emits triggered, toggles checked state if checkable

        else:
            super().keyPressEvent(event)
