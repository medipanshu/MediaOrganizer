import sqlite3
import os
from datetime import datetime

class MediaDatabase:
    def __init__(self, db_path="media.db"):
        self.db_path = db_path
        self.connection = None
        self.cursor = None
        self.init_db()

    def connect(self):
        """Establishes a connection to the database."""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.cursor = self.connection.cursor()
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")

    def init_db(self):
        """Initializes the database schema."""
        self.connect()
        if self.connection:
            try:
                self.cursor.execute("""
                    CREATE TABLE IF NOT EXISTS media_files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_path TEXT UNIQUE NOT NULL,
                        filename TEXT NOT NULL,
                        extension TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        date_modified TIMESTAMP,
                        file_size INTEGER
                    )
                """)
                self.connection.commit()
            except sqlite3.Error as e:
                print(f"Error creating table: {e}")
            finally:
                self.close()

    def add_media(self, file_path, file_type):
        """Adds a single media file to the database.
        
        Args:
            file_path (str): Absolute path to the file.
            file_type (str): 'image' or 'video'.
        
        Returns:
            bool: True if added, False otherwise.
        """
        return self.batch_insert_media([(file_path, file_type)]) > 0

    def batch_insert_media(self, media_list):
        """Adds multiple media files to the database in a single transaction.
        
        Args:
            media_list (list): List of tuples (file_path, file_type).
            
        Returns:
            int: Number of files successfully added.
        """
        self.connect()
        if not self.connection:
            return 0

        count = 0
        try:
            # Prepare data
            data_to_insert = []
            for file_path, file_type in media_list:
                try:
                    # STRICT Normalization to ensure consistency (Windows Backslashes)
                    norm_path = os.path.normpath(file_path)
                    
                    filename = os.path.basename(norm_path)
                    extension = os.path.splitext(filename)[1].lower()
                    stats = os.stat(norm_path)
                    date_modified = datetime.fromtimestamp(stats.st_mtime)
                    file_size = stats.st_size
                    data_to_insert.append((norm_path, filename, extension, file_type, date_modified, file_size))
                except OSError as e:
                    print(f"Error reading file stats for {file_path}: {e}")
                    continue

            self.cursor.executemany("""
                INSERT OR IGNORE INTO media_files 
                (file_path, filename, extension, file_type, date_modified, file_size)
                VALUES (?, ?, ?, ?, ?, ?)
            """, data_to_insert)
            
            self.connection.commit()
            count = self.cursor.rowcount 
            return count
        except sqlite3.Error as e:
            print(f"Error adding batch media: {e}")
            return 0
        finally:
            self.close()

    def get_all_media(self):
        """Retrieves all media files."""
        self.connect()
        if not self.connection:
            return []
        
        try:
            self.cursor.execute("SELECT * FROM media_files ORDER BY date_modified DESC")
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error fetching media: {e}")
            return []
        finally:
            self.close()

    def get_media_by_path(self, path):
        """Retrieves media files under a specific directory."""
        self.connect()
        if not self.connection:
            return []
        
        try:
            # Normalize path for DB query
            search_path = os.path.normpath(path)
            
            # Use REPLACE to normalize the DB column on the fly during comparison.
            # This ensures that if the DB has 'D:/foo/bar.jpg' (forward)
            # and we search for 'D:\foo\' (backward), it still matches.
            # We normalize everything to backslashes for the comparison if on Windows,
            # or essentially specific separator of the OS.
            
            # Since os.path.normpath depends on OS, we should probably stick to one standard for the SQL logic
            # OR we just rely on the fact that we are replacing / with \ which handles the common mismatch.
            
            # For robustness: replace all / with \ in the DB field, and match against our backslash-normalized search path.
            # Escape backslashes for python string in SQL: \\ -> \
            
            sql = "SELECT * FROM media_files WHERE REPLACE(file_path, '/', '\\') LIKE ? ORDER BY date_modified DESC"
            
            # Ensure search_path ends with separator if we want directory content, 
            # OR we just match prefix.
            # If search_path is "D:\Photos", we match "D:\Photos\Img1.jpg"
            # But we also match "D:\Photos_Backup\..." which is WRONG.
            # So we should append a separator if not present.
            if not search_path.endswith(os.sep):
                search_path += os.sep
                
            # But the stored paths include the filename.
            # so LIKE 'D:\Photos\%'
            
            self.cursor.execute(sql, (f"{search_path}%",))
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            print(f"Error fetching media by path: {e}")
            return []
        finally:
            self.close()

    def get_image_folders(self):
        """Retrieves a list of unique folders containing images."""
        self.connect()
        if not self.connection:
            return []
        
        try:
            # Fetch all media paths (images and videos)
            self.cursor.execute("SELECT file_path FROM media_files")
            results = self.cursor.fetchall()
            
            # Extract unique directories
            folders = set()
            for row in results:
                folders.add(os.path.dirname(row[0]))
            
            return sorted(list(folders))
        except sqlite3.Error as e:
            print(f"Error fetching image folders: {e}")
            return []
        finally:
            self.close()

    def remove_media_in_folder(self, folder_path):
        """Removes all media files in a specific folder from the database."""
        self.connect()
        if not self.connection:
            return 0
            
        try:
            # Normalize path
            folder_path = os.path.normpath(folder_path)
            
            # Ensure path ends with separator for correct prefix matching if needed, 
            # OR just rely on correct usage. 
            # We want to match "D:\Photos\Vacation\*"
            
            # Strategy: Use LIKE with normalized separator
            # Replace / with \ just in case
            search_pattern = folder_path.replace('/', '\\') + '\\%'
            
            # Also remove the folder itself if it was somehow added as a file (unlikely but safe)
            # Actually, we want to remove FILES inside this folder.
            
            self.cursor.execute("DELETE FROM media_files WHERE replace(file_path, '/', '\\') LIKE ?", (search_pattern,))
            deleted_count = self.cursor.rowcount
            self.connection.commit()
            return deleted_count
        except sqlite3.Error as e:
            print(f"Error removing media in folder: {e}")
            return 0
        finally:
            self.close()

    def media_exists(self, file_path):
        """Checks if a file already exists in the database."""
        self.connect()
        if not self.connection:
            return False
            
        try:
            self.cursor.execute("SELECT 1 FROM media_files WHERE file_path = ?", (file_path,))
            return self.cursor.fetchone() is not None
        except sqlite3.Error as e:
            print(f"Error checking media existence: {e}")
            return False
        finally:
            self.close()

    def close(self):
        """Closes the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.cursor = None
