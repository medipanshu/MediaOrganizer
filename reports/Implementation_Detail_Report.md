# Implementation & Working Report - Phase 1

This report details the actual implementation of the "Local AI Media Organizer" compared to the initial plan, and explains the internal working mechanism of the application.

## 1. Plan vs. Implementation Analysis

The development process strictly followed the **Phase 1 Implementation Plan**.

| Component | Planned | Implemented | Status |
| :--- | :--- | :--- | :--- |
| **Architecture** | MVC Separation (`core/`, `ui/`) | **Success**: Logic is isolated in `src/core`, UI in `src/ui`. | ✅ |
| **Database** | SQLite, `media_files` table | **Success**: `MediaDatabase` class manages a single table schema. | ✅ |
| **Scanner** | Background Thread, Recursive | **Success**: `MediaScanner` extends `QThread` and scans recursively. | ✅ |
| **GUI** | Grid View, Lazy Loading | **Success**: `GalleryView` uses `QAbstractListModel` with icon caching. | ✅ |
| **Video** | External Player Launch | **Success**: Uses `os.startfile` / `subprocess` for native playback. | ✅ |

## 2. Technical Implementation Details

### A. Core Logic (`src/core/`)
1.  **`database.py` (Persistence Layer)**
    -   **Class**: `MediaDatabase`
    -   **Function**: Manages the SQLite connection.
    -   **Schema**:
        ```sql
        CREATE TABLE media_files (
            id INTEGER PRIMARY KEY,
            file_path TEXT UNIQUE,
            filename TEXT,
            extension TEXT,
            file_type TEXT, ...
        )
        ```
    -   **Logic**: Uses `INSERT OR IGNORE` to prevent duplicate entries for the same file path.

2.  **`scanner.py` (Background Worker)**
    -   **Class**: `MediaScanner` (Inherits `QThread`)
    -   **Concurrency**: usage of `QThread` prevents the GUI from freezing during heavy I/O operations.
    -   **Signals**: Emits `progress_update` (text) and `finished_scan` (void) to communicate with the Main Window.

### B. User Interface (`src/ui/`)
1.  **`gallery.py` (Visualization)**
    -   **Model-View Pattern**: Uses `QListView` (View) backed by `GalleryModel` (Model).
    -   **Lazy Loading / Caching**:
        -   The model generates icons only when requested by the view (`data()` method).
        -   `QImageReader` is used to load scaled-down versions of images for performance.
        -   `icon_cache` dictionary stores generated thumbnails to prevent re-reading files on scroll.

2.  **`main_window.py` (Orchestrator)**
    -   Connects the "Add Folder" button to the `MediaScanner`.
    -   Listens for scanner signals to update the Progress Bar and Status Label.
    -   Reloads the gallery from the database upon scan completion.

## 3. How the Project Works (Workflow)

### Step 1: Initialization
-   `main.py` creates the `QApplication` and `MainWindow`.
-   `MainWindow` connects to `media.db` (auto-creating it if missing) and loads any existing records into the gallery.

### Step 2: Ingesting Media
1.  **User Action**: Clicks "Add Folder" and selects a directory.
2.  **Process**:
    -   The UI disables conflict checks and starts `MediaScanner.start()`.
    -   The Scanner iterates through the folder tree on a separate thread.
    -   Found files are inserted into SQLite via `MediaDatabase.add_media()`.
3.  **Feedback**: The status bar updates with the current folder being scanned.

### Step 3: Viewing & Interaction
1.  **Display**: Once scanning ends, `MainWindow` calls `load_media()`.
2.  **Rendering**: The `GalleryView` populates the grid. Thumbnails are generated on-the-fly as the user scrolls.
3.  **Interaction**:
    -   **Double-Click Image**: Opens a simple internal viewer dialog (`ImageViewerById`).
    -   **Double-Click Video**: The app detects video extensions and calls the OS to open the file in the default player (e.g., VLC).
