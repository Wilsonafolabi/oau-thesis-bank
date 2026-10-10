import os, hashlib, shutil
from pathlib import Path

class FileStore:
    def __init__(self, base_dir: str = "storage/documents"):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def validate_and_store(self, file_path: str, max_size_mb: int = 100) -> tuple[str, str]:
        # Explicit path traversal check
        if ".." in file_path:
            raise ValueError("Path traversal detected")
            
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        ext = path.suffix.lower()
        if ext not in ['.pdf', '.docx']:
            raise ValueError(f"Unsupported file type: {ext}")
        if path.stat().st_size > max_size_mb * 1024 * 1024:
            raise ValueError(f"File too large: {path.stat().st_size} bytes")
            
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        file_hash = hasher.hexdigest()
        
        dest_dir = self.base_dir / file_hash[:2] / file_hash[2:4]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{file_hash}{ext}"
        if not dest_path.exists():
            shutil.copy2(path, dest_path)
        return str(dest_path), file_hash