from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, 
                             QWidget, QListWidget, QPushButton, QLabel, 
                             QInputDialog, QMessageBox, QAbstractItemView)
from PyQt6.QtCore import Qt
from src.core.config import ConfigManager

class FormatManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Media Formats")
        self.resize(400, 500)
        self.config = ConfigManager()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Tabs for Image vs Video
        self.tabs = QTabWidget()
        self.image_tab = self.create_format_tab("image")
        self.video_tab = self.create_format_tab("video")
        
        self.tabs.addTab(self.image_tab, "Images")
        self.tabs.addTab(self.video_tab, "Videos")
        
        layout.addWidget(self.tabs)
        
        # Close button
        button_box = QHBoxLayout()
        button_box.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_box.addWidget(close_btn)
        
        layout.addLayout(button_box)

    def create_format_tab(self, media_type):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # List
        list_widget = QListWidget()
        list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.populate_list(list_widget, media_type)
        layout.addWidget(list_widget)
        
        # Buttons
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add Format")
        remove_btn = QPushButton("Remove Selected")
        
        add_btn.clicked.connect(lambda: self.add_format(list_widget, media_type))
        remove_btn.clicked.connect(lambda: self.remove_format(list_widget, media_type))
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(remove_btn)
        layout.addLayout(btn_layout)
        
        return widget

    def populate_list(self, list_widget, media_type):
        list_widget.clear()
        if media_type == "image":
            exts = self.config.get_image_extensions()
        else:
            exts = self.config.get_video_extensions()
            
        for ext in sorted(exts):
            list_widget.addItem(ext)

    def add_format(self, list_widget, media_type):
        ext, ok = QInputDialog.getText(self, "Add Format", 
                                     "Enter file extension (e.g., .raw):")
        if ok and ext:
            ext = ext.strip().lower()
            if not ext.startswith('.'):
                ext = '.' + ext
                
            if self.config.add_extension(media_type, ext):
                self.populate_list(list_widget, media_type)
            else:
                QMessageBox.warning(self, "Error", "Format already exists or invalid.")

    def remove_format(self, list_widget, media_type):
        selected_items = list_widget.selectedItems()
        if not selected_items:
            return
            
        ext = selected_items[0].text()
        reply = QMessageBox.question(self, "Confirm Remove", 
                                   f"Are you sure you want to stop scanning {ext} files?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                   
        if reply == QMessageBox.StandardButton.Yes:
            if self.config.remove_extension(media_type, ext):
                self.populate_list(list_widget, media_type)
