import os
import datetime
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QScrollArea, QFormLayout, 
                             QFrame)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImageReader

# Try importing cv2 for video metadata
try:
    import cv2
except ImportError:
    cv2 = None

class MetadataPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QLabel("Media Information")
        header.setStyleSheet("font-weight: bold; padding: 5px; background-color: #e0e0e0; border-bottom: 1px solid #c0c0c0;")
        layout.addWidget(header)
        
        # Scroll Area for properties
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        self.content_widget = QWidget()
        self.form_layout = QFormLayout(self.content_widget)
        self.form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.form_layout.setSpacing(10)
        self.form_layout.setContentsMargins(10, 10, 10, 10)
        
        self.scroll_area.setWidget(self.content_widget)
        layout.addWidget(self.scroll_area)
        
        # Initial Placeholder
        self.clear_info()

    def clear_info(self):
        # Clear existing rows
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
                
        self.add_row("Status", "No media selected")

    def add_row(self, label, value):
        lbl = QLabel(label + ":")
        lbl.setStyleSheet("color: #666; font-weight: bold;")
        val = QLabel(str(value))
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.form_layout.addRow(lbl, val)

    def update_info(self, file_path):
        self.clear_info()
        
        # Remove "No media selected" placeholder if clearing did that
        # Actually clear_info adds it. We should clear that first row.
        while self.form_layout.count():
            self.form_layout.takeAt(0).widget().deleteLater()
            
        if not file_path or not os.path.exists(file_path):
            self.add_row("Status", "File not found")
            return

        try:
            # 1. Basic File Info
            stats = os.stat(file_path)
            size_mb = stats.st_size / (1024 * 1024)
            created_time = datetime.datetime.fromtimestamp(stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
            mod_time = datetime.datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            self.add_row("Filename", os.path.basename(file_path))
            self.add_row("Folder", os.path.dirname(file_path))
            self.add_row("Size", f"{size_mb:.2f} MB")
            self.add_row("Modified", mod_time)
            self.add_row("Created", created_time)
            
            ext = os.path.splitext(file_path)[1].lower()
            self.add_row("Type", ext.upper().strip('.'))
            
            # 2. Type Specific Info
            if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff']:
                self.get_image_metadata(file_path)
            elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.webm']:
                self.get_video_metadata(file_path)
                
        except Exception as e:
            self.add_row("Error", str(e))

    def get_image_metadata(self, path):
        try:
            reader = QImageReader(path)
            # Use Quick read of size/format
            size = reader.size()
            fmt = reader.format().data().decode('utf-8')
            
            if size.isValid():
                self.add_row("Resolution", f"{size.width()} x {size.height()} px")
                self.add_row("Format", fmt.upper())
                
                # Aspect Ratio
                if size.height() > 0:
                    ar = size.width() / size.height()
                    self.add_row("Aspect Ratio", f"{ar:.2f}")
                    
            # Color Space?
            # image = reader.read() # Might be slow for big files
            # if not image.isNull():
            #     self.add_row("Depth", f"{image.depth()} bit")

        except Exception as e:
            pass

    def get_video_metadata(self, path):
        if cv2 is None:
            self.add_row("Video Info", "OpenCV not installed")
            return
            
        try:
            cap = cv2.VideoCapture(path)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                
                if w > 0 and h > 0:
                    self.add_row("Resolution", f"{w} x {h}")
                
                if fps > 0:
                    self.add_row("Frame Rate", f"{fps:.2f} fps")
                    if frame_count > 0:
                        duration_sec = frame_count / fps
                        duration_str = str(datetime.timedelta(seconds=int(duration_sec)))
                        self.add_row("Duration", duration_str)
                
                cap.release()
        except Exception:
            pass
