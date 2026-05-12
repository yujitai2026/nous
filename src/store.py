"""
FileStore — 带并发锁的 JSON 文件存储层
"""
import json
import asyncio
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger("nous.store")


class FileStore:
    """线程安全的 JSON 文件读写，每个文件路径独立加锁"""

    def __init__(self, base_dir: str = "data"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, path: str) -> asyncio.Lock:
        key = str(path)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _resolve(self, *parts) -> Path:
        """拼接 base_dir 下的路径"""
        return self.base_dir.joinpath(*parts)

    async def read_json(self, path: Path, default: Any = None) -> Any:
        """读取 JSON 文件，不存在则返回 default"""
        async with self._get_lock(str(path)):
            if not path.exists():
                return default if default is not None else {}
            try:
                text = path.read_text(encoding="utf-8")
                return json.loads(text)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"读取文件失败 {path}: {e}")
                return default if default is not None else {}

    async def write_json(self, path: Path, data: Any) -> None:
        """写入 JSON 文件，自动创建父目录"""
        async with self._get_lock(str(path)):
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                text = json.dumps(data, ensure_ascii=False, indent=2)
                path.write_text(text, encoding="utf-8")
            except IOError as e:
                logger.error(f"写入文件失败 {path}: {e}")
                raise

    async def append_json_list(self, path: Path, item: dict) -> int:
        """向 JSON 数组文件追加一条记录，返回总条数"""
        async with self._get_lock(str(path)):
            path.parent.mkdir(parents=True, exist_ok=True)
            data = []
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, IOError):
                    data = []
            data.append(item)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return len(data)

    async def delete_file(self, path: Path) -> bool:
        """删除文件"""
        async with self._get_lock(str(path)):
            if path.exists():
                path.unlink()
                return True
            return False

    # ─── 便捷方法 ───

    def user_dir(self, username: str) -> Path:
        return self._resolve("users", username)

    def profile_path(self, username: str) -> Path:
        return self.user_dir(username) / "profile.json"

    def messages_path(self, username: str, persona_id: str) -> Path:
        return self.user_dir(username) / "messages" / f"{persona_id}.json"

    def memory_path(self, username: str, persona_id: str) -> Path:
        return self.user_dir(username) / "memories" / f"{persona_id}.json"

    def users_db_path(self) -> Path:
        return self._resolve("users.json")
