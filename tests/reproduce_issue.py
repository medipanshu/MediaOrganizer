import os
import sqlite3
from src.core.database import MediaDatabase

def test_remove_logic():
    print("Testing removal logic...")
    db_path = "test_debug.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    db = MediaDatabase(db_path)
    
    # Setup Data
    # Simulate Windows paths
    files = [
        (r"D:\Photos\Vacation\IMG_001.jpg", "image"),
        (r"D:\Photos\Vacation\IMG_002.jpg", "image"),
        (r"D:\Photos\Work\Design.png", "image"),
        (r"D:\Photos\Vacation.jpg", "image") # Should NOT be removed when removing 'Vacation' folder
    ]
    
    count = db.batch_insert_media(files)
    print(f"Inserted {count} files.")
    
    # Verify Insertion
    all_media = db.get_all_media()
    print(f"Total media in DB: {len(all_media)}")
    
    # Try removing 
    folder_to_remove = r"D:\Photos\Vacation"
    print(f"Removing folder: {folder_to_remove}")
    
    removed = db.remove_media_in_folder(folder_to_remove)
    print(f"Removed count: {removed}")
    
    # Verify Remaining
    remaining = db.get_all_media()
    print(f"Remaining media: {len(remaining)}")
    for r in remaining:
        print(f" - {r[1]}") # Path
        
    # Check expected
    expected_remaining = 2 # Work\Design.png and Vacation.jpg
    if len(remaining) == expected_remaining:
        print("SUCCESS: Logic appears correct.")
    else:
        print("FAILURE: Logic incorrect.")

    db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    test_remove_logic()
