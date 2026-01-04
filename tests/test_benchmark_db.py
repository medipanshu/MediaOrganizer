import sys
import os
import time
import shutil

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.core.database import MediaDatabase

TEST_DB = "test_benchmark.db"
NUM_FILES = 1000

def create_dummy_data(n):
    data = []
    for i in range(n):
        # We need actual files for os.stat in the current implementation of add_media/batch_insert
        # But for benchmark logic we might want to mock, but current code reads file stats inside the method.
        # So we'll just mock the os.stat or create dummy files.
        # Creating dummy files is cleaner.
        path = f"dummy_test_{i}.jpg"
        with open(path, 'w') as f:
            f.write("test")
        data.append((os.path.abspath(path), 'image'))
    return data

def cleanup(data):
    for path, _ in data:
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def main():
    print(f"Preparing {NUM_FILES} dummy files...")
    data = create_dummy_data(NUM_FILES)
    
    db = MediaDatabase(TEST_DB)
    db.init_db()
    
    # Test Single Insert
    # Warning: Current add_media calls batch_insert with 1 item, so it still has overhead of connect/close.
    # We want to see how bad it is vs batch.
    
    start_time = time.time()
    for path, type_ in data[:NUM_FILES//2]:
        db.add_media(path, type_)
    duration_single = time.time() - start_time
    print(f"Inserted {NUM_FILES//2} files individually: {duration_single:.4f} seconds")

    # Test Batch Insert
    start_time = time.time()
    db.batch_insert_media(data[NUM_FILES//2:])
    duration_batch = time.time() - start_time
    print(f"Inserted {NUM_FILES//2} files in batch: {duration_batch:.4f} seconds")
    
    print("-" * 30)
    if duration_batch < duration_single:
         print(f"Batch is {duration_single/duration_batch:.2f}x faster")
    else:
         print("Batch is slower?!")

    cleanup(data)

if __name__ == "__main__":
    main()
