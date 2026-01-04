import sys
import os
from src.core.database import MediaDatabase

def test_query():
    db = MediaDatabase()
    folders = db.get_image_folders()
    print(f"Found {len(folders)} image folders.")
    for f in folders:
        print(f"Folder: {f}")
        norm = os.path.normpath(f)
        try:
            media = db.get_media_by_path(norm)
            print(f"  -> Found {len(media)} media files.")
            if len(media) > 0:
                print(f"  -> Sample: {media[0]}")
        except Exception as e:
            print(f"  -> ERROR querying path '{norm}': {e}")
            
    print("\n--- Mixed Separator Test ---")
    # Try to find a folder that we know exists from above
    if folders:
        test_folder = folders[0]
        # Create a mixed version: replace some backslashes with forward slashes
        mixed = test_folder.replace('\\', '/')
        print(f"Testing mixed path: {mixed}")
        try:
             media = db.get_media_by_path(mixed)
             print(f"  -> Found {len(media)} items (Success if > 0)")
        except Exception as e:
             print(f"  -> Failed: {e}")

if __name__ == "__main__":
    test_query()
