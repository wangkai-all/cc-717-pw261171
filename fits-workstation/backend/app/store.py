"""文件存储：上传文件与内置样例的登记。"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path


class FileStore:
    def __init__(self, upload_dir: str | Path, samples_dir: str | Path):
        self.upload_dir = Path(upload_dir)
        self.samples_dir = Path(samples_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self._files: dict[str, dict] = {}

    def register(self, path: str | Path, name: str) -> str:
        file_id = uuid.uuid4().hex[:12]
        self._files[file_id] = {"path": str(path), "name": name}
        return file_id

    def save_upload(self, filename: str, stream) -> str:
        safe_name = Path(filename).name or "uploaded.fits"
        dest = self.upload_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"
        with open(dest, "wb") as fh:
            shutil.copyfileobj(stream, fh)
        return self.register(dest, safe_name)

    def register_sample(self, sample_name: str) -> str:
        path = self.samples_dir / sample_name
        if not path.is_file():
            raise FileNotFoundError(sample_name)
        return self.register(path, sample_name)

    def list_samples(self) -> list[dict]:
        samples = []
        if self.samples_dir.is_dir():
            for p in sorted(self.samples_dir.glob("*.fits")):
                samples.append({"name": p.name, "size": p.stat().st_size})
        return samples

    def get(self, file_id: str) -> dict:
        if file_id not in self._files:
            raise KeyError(file_id)
        return self._files[file_id]
