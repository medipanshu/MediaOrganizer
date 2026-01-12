import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QGroupBox, QFormLayout, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from src.core.config import ConfigManager
from src.core.database import MediaDatabase

class SizeCalculator(QThread):
    finished_calculation = pyqtSignal(int, int) # db_size, thumb_size

    def __init__(self, db_path, thumb_path):
        super().__init__()
        self.db_path = db_path
        self.thumb_path = thumb_path

    def run(self):
        # DB Size
        db_size = 0
        if os.path.exists(self.db_path):
            try:
                db_size = os.path.getsize(self.db_path)
            except OSError:
                pass
        
        # Thumbnails Size
        thumb_size = 0
        if os.path.exists(self.thumb_path):
            for dirpath, dirnames, filenames in os.walk(self.thumb_path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        try:
                            thumb_size += os.path.getsize(fp)
                        except OSError:
                            pass
        
        self.finished_calculation.emit(db_size, thumb_size)

class DbOptimizer(QThread):
    finished_optimization = pyqtSignal(bool) # success

    def __init__(self):
        super().__init__()
        self.db = MediaDatabase()

    def run(self):
        result = self.db.optimize_db()
        self.finished_optimization.emit(result)

class StatsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Application Statistics")
        self.resize(400, 350)
        
        # Add Minimize Button
        self.setWindowFlags(self.windowFlags() | 
                          Qt.WindowType.WindowMinimizeButtonHint | 
                          Qt.WindowType.WindowSystemMenuHint)
                          
        self.config = ConfigManager()
        self.calc_thread = None
        self.opt_thread = None
        self.init_ui()
        self.refresh_stats()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Usage Info Group
        usage_group = QGroupBox("Disk Usage")
        usage_layout = QFormLayout()
        
        # DB Row with Compact Button
        db_row_layout = QHBoxLayout()
        self.lbl_db_size = QLabel("Calculating...")
        db_row_layout.addWidget(self.lbl_db_size)
        
        self.btn_compact = QPushButton("Compact Database")
        self.btn_compact.setToolTip("Reclaim unused space (VACUUM)")
        self.btn_compact.clicked.connect(self.compact_db)
        # Make it smaller or less prominent? Standard is fine.
        db_row_layout.addWidget(self.btn_compact)
        
        # Thumbnails Row
        self.lbl_thumb_size = QLabel("Calculating...")
        self.lbl_total_size = QLabel("Calculating...")
        
        usage_layout.addRow("Database Size:", db_row_layout)
        usage_layout.addRow("Thumbnails Size:", self.lbl_thumb_size)
        usage_layout.addRow("Total App Usage:", self.lbl_total_size)
        
        usage_group.setLayout(usage_layout)
        layout.addWidget(usage_group)

        # Last Scan Info Group
        scan_group = QGroupBox("Last Scan Information")
        scan_layout = QFormLayout()
        
        self.lbl_scan_date = QLabel("Unknown")
        self.lbl_scan_status = QLabel("Unknown")
        self.lbl_scan_files = QLabel("0")
        
        scan_layout.addRow("Date:", self.lbl_scan_date)
        scan_layout.addRow("Status:", self.lbl_scan_status)
        scan_layout.addRow("New Files Found:", self.lbl_scan_files)
        
        scan_group.setLayout(scan_layout)
        layout.addWidget(scan_group)

        # Buttons
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_stats)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)

    def refresh_stats(self):
        # 1. Update Scan Info (Instant)
        info = self.config.get_last_scan_info()
        self.lbl_scan_date.setText(str(info.get('timestamp', 'Never')))
        self.lbl_scan_status.setText(str(info.get('status', 'N/A')))
        self.lbl_scan_files.setText(str(info.get('new_files_count', 0)))

        # 2. Disk Usage (Async)
        self.lbl_db_size.setText("Calculating...")
        self.lbl_thumb_size.setText("Calculating...")
        self.lbl_total_size.setText("Calculating...")
        
        # Start thread
        if self.calc_thread and self.calc_thread.isRunning():
            self.calc_thread.wait() 
            
        db_path = "media.db"
        thumb_path = ".thumbnails"
        
        self.calc_thread = SizeCalculator(db_path, thumb_path)
        self.calc_thread.finished_calculation.connect(self.on_stats_calculated)
        self.calc_thread.start()

    def on_stats_calculated(self, db_size, thumb_size):
        self.lbl_db_size.setText(self.format_size(db_size))
        self.lbl_thumb_size.setText(self.format_size(thumb_size))
        self.lbl_total_size.setText(self.format_size(db_size + thumb_size))

    def compact_db(self):
        # Safety Check: Is Scanner Running?
        # Requires accessing MainWindow.scanner
        parent = self.parent()
        if parent and hasattr(parent, 'scanner') and parent.scanner and parent.scanner.isRunning():
            QMessageBox.warning(self, "Cannot Compact", 
                                "A media scan is currently running.\n\nPlease wait for the scan to finish before compacting the database to avoid conflicts.")
            return

        # Double check user intent
        reply = QMessageBox.question(self, "Compact Database", 
                                     "This operation will reclaim unused disk space from deletions.\n\n"
                                     "The application will be locked during this process, but you can minimize this window.\n"
                                     "Do you want to proceed?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                                     
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Prepare UI
        self.lbl_db_size.setText("Compacting...")
        self.btn_compact.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        
        # Start Thread
        self.opt_thread = DbOptimizer()
        self.opt_thread.finished_optimization.connect(self.on_compact_finished)
        self.opt_thread.start()

    def on_compact_finished(self, success):
        self.btn_compact.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.close_btn.setEnabled(True)
        
        if success:
            QMessageBox.information(self, "Success", "Database compacted successfully.")
        else:
            QMessageBox.warning(self, "Error", "Failed to compact database. Check logs.")
            
        self.refresh_stats()

    def format_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = 0
        p = 0 # power of 1024
        
        import math
        if size_bytes > 0:
             i = int(math.floor(math.log(size_bytes, 1024)))
             
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        
        if i >= len(size_name):
             i = len(size_name) - 1
             
        return "%s %s" % (s, size_name[i])

