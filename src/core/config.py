import json
import os

CONFIG_FILE = os.path.join(os.getcwd(), 'config.json')

DEFAULT_IMAGE_EXTS = {
    '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif',
    '.svg', '.heic', '.ico', '.raw', '.cr2', '.nef', '.orf', '.sr2'
}

DEFAULT_VIDEO_EXTS = {
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', 
    '.mpg', '.mpeg', '.m4v', '.3gp', '.webm', '.ts', '.mts', '.m2ts'
}

class ConfigManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance.load_config()
        return cls._instance

    def load_config(self):
        self.config = {
            'image_extensions': list(DEFAULT_IMAGE_EXTS),
            'video_extensions': list(DEFAULT_VIDEO_EXTS)
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    saved_config = json.load(f)
                    # Update defaults with saved (merge or replace? Replace allows removal)
                    # But we want to ensure keys exist
                    if 'image_extensions' in saved_config:
                        self.config['image_extensions'] = saved_config['image_extensions']
                    if 'video_extensions' in saved_config:
                        self.config['video_extensions'] = saved_config['video_extensions']
            except (json.JSONDecodeError, OSError):
                pass # Fallback to defaults

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except OSError:
            pass # TODO: log error

    def get_image_extensions(self):
        return set(self.config['image_extensions'])

    def get_video_extensions(self):
        return set(self.config['video_extensions'])

    def add_extension(self, media_type, ext):
        ext = ext.lower()
        if not ext.startswith('.'):
            ext = '.' + ext
            
        key = f'{media_type}_extensions'
        if key in self.config:
            if ext not in self.config[key]:
                self.config[key].append(ext)
                self.save_config()
                return True
        return False

    def remove_extension(self, media_type, ext):
        ext = ext.lower()
        key = f'{media_type}_extensions'
        if key in self.config:
            if ext in self.config[key]:
                self.config[key].remove(ext)
                self.save_config()
                return True
        return False

    def get_last_scan_info(self):
        return self.config.get('last_scan', {
            'timestamp': 'Never',
            'status': 'N/A',
            'new_files_count': 0,
            'total_files_scanned': 0
        })

    def set_last_scan_info(self, info):
        self.config['last_scan'] = info
        self.save_config()
