import sys
import os
import subprocess
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QFileDialog, QLabel, QProgressBar, QMessageBox, QFrame, QDialog, QScrollArea,
                             QSplitter, QTreeView, QListView, QApplication, QMenu, QStyle)
from PyQt6.QtCore import Qt, QUrl, QDir, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QDesktopServices, QPixmap, QAction, QFileSystemModel, QStandardItemModel, QStandardItem
from src.core.database import MediaDatabase
from src.core.scanner import MediaScanner
from src.ui.gallery import GalleryView, GalleryModel, GallerySeparator
from src.ui.metadata_panel import MetadataPanel

class DataLoader(QObject):
    media_loaded = pyqtSignal(list)
    folders_loaded = pyqtSignal(list)
    finished = pyqtSignal()

    def run(self):
        # Create a local db instance for thread safety
        db = MediaDatabase()
        
        # 1. Load Media
        media = db.get_all_media()
        self.media_loaded.emit(media)
        
        # 2. Load Folders
        folders = db.get_image_folders()
        self.folders_loaded.emit(folders)
        
        self.finished.emit()

class ImageViewerById(QDialog):
    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(os.path.basename(image_path))
        self.resize(800, 600)
        
        layout = QVBoxLayout()
        self.scroll_area = QScrollArea()
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            # Scale if too large, but keep aspect ratio
            if pixmap.width() > 1600 or pixmap.height() > 1200:
                 pixmap = pixmap.scaled(1600, 1200, Qt.AspectRatioMode.KeepAspectRatio)
            self.label.setPixmap(pixmap)
        else:
            self.label.setText("Could not load image.")

        self.scroll_area.setWidget(self.label)
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)
        self.setLayout(layout)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Local AI Media Organizer")
        
        # Set default size to screen size
        screen = QApplication.primaryScreen()
        if screen:
            self.resize(screen.availableGeometry().size())
        else:
            self.resize(1200, 800)
            
        self.showMaximized()

        self.db = MediaDatabase()
        self.scanner = None
        self.loader_thread = None
        
        # Filtering State
        self.current_media_data = [] # Source of truth (unfiltered)
        self.active_filters = {
            'types': {'image', 'video'}, # Default: Show both
            'exts': None # None means "All", set() means "Specific"
        }
        self.sort_mode = 'date' # 'date', 'size', 'name'
        self.collapsed_sections = set() # Set of keys (generic)
        
        self.init_ui()
        # self.load_media() # Removed synchronous call
        self.start_async_loading()

    # ... (start_async_loading, on_media_loaded, on_folders_loaded, on_loading_finished, init_ui remain unchanged)
    # ... (skipping to show_filter_menu to be brief in replacement context? 
    # Actually I need to be careful with line numbers. I'll target specific blocks.)

    def show_filter_menu(self):
        menu = QMenu(self)
        
        # Helper to get extensions by type
        image_exts = set()
        video_exts = set()
        
        for item in self.current_media_data:
            path = item[1]
            m_type = item[4]
            ext = os.path.splitext(path)[1].lower()
            
            if m_type == 'image':
                image_exts.add(ext)
            elif m_type == 'video':
                video_exts.add(ext)

        # --- Images Submenu ---
        images_menu = menu.addMenu("Images")
        
        img_sel_all = QAction("Select All", self)
        img_sel_all.triggered.connect(lambda: self.set_category_filter_state('image', True))
        images_menu.addAction(img_sel_all)

        img_desel_all = QAction("Deselect All", self)
        img_desel_all.triggered.connect(lambda: self.set_category_filter_state('image', False))
        images_menu.addAction(img_desel_all)
        
        images_menu.addSeparator()
        
        if image_exts:
            sorted_img_exts = sorted(list(image_exts))
            current_exts_filter = self.active_filters['exts']
            
            for ext in sorted_img_exts:
                action = QAction(ext, self)
                action.setCheckable(True)
                is_checked = (current_exts_filter is None) or (ext in current_exts_filter)
                action.setChecked(is_checked)
                action.triggered.connect(lambda checked, e=ext: self.toggle_filter('exts', e, checked, type_context='image'))
                images_menu.addAction(action)

        # --- Videos Submenu ---
        videos_menu = menu.addMenu("Videos")
        
        vid_sel_all = QAction("Select All", self)
        vid_sel_all.triggered.connect(lambda: self.set_category_filter_state('video', True))
        videos_menu.addAction(vid_sel_all)

        vid_desel_all = QAction("Deselect All", self)
        vid_desel_all.triggered.connect(lambda: self.set_category_filter_state('video', False))
        videos_menu.addAction(vid_desel_all)
        
        videos_menu.addSeparator()
        
        if video_exts:
            sorted_vid_exts = sorted(list(video_exts))
            current_exts_filter = self.active_filters['exts']
            
            for ext in sorted_vid_exts:
                action = QAction(ext, self)
                action.setCheckable(True)
                is_checked = (current_exts_filter is None) or (ext in current_exts_filter)
                action.setChecked(is_checked)
                action.triggered.connect(lambda checked, e=ext: self.toggle_filter('exts', e, checked, type_context='video'))
                videos_menu.addAction(action)
        
        menu.exec(self.filter_btn.mapToGlobal(self.filter_btn.rect().bottomLeft()))

    def set_category_filter_state(self, category_type, state):
        # 1. Update Type Filter
        if state:
            self.active_filters['types'].add(category_type)
        else:
            self.active_filters['types'].discard(category_type)
            
        # 2. Update Extension Filter
        # If selecting all, we need to make sure extensions for this type are effectively included.
        # If deselecting all, we need to make sure extensions for this type are effectively excluded.
        
        # Collect relevant extensions for this category
        relevant_exts = set()
        for item in self.current_media_data:
            if item[4] == category_type:
                ext = os.path.splitext(item[1])[1].lower()
                relevant_exts.add(ext)
                
        current_ext_filter = self.active_filters['exts']
        
        if state:
            # SELECT ALL
            if current_ext_filter is not None:
                # We have a specific list, let's add these to it
                current_ext_filter.update(relevant_exts)
                # Optimization: If we now have ALL possible extensions, we can revert to None? 
                # Doing simply adding is safer.
        else:
            # DESELECT ALL
            if current_ext_filter is None:
                # Transition from "All Allowed" to "Specific Allowed" (All MINUS these)
                all_possible = {os.path.splitext(x[1])[1].lower() for x in self.current_media_data}
                self.active_filters['exts'] = all_possible
                self.active_filters['exts'].difference_update(relevant_exts)
            else:
                # Remove them from existing specific list
                current_ext_filter.difference_update(relevant_exts)
                
        self.apply_filters()



    def toggle_filter(self, category, value, checked, type_context=None):
        if category == 'types':
            if checked:
                self.active_filters['types'].add(value)
            else:
                self.active_filters['types'].discard(value)
        
        elif category == 'exts':
            current = self.active_filters['exts']
            
            if checked and type_context:
                self.active_filters['types'].add(type_context)

            if current is None:
                # Transition from All -> Specific (minus one)
                if not checked:
                    # Gather all current
                    all_possible = {os.path.splitext(x[1])[1].lower() for x in self.current_media_data}
                    self.active_filters['exts'] = all_possible
                    self.active_filters['exts'].discard(value)
            else:
                if checked:
                    current.add(value)
                else:
                    current.discard(value)
        
        self.apply_filters()

    def apply_filters(self):
        filtered_media = []
        
        allowed_types = self.active_filters['types']
        allowed_exts = self.active_filters['exts']
        
        for item in self.current_media_data:
            # DB Schema: 0=id, 1=path, 2=filename, 3=ext, 4=type
            m_path = item[1]
            m_type = item[4] # Correct index for 'file_type'
            
            if m_type not in allowed_types:
                continue
                
            if allowed_exts is not None:
                ext = os.path.splitext(m_path)[1].lower()
                if ext not in allowed_exts:
                    continue
            
            filtered_media.append(item)
            
        # Inject Separators if sorted by date OR size OR name
        if self.sort_mode in ['date', 'size', 'name']:
            final_data = self.inject_separators(filtered_media)
        else:
            final_data = filtered_media

        self.gallery_model.update_data(final_data)
        self.statusBar().showMessage(f"Showing {len(filtered_media)} files (Filtered from {len(self.current_media_data)})")
        
        # Update toggle button text if enabled
        if self.toggle_all_btn.isEnabled():
            self.update_toggle_button_text()

    def start_async_loading(self):
        self.statusBar().showMessage("Loading media...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0) # Indeterminate
        
        self.loader_thread = QThread()
        self.worker = DataLoader()
        self.worker.moveToThread(self.loader_thread)
        
        self.loader_thread.started.connect(self.worker.run)
        self.worker.media_loaded.connect(self.on_media_loaded)
        self.worker.folders_loaded.connect(self.on_folders_loaded)
        self.worker.finished.connect(self.on_loading_finished)
        self.worker.finished.connect(self.loader_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.loader_thread.finished.connect(self.loader_thread.deleteLater)
        
        self.loader_thread.start()

    def on_media_loaded(self, media):
        print(f"DEBUG: Media loaded. Count: {len(media)}")
        self.current_media_data = media
        self.apply_filters()
        
    def on_folders_loaded(self, folders):
        self.update_image_folder_tree(folders)

    def on_loading_finished(self):
        self.statusBar().showMessage("Ready")
        self.progress_bar.setVisible(False)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Toolbar / Control Area
        controls_layout = QHBoxLayout()
        
        # Sidebar Toggle
        self.toggle_sidebar_btn = QPushButton()
        self.toggle_sidebar_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarMenuButton))
        self.toggle_sidebar_btn.setToolTip("Toggle Sidebar")
        self.toggle_sidebar_btn.clicked.connect(self.toggle_sidebar)
        controls_layout.addWidget(self.toggle_sidebar_btn)
        
        self.add_folder_btn = QPushButton("Add Folder")
        self.add_folder_btn.clicked.connect(self.select_folder)
        controls_layout.addWidget(self.add_folder_btn)

        self.manage_formats_btn = QPushButton("Manage Formats")
        self.manage_formats_btn.clicked.connect(self.open_format_dialog)
        controls_layout.addWidget(self.manage_formats_btn)
        
        # Filter button moved to Gallery Ribbon
        # self.filter_btn = QPushButton("Filter")
        # self.filter_btn.clicked.connect(self.show_filter_menu)
        # controls_layout.addWidget(self.filter_btn)

        # App Stats Button
        self.stats_btn = QPushButton("App Stats")
        self.stats_btn.clicked.connect(self.show_app_stats)
        controls_layout.addWidget(self.stats_btn)

        # View Thumbnails Button
        self.view_thumbs_btn = QPushButton("View Thumbnails")
        self.view_thumbs_btn.clicked.connect(self.open_thumbnails_folder)
        controls_layout.addWidget(self.view_thumbs_btn)
        
        controls_layout.addStretch()
        main_layout.addLayout(controls_layout)

        # Main Splitter (Horizontal)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # Left Panel (Vertical Splitter: File Tree + Image Folders)
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 1. File Tree (Top)
        # 1. File Tree (Top) Container
        top_left_widget = QWidget()
        top_left_layout = QVBoxLayout(top_left_widget)
        top_left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.file_model = QFileSystemModel()
        self.file_model.setRootPath(QDir.rootPath())
        self.file_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot | QDir.Filter.Drives)
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.file_model)
        self.tree_view.setHeaderHidden(True)
        for i in range(1, 4):
            self.tree_view.hideColumn(i)
        self.tree_view.clicked.connect(self.on_tree_clicked)
        
        top_left_layout.addWidget(self.tree_view)
        
        # Scan Button
        self.scan_btn = QPushButton("Deep Scan Directory")
        self.scan_btn.setEnabled(False) # Disabled until folder selected
        self.scan_btn.clicked.connect(self.scan_selected_directory)
        top_left_layout.addWidget(self.scan_btn)
        
        left_splitter.addWidget(top_left_widget)
        
        # 2. Image Folders Tree (Bottom) Container
        bottom_left_widget = QWidget()
        bottom_left_layout = QVBoxLayout(bottom_left_widget)
        bottom_left_layout.setContentsMargins(0, 0, 0, 0)

        self.image_folder_model = QStandardItemModel()
        self.image_folder_model.setHorizontalHeaderLabels(["Media Folders"])
        self.image_folder_view = QTreeView()
        self.image_folder_view.setModel(self.image_folder_model)
        self.image_folder_view.setHeaderHidden(True)
        self.image_folder_view.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self.image_folder_view.clicked.connect(self.on_image_folder_clicked)
        
        bottom_left_layout.addWidget(self.image_folder_view)
        
        # Remove Folder Button
        self.remove_folder_btn = QPushButton("Remove Folder")
        self.remove_folder_btn.setEnabled(False)
        self.remove_folder_btn.clicked.connect(self.remove_selected_folder)
        bottom_left_layout.addWidget(self.remove_folder_btn)
        
        left_splitter.addWidget(bottom_left_widget)
        
        # 3. Metadata Panel (Bottom-most)
        self.metadata_panel = MetadataPanel()
        left_splitter.addWidget(self.metadata_panel)
        
        # Set initial sizes for left panel (FileTree, FolderTree, Metadata)
        # Give metadata some space
        left_splitter.setSizes([300, 200, 300])

        # Add left split to main split
        self.splitter.addWidget(left_splitter)

        # Right Panel: content area (Progress + Gallery)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        # Revert margin to 0 to remove gap
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Combined Container for Ribbon + Gallery
        self.combined_frame = QFrame()
        self.combined_frame.setFrameShape(QFrame.Shape.NoFrame)
        # Apply styled border to the combination
        self.combined_frame.setStyleSheet("""
            .QFrame {
                border: 1px solid #c0c0c0;
            }
        """)
        combined_layout = QVBoxLayout(self.combined_frame)
        combined_layout.setContentsMargins(0, 0, 0, 0)
        combined_layout.setSpacing(0)

        # Gallery Ribbon (Toolbar Container)
        self.ribbon_widget = QWidget()
        # Remove borders from ribbon itself, rely on container border
        self.ribbon_widget.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5; 
                border: none;
                border-bottom: 1px solid #e0e0e0; /* Optional faint separator or none? User said remove below line. */
                /* User said remove below line. Let's make it none or same color as bg? */
                /* Actually, sticking to 'remove the below line' -> border-bottom: 0px */
                border-bottom: 0px; 
            }
            QPushButton {
                 background-color: #ffffff;
                 border: 1px solid #c0c0c0;
                 border-radius: 3px;
                 padding: 2px 10px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.ribbon_widget.setFixedHeight(34)
        
        ribbon_layout = QHBoxLayout(self.ribbon_widget)
        ribbon_layout.setContentsMargins(10, 2, 10, 2)
        ribbon_layout.setSpacing(10)
        
        ribbon_layout.addStretch() 
        
        # Filter Button
        self.filter_btn = QPushButton("Filter")
        self.filter_btn.setToolTip("Filter Media")
        self.filter_btn.setFixedSize(60, 24)
        self.filter_btn.clicked.connect(self.show_filter_menu)
        ribbon_layout.addWidget(self.filter_btn)
        
        # Sort Button
        self.sort_btn = QPushButton("Sort")
        self.sort_btn.setToolTip("Sort Media")
        self.sort_btn.setFixedSize(60, 24) 
        self.sort_btn.clicked.connect(self.show_sort_menu)
        ribbon_layout.addWidget(self.sort_btn)
        
        # Toggle Collapse/Expand Button
        self.toggle_all_btn = QPushButton("Collapse All")
        self.toggle_all_btn.setToolTip("Toggle expand/collapse for all sections")
        self.toggle_all_btn.clicked.connect(self.on_toggle_all)
        self.toggle_all_btn.setEnabled(self.sort_mode in ['date', 'size', 'name'])
        ribbon_layout.addWidget(self.toggle_all_btn)
        
        combined_layout.addWidget(self.ribbon_widget)
        
        # Progress Bar (Inside container? Or above? Usually overlays or independent. 
        # Plan had it separate. Let's put it inside or leave it?
        # If I put it inside combined layout, it pushes gallery down.
        # Let's keep existing structure where progress bar was separate?
        # Wait, progress bar was in right_layout.
        # Let's add combined_frame to right_layout. But where does GalleryView go?
        # GalleryView needs to be INSIDE combined_frame to share border.
        
        # Gallery (Moved inside combined layout)
        self.gallery_model = GalleryModel()
        self.gallery_view = GalleryView()
        self.gallery_view.setModel(self.gallery_model)
        # Remove Gallery's own border so it blends with container
        self.gallery_view.setFrameShape(QFrame.Shape.NoFrame)
        
        self.gallery_model.thumbnail_loader.set_visibility_checker(self.gallery_view.is_row_visible)
        
        self.gallery_view.media_opened.connect(self.open_media)
        self.gallery_view.selectionModel().currentChanged.connect(self.on_gallery_selection_changed)
        # Handle simple clicks for collapsing separators
        self.gallery_view.clicked.connect(self.on_item_clicked)
        
        combined_layout.addWidget(self.gallery_view)
        
        right_layout.addWidget(self.combined_frame)

        # Progress Bar (Keep outside or overlay? Let's put it at bottom of right layout or top?)
        # Originally it was separate. Let's add it back to right_layout BELOW combined frame?
        # Or ABOVE.
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(5) # Slim
        right_layout.addWidget(self.progress_bar)
        
        self.splitter.addWidget(right_widget)
        self.splitter.setSizes([300, 900])

        # Status Bar
        self.setStatusBar(self.statusBar())
        self.statusBar().showMessage("Ready")

    def show_sort_menu(self):
        menu = QMenu(self)
        
        # Date
        # Use lambda with explicit arguments to avoid closure issues
        menu.addAction("Date: Newest First", lambda: self.apply_sort('date', reverse=True))
        menu.addAction("Date: Oldest First", lambda: self.apply_sort('date', reverse=False))
        menu.addSeparator()
        
        # Name
        menu.addAction("Name: A-Z", lambda: self.apply_sort('name', reverse=False))
        menu.addAction("Name: Z-A", lambda: self.apply_sort('name', reverse=True))
        menu.addSeparator()
        
        # Size
        menu.addAction("Size: Largest First", lambda: self.apply_sort('size', reverse=True))
        menu.addAction("Size: Smallest First", lambda: self.apply_sort('size', reverse=False))
        
        menu.exec(self.sort_btn.mapToGlobal(self.sort_btn.rect().bottomLeft()))

    def apply_sort(self, sort_key, reverse):
        # Sort current_media_data in place
        # Indices: 2=Filename, 5=Date, 6=Size
        
        key_idx = 5 # Default Date
        if sort_key == 'name':
            key_idx = 2
        elif sort_key == 'size':
            key_idx = 6
            
        try:
            # Simple Sort
            # Note: lower() for filename case-insensitive sort if string
            if sort_key == 'name':
                self.current_media_data.sort(key=lambda x: x[key_idx].lower(), reverse=reverse)
                self.sort_mode = 'name'
            elif sort_key == 'date':
                self.current_media_data.sort(key=lambda x: x[key_idx], reverse=reverse)
                self.sort_mode = 'date'
            elif sort_key == 'size':
                self.current_media_data.sort(key=lambda x: x[key_idx], reverse=reverse)
                # For size sort, we usually want largest first (Reverse=True)
                # If separate buckets are tricky with reverse logic, we just handle buckets based on value.
                self.sort_mode = 'size'
            else:
                self.current_media_data.sort(key=lambda x: x[key_idx], reverse=reverse)
                self.sort_mode = None
                
            self.apply_filters() # Refresh view
            self.statusBar().showMessage(f"Sorted by {sort_key.capitalize()}")
            self.update_sort_buttons_state()

        except Exception as e:
            print(f"Sort Error: {e}")
            self.statusBar().showMessage("Error sorting media")

    def update_sort_buttons_state(self):
        """Updates the enabled state of collapse/expand buttons."""
        enabled = self.sort_mode in ['date', 'size', 'name']
        self.toggle_all_btn.setEnabled(enabled)
        # Also update text to correct state
        if enabled:
            self.update_toggle_button_text()

    def update_toggle_button_text(self):
        """Updates the toggle button text based on current collapsed state."""
        # Find all current keys
        all_keys = set()
        for item in self.current_media_data:
            key = self.get_group_key(item)
            if key is not None:
                all_keys.add(key)
        
        # Check if all keys are in collapsed_sections
        if not all_keys:
             is_all_collapsed = False
        else:
             is_all_collapsed = all_keys.issubset(self.collapsed_sections)
        
        if is_all_collapsed:
            self.toggle_all_btn.setText("Expand All")
        else:
            self.toggle_all_btn.setText("Collapse All")

    def get_group_key(self, item):
        """Helper to extract a grouping key from a media item based on sort mode."""
        if self.sort_mode == 'date':
            date_val = item[5]
            from datetime import datetime
            if isinstance(date_val, str) and len(date_val) >= 7:
                 try:
                     year = int(date_val[:4])
                     month = int(date_val[5:7])
                     return (year, month)
                 except ValueError: pass
            elif isinstance(date_val, datetime):
                 return (date_val.year, date_val.month)
            return (0, 0)
            
        elif self.sort_mode == 'size':
            size_val = item[6] # bytes
            if size_val < 1024: return 0
            if size_val < 10 * 1024: return 1
            if size_val < 1024 * 1024: return 2
            if size_val < 10 * 1024 * 1024: return 3
            if size_val < 100 * 1024 * 1024: return 4
            return 5
            
        elif self.sort_mode == 'name':
            filename = item[2]
            if filename:
                first_char = filename[0].upper()
                if first_char.isalpha():
                    return first_char
            return '#'
            
        return None

    def get_group_label(self, key):
        """Returns visual label for a key."""
        if self.sort_mode == 'date':
            if key == (0, 0): return "Unknown Date"
            import calendar
            try:
                month_name = calendar.month_name[key[1]]
                return f"{month_name} {key[0]}"
            except IndexError: return "Unknown Date"
            
        elif self.sort_mode == 'size':
            labels = {
                0: "Tiny (< 1 KB)",
                1: "Very Small (1 KB - 10 KB)",
                2: "Small (10 KB - 1 MB)",
                3: "Medium (1 MB - 10 MB)",
                4: "Large (10 MB - 100 MB)",
                5: "Huge (> 100 MB)"
            }
            return labels.get(key, "Unknown Size")
            
        elif self.sort_mode == 'name':
            return key
            
        return "Unknown"

    def on_toggle_all(self):
        """Toggles between Collapse All and Expand All."""
        # Check current state
        all_keys = set()
        for item in self.current_media_data:
            key = self.get_group_key(item)
            if key is not None:
                all_keys.add(key)
        
        if not all_keys:
            return

        is_all_collapsed = all_keys.issubset(self.collapsed_sections)
        
        if is_all_collapsed:
            # Expand All
            self.collapsed_sections.clear()
        else:
            # Collapse All
            self.collapsed_sections.update(all_keys)
            
        self.apply_filters()

    def inject_separators(self, media_list):
        """Injects GallerySeparator objects into the list."""
        if not media_list:
            return []
            
        new_list = []
        current_key = None
        
        # We need to know if the current section is collapsed to skip items
        is_current_section_collapsed = False
        
        for item in media_list:
            key = self.get_group_key(item)
            
            # If we returned None key, it means no grouping for this item? 
            # Or should we group under "Unknown"?
            # If sort_mode is active, we should always return a key ideally.
            if key is None:
                new_list.append(item)
                continue
                
            if key != current_key:
                current_key = key
                
                # Check if this new section is collapsed
                # Store key in collapsed_sections. 
                # Note: Keys for date are tuples, size are ints. 
                # To avoid collision if user switches sort mode but keeps set?
                # Actually, set should be cleared on sort change? 
                # Or we prefix keys: ('date', 2025, 1) vs ('size', 3)
                # For simplicity, let's CLEAR collapsed_sections when sort mode changes?
                # We haven't done that yet. Let's assume unique enough or clearing.
                
                # Let's prefix the key in the set to be safe?
                # Or just rely on (year, month) tuple vs int mismatch.
                
                is_current_section_collapsed = (key in self.collapsed_sections)
                
                label = self.get_group_label(key)
                
                # Create Separator
                sep = GallerySeparator(label, key=key, collapsed=is_current_section_collapsed)
                new_list.append(sep)
            
            # Add item ONLY if not collapsed
            if not is_current_section_collapsed:
                new_list.append(item)
            
        return new_list

    def on_item_clicked(self, index):
        if not index.isValid():
            return
            
        # Check if it's a separator
        item_data = index.data(Qt.ItemDataRole.UserRole)
        # With our changes, GallerySeparator returns ITSELF for UserRole
        if isinstance(item_data, GallerySeparator):
            key = item_data.key
            # Key can be int or tuple or None
            if key is not None:
                if key in self.collapsed_sections:
                    self.collapsed_sections.remove(key)
                else:
                    self.collapsed_sections.add(key)
                
                # Refresh view (re-inject separators with new state)
                self.apply_filters()

    def on_gallery_selection_changed(self, current, previous):
        if not current.isValid():
            self.metadata_panel.update_info(None)
            return

        # Use the data directly from the model index
        item_data = current.data(Qt.ItemDataRole.UserRole)
        
        # Check if regular file path (str) or Separator (DateSeparator object)
        if isinstance(item_data, str):
             self.metadata_panel.update_info(item_data)
        else:
             # Separator or None
             self.metadata_panel.update_info(None)

    def toggle_sidebar(self):
        # The left panel is the first widget in the main splitter
        if self.splitter.count() > 0:
            left_panel = self.splitter.widget(0)
            left_panel.setVisible(not left_panel.isVisible())

    def on_tree_clicked(self, index):
        path = self.file_model.filePath(index)
        if path:
            self.filter_media_by_path(path)
            self.scan_btn.setEnabled(True)
            
    def on_image_folder_clicked(self, index):
        item = self.image_folder_model.itemFromIndex(index)
        if item:
            # We need to reconstruct the full path from the tree item
            # Or store the full path in UserRole
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                self.filter_media_by_path(path)
                self.remove_folder_btn.setEnabled(True)

    def remove_selected_folder(self):
        index = self.image_folder_view.currentIndex()
        if not index.isValid():
            return
            
        item = self.image_folder_model.itemFromIndex(index)
        if not item:
            return
            
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            return
            
        # Confirmation Dialog
        reply = QMessageBox.question(self, 'Remove Folder', 
                                     f"Are you sure you want to remove this folder from the library?\n\n{path}\n\nThis will NOT delete files from disk, only from the database.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                     QMessageBox.StandardButton.No)
                                     
        if reply == QMessageBox.StandardButton.Yes:
            count = self.db.remove_media_in_folder(path)
            QMessageBox.information(self, "Folder Removed", f"Removed {count} files from the library.")
            
            # Refresh
            self.remove_folder_btn.setEnabled(False)
            # Explicitly clear view to give visual feedback
            self.current_media_data = []
            self.gallery_model.update_data([])
            self.load_media()

    def filter_media_by_path(self, path):
        # Normalize to match DB storage
        normalized_path = os.path.normpath(path)
        self.statusBar().showMessage(f"Showing media in: {normalized_path}")
        
        try:
            media = self.db.get_media_by_path(normalized_path)
            if not media:
                self.statusBar().showMessage(f"No media found in: {normalized_path}")
            
            if not media:
                self.statusBar().showMessage(f"No media found in: {normalized_path}")
            
            self.current_media_data = media
            self.apply_filters()
        except Exception as e:
            self.statusBar().showMessage(f"Error loading media: {e}")
            print(f"Error in filter_media_by_path: {e}")

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder:
            self.start_scan([folder])

    def scan_selected_directory(self):
        index = self.tree_view.currentIndex()
        if not index.isValid():
             return
             
        path = self.file_model.filePath(index)
        if path and os.path.isdir(path):
            self.start_scan([path])

    def start_scan(self, folders):
        if self.scanner and self.scanner.isRunning():
            QMessageBox.warning(self, "Scan in Progress", "Please wait for the current scan to finish.")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0) # Indeterminate
        self.statusBar().showMessage("Scanning...")
        
        self.scanner = MediaScanner(folders)
        self.scanner.progress_update.connect(self.update_status)
        self.scanner.finished_scan.connect(self.on_scan_finished)
        self.scanner.start()

    def update_status(self, message):
        self.statusBar().showMessage(message)

    def on_scan_finished(self):
        self.statusBar().showMessage("Scan Complete")
        self.progress_bar.setVisible(False)
        self.load_media()
        QMessageBox.information(self, "Done", "Scanning finished successfully.")

    def load_media(self):
        # Reloading logic for after scan usually
        self.start_async_loading()
        
    def update_image_folder_tree(self, folders):
        self.image_folder_model.clear()
        self.image_folder_model.setHorizontalHeaderLabels(["Media Folders"])
        
        root_item = self.image_folder_model.invisibleRootItem()
        
        # Map absolute path -> QStandardItem for quick lookup and parent resolution
        # Initialize with special handling for roots if needed
        # But our paths are absolute, so we can build them up.
        
        # We need a way to link "C:" to "C:\Users" correctly.
        # os.path.splitdrive might be useful.
        
        # Simpler approach: 
        # For each folder path:
        #   Split into chain of cumulative paths: "D:", "D:\Photos", "D:\Photos\2023"
        #   For each path in chain:
        #     If exists in tree/map (by absolute path key), get item.
        #     Else, create item, find parent item (path - last part), add row.
        
        # Key: Normalized absolute path string
        # Value: QStandardItem
        item_map = {}

        for folder_path in folders:
            # Normalize
            norm_path = os.path.normpath(folder_path)
            
            # Split into all parts (drive, folders...)
            # os.sep is '\\' on Windows
            parts = norm_path.split(os.sep)
            
            # Reconstruct cumulative paths to build tree node by node
            current_build = ""
            
            for i, part in enumerate(parts):
                if not part: continue
                
                # Handle Drive Root correctly
                if i == 0:
                    if part.endswith(':'):
                         current_build = part + os.sep # "D:\"
                    else:
                         current_build = part # Unix "/" or similar
                else:
                    current_build = os.path.join(current_build, part)
                
                # Check if we already have this node
                if current_build not in item_map:
                    new_item = QStandardItem(part)
                    new_item.setData(current_build, Qt.ItemDataRole.UserRole)
                    new_item.setEditable(False)
                    
                    # Find Parent
                    parent = root_item
                    
                    # Parent path is current_build without the last component
                    parent_path = os.path.dirname(current_build)

                    # If this is a drive root (e.g. "D:\"), parent is root_item (because dirname("D:\") is "D:\")
                    # os.path.dirname("D:\\") -> "D:\\"
                    
                    if parent_path != current_build and parent_path in item_map:
                        parent = item_map[parent_path]
                    
                    parent.appendRow(new_item)
                    item_map[current_build] = new_item
                    
                    # Expand effectively?
                    # parent.setExpanded(True) # Maybe?

    def get_short_path_name(self, long_name):
        import ctypes
        output_buf_size = 0
        
        # Prepend \\?\ to allow GetShortPathName to read the long path
        if not long_name.startswith('\\\\?\\') and len(long_name) > 255:
            long_name = '\\\\?\\' + long_name
            
        # Get buffer size
        output_buf_size = ctypes.windll.kernel32.GetShortPathNameW(long_name, None, 0)
        if output_buf_size == 0:
            return long_name # Failed, return original
            
        output_buf = ctypes.create_unicode_buffer(output_buf_size)
        ctypes.windll.kernel32.GetShortPathNameW(long_name, output_buf, output_buf_size)
        return output_buf.value

    def find_vlc_path(self):
        """Attempts to locate VLC executable on Windows."""
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\VideoLAN\VLC")
            val, _ = winreg.QueryValueEx(key, "InstallDir")
            return os.path.join(val, "vlc.exe")
        except OSError:
            pass
        
        # Check defaults
        defaults = [
            r"C:\Program Files\VideoLAN\VLC\vlc.exe",
            r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
        ]
        for p in defaults:
            if os.path.exists(p):
                return p
        return None

    def find_wmplayer_path(self):
        """Attempts to locate Windows Media Player executable."""
        # WMP is standard on Windows
        paths = [
            os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'Windows Media Player', 'wmplayer.exe'),
            os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'Windows Media Player', 'wmplayer.exe')
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return None

    def open_media(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv']:
            try:
                if sys.platform == 'win32':
                     abs_path = os.path.abspath(file_path)
                     
                     if len(abs_path) > 255:
                         print(f"Long path detected ({len(abs_path)} chars). Attempting WMP launch strategy.")
                         
                         wmp_ps = [
                            os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'Windows Media Player', 'wmplayer.exe'),
                            os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'Windows Media Player', 'wmplayer.exe')
                         ]
                         wmp_path = next((p for p in wmp_ps if os.path.exists(p)), None)
                         
                         if not wmp_path:
                             # Fallback to VLC if WMP not found
                             wmp_path = self.find_vlc_path()
                             print(f"WMP not found, using player at: {wmp_path}")

                         if wmp_path:
                             # Strategy 1: Short Path (8.3)
                             # WMP may not like \\?\ prefix, so 8.3 path is safest
                             short_path = self.get_short_path_name(abs_path)
                             print(f"Generated Short Path: {short_path}")
                             
                             launch_path = None
                             
                             if len(short_path) < 255 and short_path != abs_path:
                                 launch_path = short_path
                             else:
                                 # Strategy 2: Hard Link
                                 print("Short path failed or unavailable. Creating Hard Link.")
                                 drive = os.path.splitdrive(abs_path)[0]
                                 temp_link = os.path.join(drive, "\\", f"temp_play_{os.getpid()}.{ext.strip('.')}")
                                 
                                 # Cleanup old link
                                 if os.path.exists(temp_link):
                                     try: os.remove(temp_link)
                                     except: pass
                                 
                                 try:
                                     target = abs_path
                                     if not target.startswith('\\\\?\\'):
                                         target = '\\\\?\\' + target
                                     os.link(target, temp_link)
                                     launch_path = temp_link
                                     print(f"Hard Link created: {launch_path}")
                                 except OSError as e:
                                     print(f"Hard link creation failed: {e}")

                             if launch_path:
                                 print(f"Launching WMP with path: {launch_path}")
                                 subprocess.Popen([wmp_path, launch_path])
                                 return
                             else:
                                 print("All strategies failed for WMP. Trying raw force launch.")
                                 # Last Ditch: Force \\?\ path
                                 safe_path = abs_path
                                 if not safe_path.startswith('\\\\?\\'):
                                     safe_path = '\\\\?\\' + safe_path
                                 subprocess.Popen([wmp_path, safe_path])
                                 return

                         else:
                             raise Exception("No suitable player (WMP/VLC) found.")

                     else:
                         # Normal path
                         os.startfile(abs_path)

                elif sys.platform == 'darwin':
                    subprocess.call(['open', file_path])
                else:
                    subprocess.call(['xdg-open', file_path])
            except Exception as e:
                QMessageBox.warning(self, "Error Opening File", f"Could not open file: {e}\nPath: {file_path}")
        else:
            # Open image in enhanced internal viewer
            # Find index in current_media_data
            start_index = 0
            for i, data in enumerate(self.current_media_data):
                # data[1] is path
                if data[1] == file_path:
                    start_index = i
                    break
            
            # Use self.image_viewer to keep reference (prevent GC)
            # Close existing if open? Or allow multiple? Windows usually allows multiple or one instance.
            # Let's simple create new one for now.
            try:
                from src.ui.image_viewer import ImageViewer
                self.image_viewer_window = ImageViewer(self.current_media_data, start_index, self)
                self.image_viewer_window.show()
            except Exception as e:
                print(f"Error launching image viewer: {e}")
                # Fallback
                QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))

    def open_format_dialog(self):
        # Local import or use global if already imported
        try:
            from src.ui.format_dialog import FormatManagerDialog
            dialog = FormatManagerDialog(self)
            dialog.exec()
        except ImportError:
            QMessageBox.critical(self, "Error", "Could not load Format Manager.")

    def show_app_stats(self):
        try:
            from src.ui.stats_dialog import StatsDialog
            dialog = StatsDialog(self)
            dialog.exec()
        except ImportError as e:
            QMessageBox.critical(self, "Error", f"Could not load Stats Dialog: {e}")

    def open_thumbnails_folder(self):
        # Path to .thumbnails
        thumb_dir = os.path.join(os.getcwd(), '.thumbnails')
        if not os.path.exists(thumb_dir):
            os.makedirs(thumb_dir)
            
        try:
            url = QUrl.fromLocalFile(thumb_dir)
            QDesktopServices.openUrl(url)
        except Exception as e:
             QMessageBox.warning(self, "Error", f"Could not open thumbnails folder: {e}")

