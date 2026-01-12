import os
import time
from PyQt6.QtCore import QThread, pyqtSignal
from src.core.database import MediaDatabase
from src.core.config import ConfigManager

class MediaScanner(QThread):
    progress_update = pyqtSignal(str) # Emit status messages
    media_found = pyqtSignal(dict)    # Emit found media data (optional)
    finished_scan = pyqtSignal()
    
    def __init__(self, folders_to_scan=None):
        super().__init__()
        self.folders_to_scan = folders_to_scan if folders_to_scan else []
        self.db = MediaDatabase()
        self.config = ConfigManager() # Load config
        self._is_running = True
        self.batch_size = 50

    def run(self):
        """Main thread loop."""
        self.db.init_db() # Ensure DB is ready
        total_files = 0
        batch_buffer = []

        # Load extensions fresh for each run
        image_exts = self.config.get_image_extensions()
        video_exts = self.config.get_video_extensions()

        for folder in self.folders_to_scan:
            if not self._is_running:
                break
                
            self.progress_update.emit(f"Scanning directory: {folder}")
            
            for root, dirs, files in os.walk(folder):
                # Exclude system directories
                dirs[:] = [d for d in dirs if d not in ['$RECYCLE.BIN', 'System Volume Information'] and not d.startswith('.')]
                
                if not self._is_running:
                    break
                
                # Emit directory progress
                # Shorten path for display if needed, but full path is fine for now
                self.progress_update.emit(f"Scanning: {root}")

                for file in files:
                    if not self._is_running:
                        break
                        
                    file_path = os.path.normpath(os.path.join(root, file))
                    self.progress_update.emit(f"Found: {file}")
                    
                    ext = os.path.splitext(file)[1].lower()
                    
                    file_type = None
                    if ext in image_exts:
                        file_type = 'image'
                    elif ext in video_exts:
                        file_type = 'video'
                    
                    if file_type:
                        batch_buffer.append((file_path, file_type))
                        
                        if len(batch_buffer) >= self.batch_size:
                            count = self.db.batch_insert_media(batch_buffer)
                            total_files += count
                            batch_buffer = []
        
        # Flush remaining items
        if batch_buffer and self._is_running:
            count = self.db.batch_insert_media(batch_buffer)
            total_files += count

        self.progress_update.emit(f"Scan complete. Found {total_files} new files.")
        
        # Save scan stats
        scan_info = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'Completed',
            'new_files_count': total_files,
            'total_files_scanned': 'Unknown' # Could track this if needed
        }
        self.config.set_last_scan_info(scan_info)
        
        self.finished_scan.emit()

    def stop(self):
        """Stops the scanning process gracefully."""
        self._is_running = False
        self.wait()
