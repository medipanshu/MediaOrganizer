import sys
import unittest
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from src.ui.image_viewer import ImageViewer

# Ensure QApplication exists
app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

class TestImageViewer(unittest.TestCase):
    def setUp(self):
        # Create dummy media list
        # (id, path, filename, extension, type)
        self.media_list = [
            (1, "test1.jpg", "test1", ".jpg", "image"),
            (2, "test2.jpg", "test2", ".jpg", "image"),
            (3, "test3.jpg", "test3", ".jpg", "image")
        ]
        # fake files existence for logic check (will fail to load pixmap but logic should run)
        # We can mock os.path.exists if needed, but let's see if the logic holds without crasching
        
        self.viewer = ImageViewer(self.media_list, 1) # Start at index 1 (test2)

    def test_initial_state(self):
        self.assertEqual(self.viewer.current_index, 1)
        # Check title roughly (might be "Failed to load..." if file missing, but window exists)
        self.assertTrue(self.viewer.isVisible() == False)

    def test_navigation_next(self):
        self.viewer.next_image()
        self.assertEqual(self.viewer.current_index, 2)
        
    def test_navigation_prev(self):
        self.viewer.prev_image() # Back to 0
        self.assertEqual(self.viewer.current_index, 0)
        
    def test_zoom_logic(self):
        # Initial scale is 1.0 (or fit)
        # Just check that calling it doesn't crash
        self.viewer.zoom_in()
        self.viewer.zoom_out()
        self.viewer.fit_to_window()
        self.viewer.reset_zoom()
        
    def test_rotation(self):
        self.viewer.rotate(90)
        # We can check transform if we want detailed verify, but "no crash" is good first step
        
if __name__ == '__main__':
    unittest.main()
