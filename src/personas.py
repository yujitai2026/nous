"""
Personas — 人设配置加载 + 用户自定义人设 CRUD
"""
import json
import uuid
import time
from pathlib import Path
import logging

logger = logging.getLogger("nous.personas")


class PersonaManager:
    """人设配置管理（系统 + 用户自定义）"""

    def __init__(self, personas_dir: str = "personas", store=None):
        self.personas_dir = Path(personas_dir)
        self.store = store
        self._system_personas: dict[str, dict] = {}
        self._load_all()

    def _load_all(self):
        """启动时加载所有系统人设"""
        for f in self.personas_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                pid = data.get("id", f.stem)
                self._system_personas[pid] = data
                logger.info(f"加载人设: {pid} ({data.get('name', '')})")
            except Exception as e:
                logger.error(f"人设加载失败 {f}: {e}")

    def _format_persona(self, p: dict, is_custom: bool = False) -> dict:
        """统一格式化人设数据（用于列表展示）"""
        return {
            "id": p["id"],
            "name": p.get("name", ""),
            "avatar": p.get("emoji", "🤖"),
            "description": p.get("tagline", ""),
            "greeting": p.get("greeting", "你好！"),
            "color": p.get("color", "#666"),
            "avatar_bg": p.get("avatar_bg", ""),
            "is_custom": is_custom,
        }

    def _custom_path(self, username: str, persona_id: str) -> Path:
        """用户自定义人设文件路径"""
        return self.store._resolve("custom_personas", username, f"{persona_id}.json")

    def _custom_dir(self, username: str) -> Path:
        return self.store._resolve("custom_personas", username)

    async def _list_custom(self, username: str) -> list[dict]:
        """获取用户自定义人设列表"""
        if not self.store:
            return []
        custom_dir = self._custom_dir(username)
        if not custom_dir.exists():
            return []
        custom = []
        for f in custom_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                custom.append(data)
            except Exception as e:
                logger.error(f"自定义人设加载失败 {f}: {e}")
        return custom

    async def get_all(self, username: str = None) -> list[dict]:
        """返回所有人设列表（系统 + 用户自定义，不含 system_prompt）"""
        result = []
        for p in self._system_personas.values():
            result.append(self._format_persona(p, is_custom=False))
        if username:
            for p in await self._list_custom(username):
                result.append(self._format_persona(p, is_custom=True))
        return result

    def get(self, persona_id: str, username: str = None) -> dict | None:
        """获取完整人设配置（含 system_prompt）— 同步"""
        if persona_id in self._system_personas:
            return self._system_personas[persona_id]
        # Check user custom (sync file read)
        if username and self.store:
            path = self._custom_path(username, persona_id)
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data.get("id"):
                        return data
                except Exception:
                    pass
        return None

    def get_name(self, persona_id: str, username: str = None) -> str:
        p = self.get(persona_id, username)
        return p.get("name", persona_id) if p else persona_id

    # ──── 用户自定义人设 CRUD ────

    async def create_custom(self, username: str, data: dict) -> dict:
        """创建自定义人设"""
        pid = "custom_" + uuid.uuid4().hex[:8]
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        persona = {
            "id": pid,
            "name": data.get("name", "新人设"),
            "emoji": data.get("emoji", "🤖"),
            "tagline": data.get("tagline", ""),
            "color": data.get("color", "#7c5bf5"),
            "avatar_bg": data.get("avatar_bg", ""),
            "greeting": data.get("greeting", "你好！有什么想聊的？"),
            "system_prompt": data.get("system_prompt", "你是一个友好的AI助手，请用中文回复。"),
            "created_at": now,
            "updated_at": now,
        }
        path = self._custom_path(username, pid)
        await self.store.write_json(path, persona)
        logger.info(f"用户 {username} 创建自定义人设: {pid} ({persona['name']})")
        return persona

    async def update_custom(self, username: str, persona_id: str, data: dict) -> dict | None:
        """更新自定义人设"""
        path = self._custom_path(username, persona_id)
        existing = await self.store.read_json(path, default=None)
        if not isinstance(existing, dict) or not existing.get("id"):
            return None
        for key in ("name", "emoji", "tagline", "color", "avatar_bg", "greeting", "system_prompt"):
            if key in data:
                existing[key] = data[key]
        existing["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        await self.store.write_json(path, existing)
        logger.info(f"用户 {username} 更新自定义人设: {persona_id}")
        return existing

    async def delete_custom(self, username: str, persona_id: str) -> bool:
        """删除自定义人设"""
        path = self._custom_path(username, persona_id)
        if not path.exists():
            return False
        await self.store.delete_file(path)
        logger.info(f"用户 {username} 删除自定义人设: {persona_id}")
        return True
