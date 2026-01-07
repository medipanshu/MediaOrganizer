import os
from PyQt6.QtWidgets import QListView, QAbstractItemView, QFileIconProvider, QApplication, QStyle, QStyledItemDelegate
from PyQt6.QtCore import Qt, QAbstractListModel, QSize, QFileInfo, pyqtSignal, QRunnable, QThreadPool, QObject, pyqtSlot, QThread, QRect
from PyQt6.QtGui import QIcon, QPixmap, QImageReader, QImage, QPainter, QColor, QBrush, QFontMetrics

# Try importing OpenCV globally to avoid repeated overhead
try:
    import cv2
    # Suppress ffmpeg/opencv warnings globally
    os.environ["OPENCV_LOG_LEVEL"] = "OFF"
    try:
        if hasattr(cv2, 'utils') and hasattr(cv2.utils, 'logging'):
            cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
    except AttributeError:
        pass 
except ImportError:
    cv2 = None

class ThumbnailRunnable(QRunnable):
    def __init__(self, index_row, file_path, file_type, icon_provider, result_signal):
        super().__init__()
        self.index_row = index_row
        self.file_path = file_path
        self.file_type = file_type
        self.icon_provider = icon_provider
        self.result_signal = result_signal # Shared signal from Loader

    def run(self):
        image = QImage()
        
        # Cache setup
        import hashlib
        cache_dir = os.path.join(os.getcwd(), ".thumbnails")
        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir)
            except OSError:
                pass # concurrency
                
        # Hash file path to get unique cache filename
        file_hash = hashlib.md5(self.file_path.encode('utf-8')).hexdigest()
        cache_path = os.path.join(cache_dir, f"{file_hash}.jpg")
        
        # 1. Try loading from cache
        if os.path.exists(cache_path):
            reader = QImageReader(cache_path)
            image = reader.read()
            if not image.isNull():
                 self.result_signal.emit(self.index_row, image)
                 return

        # 2. Generate if not cached
        if self.file_type == 'image':
            reader = QImageReader(self.file_path)
            # Read size first to calculate aspect ratio
            # optimization: removed reader.canRead() check to avoid double open overhead
            original_size = reader.size()
            if original_size.isValid():
                # Calculate scaled size ensuring we don't distort
                target_size = original_size.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(target_size)
                image = reader.read()
                
        elif self.file_type == 'video':
            if cv2 is None:
                print("OpenCV not found. Install opencv-python for video thumbnails.")
            else:
                try:
                    # Capture video - Force FFMPEG backend if possible for better compatibility
                    # If that fails, it usually falls back, but let's try ANY if FFMPEG is issue
                    # Actually, CAP_ANY is default. Let's try explicit FFMPEG first.
                    cap = cv2.VideoCapture(self.file_path, cv2.CAP_FFMPEG)
                
                    if not cap.isOpened():
                        # Fallback to default
                        cap = cv2.VideoCapture(self.file_path)
                        
                    if cap.isOpened():
                        # Read the first valid frame
                        # Sometimes the first few frames are empty/black/corrupt
                        for i in range(5):
                            ret, frame = cap.read()
                            if ret and frame is not None and frame.size > 0:
                                # Convert to RGB (OpenCV uses BGR)
                                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                
                                # Convert to QImage
                                h, w, ch = rgb_frame.shape
                                bytes_per_line = ch * w
                                temp_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                                
                                # Scale it
                                image = temp_image.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                                
                                # Explicitly copy
                                image = image.copy()
                                break # Found a frame
                            else:
                                # Try seeking a bit? 
                                pass
                        
                        if image.isNull():
                            print(f"Failed to extract any frame from: {self.file_path}")
                            
                        cap.release()
                    else:
                        print(f"Could not open video file: {self.file_path}")
                except Exception as e:
                    print(f"Error generating video thumbnail for {self.file_path}: {e}")

        # 3. Save to cache (if we generated something)
        if not image.isNull():
            # Ensure cache directory still exists (user might have deleted it)
            if not os.path.exists(cache_dir):
                try:
                    os.makedirs(cache_dir)
                except OSError:
                    pass
            image.save(cache_path, "JPG", quality=80)
            
        # If image is null, we can return empty QImage, main thread handles fallback
        self.result_signal.emit(self.index_row, image)

class ThumbnailLoader(QObject):
    # Centralized signal to avoid per-runnable QObjects
    # Using 'object' instead of 'QImage' to avoid potential type resolution issues across threads
    thumbnail_loaded = pyqtSignal(int, object)
    task_canceled = pyqtSignal(int) # New signal for cache clearing

    def __init__(self):
        super().__init__()
        self.thread_pool = QThreadPool()
        # Keep concurrency low to prevent UI stutter
        # REDUCED TO 2 to fix initial UI lag
        self.max_workers = 2 
        self.thread_pool.setMaxThreadCount(self.max_workers)
        
        self.active_tasks = 0
        self.pending_tasks = [] # Stack for LIFO behavior
        self._active_runnables = set()
        
        self.visibility_checker = None # Function to check if a row is visible
        
        # Connect internal management
        self.thumbnail_loaded.connect(self._on_thumbnail_finished)
        
    def set_visibility_checker(self, checker):
        """Set a function(row) -> bool to check visibility."""
        self.visibility_checker = checker

    def load_thumbnail(self, index_row, file_path, file_type, icon_provider):
        # Add to stack (LIFO)
        # Note: Callback is removed, listeners should connect to thumbnail_loaded signal
        task = (index_row, file_path, file_type, icon_provider)
        self.pending_tasks.append(task)
        self.schedule()
        
    def schedule(self):
        # While we have capacity and tasks
        while self.active_tasks < self.max_workers and self.pending_tasks:
            # Pop the LATEST requested task (LIFO)
            task = self.pending_tasks.pop() 
            index_row = task[0]
            
            # CHECK VISIBILITY
            # If the user scrolled past this item, discard it!
            if self.visibility_checker:
                if not self.visibility_checker(index_row):
                    # Signal that we canceled this so Model can clear "Loading" state
                    self.task_canceled.emit(index_row)
                    continue
            
            self.start_task(task)

    def start_task(self, task):
        index_row, file_path, file_type, icon_provider = task
        
        # Pass the shared signal
        runnable = ThumbnailRunnable(index_row, file_path, file_type, icon_provider, self.thumbnail_loaded)
        
        self.active_tasks += 1
        self._active_runnables.add(runnable)
        self.thread_pool.start(runnable)

    @pyqtSlot(int, object)
    def _on_thumbnail_finished(self, row, image):
        # Manage resources (called on Main Thread via Signal)
        self.active_tasks -= 1
        
        # We don't need to manually remove from self._active_runnables set here 
        # because the centralized signal usage changed object lifecycle assumptions.
        # But for correctness with 'cancel' logic, we just rely on LIFO stack clearing.
        
        # Schedule next
        self.schedule()
        
    def cancel_pending_tasks(self):
        """Clear all pending thumbnail requests."""
        # Optional: Notify cancellation for all? 
        # For bulk clear (folder switch), we clear cache anyway, so no need to emit individual signals.
        self.pending_tasks.clear()

class GalleryModel(QAbstractListModel):
    FileTypeRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, media_files=None):
        super().__init__()
        self.media_files = media_files if media_files else []
        self.icon_cache = {}
        self.file_icon_provider = QFileIconProvider()
        self.thumbnail_loader = ThumbnailLoader()
        # Connect to the centralized signals
        self.thumbnail_loader.thumbnail_loaded.connect(self.on_thumbnail_loaded)
        self.thumbnail_loader.task_canceled.connect(self.on_task_canceled)
        self.loading_icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)

    def update_data(self, media_files):
        # Cancel any pending loads from previous folder
        self.thumbnail_loader.cancel_pending_tasks()
        
        self.beginResetModel()
        self.media_files = media_files
        self.icon_cache.clear() # Clear cache on reload
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self.media_files)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        file_data = self.media_files[row]
        # file_data structure: (id, file_path, filename, extension, file_type, date, size) based on DB
        file_path = file_data[1]
        filename = file_data[2]
        file_type = file_data[4]

        if role == Qt.ItemDataRole.DisplayRole:
            return filename
            
        if role == self.FileTypeRole:
            return file_type

        if role == Qt.ItemDataRole.DecorationRole:
            # Check cache
            if row in self.icon_cache:
                return self.icon_cache[row]
            
            # Start async load if not in cache (and not already requested ideally, but cache check covers completed)
            self.icon_cache[row] = self.loading_icon # Mark as loading/requested
            
            # Request load (callback removed)
            self.thumbnail_loader.load_thumbnail(
                row, file_path, file_type, self.file_icon_provider
            )
            return self.loading_icon
            
        if role == Qt.ItemDataRole.UserRole:
            return file_path # For opening
        
        if role == Qt.ItemDataRole.ToolTipRole:
            return filename
            
        return None

    @pyqtSlot(int, object)
    def on_thumbnail_loaded(self, row, image):
        icon = None
        if not image.isNull():
            icon = QIcon(QPixmap.fromImage(image))
        else:
             # Fallback if async gen failed or empty (video or bad image)
             if row < len(self.media_files):
                 file_path = self.media_files[row][1]
                 icon = self.file_icon_provider.icon(QFileInfo(file_path))

        if icon:
            # Validate row is still within bounds (model might have been cleared)
            if row < self.rowCount():
                self.icon_cache[row] = icon
                index = self.index(row, 0)
                if index.isValid():
                    self.dataChanged.emit(index, index, [Qt.ItemDataRole.DecorationRole])

    @pyqtSlot(int)
    def on_task_canceled(self, row):
        # Remove the "Loading" marker from cache so it can be requested again if it becomes visible
        if row in self.icon_cache:
            del self.icon_cache[row]

class MediaDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__()
        self.thumb_size = 100
        self.padding = 10
        self.text_height = 40
        self.item_width = 120
        self.item_height = 160 # thumb + padding + text
        
        # Load Video Overlay Icon
        # Assuming relative path from CWD (main.py location)
        self.video_overlay_icon = QPixmap("icons/icons8-vlc-media-player-24.png")
        if self.video_overlay_icon.isNull():
             # Fallback if path wrong or missing try searching around or just print
             print("Warning: Could not load video overlay icon from icons/icons8-vlc-media-player-24.png")
        
    def paint(self, painter, option, index):
        if not index.isValid():
            return
            
        painter.save()
        
        # Draw Selection Background
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        # Data
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        file_type = index.data(GalleryModel.FileTypeRole)
        
        # Rects
        rect = option.rect
        
        # 1. Draw Icon
        icon_rect = QRect(rect.x() + (rect.width() - self.thumb_size) // 2, 
                          rect.y() + self.padding, 
                          self.thumb_size, self.thumb_size)
        
        if isinstance(icon, QIcon):
             icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)
        elif isinstance(icon, QPixmap): # Backup
             painter.drawPixmap(icon_rect, icon)
             
        # 1.5 Draw Video Overlay
        if file_type == 'video' and not self.video_overlay_icon.isNull():
            # Draw icon in bottom-right corner of the thumbnail rect with some padding
            overlay_w = self.video_overlay_icon.width()
            overlay_h = self.video_overlay_icon.height()
            
            # Position: Bottom Right inside icon area
            x = icon_rect.right() - overlay_w
            y = icon_rect.bottom() - overlay_h
            
            painter.drawPixmap(x, y, self.video_overlay_icon)
        
        # 2. Draw Text
        text_rect = QRect(rect.x(), 
                          rect.y() + self.thumb_size + self.padding + 5, 
                          rect.width(), 
                          self.text_height)
        
        if text:
            if option.state & QStyle.StateFlag.State_Selected:
                painter.setPen(option.palette.highlightedText().color())
            else:
                painter.setPen(option.palette.text().color())
                
            # Alignment and Elision - Optimized
            # We use standard drawText with wrapping, avoiding the expensive elidedText() calculation per frame
            painter.drawText(text_rect, 
                           Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, 
                           text)
                             
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(self.item_width, self.item_height)

class GalleryView(QListView):
    media_opened = pyqtSignal(str) # Emit file path

    def __init__(self):
        super().__init__()
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setSpacing(10)
        
        # Use Delegate for precise rendering
        self.setItemDelegate(MediaDelegate(self))
        
        # Crucial for performance with heavy delegates/large lists
        self.setUniformItemSizes(True) 
        
        # These are less critical now that delegate handles size, but good defaults
        self.setGridSize(QSize(120, 160)) 
        
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.doubleClicked.connect(self._on_item_double_clicked)

    def _on_item_double_clicked(self, index):
        file_path = index.data(Qt.ItemDataRole.UserRole)
        if file_path:
            self.media_opened.emit(file_path)
            
    def is_row_visible(self, row):
        """Check if the given row is currently visible in the viewport."""
        index = self.model().index(row, 0)
        if not index.isValid():
            return False
        
        rect = self.visualRect(index)
        visible_rect = self.viewport().rect()
        
        # Add a buffer/margin to reduce strict cancellation flicker
        # Keep items that are just outside the view (e.g., 200px margin)
        buffered_rect = visible_rect.adjusted(-200, -200, 200, 200)
        
        return buffered_rect.intersects(rect)
