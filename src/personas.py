"""
Personas — 人设配置加载
"""
import json
from pathlib import Path
import logging

logger = logging.getLogger("nous.personas")


class PersonaManager:
    """人设配置管理"""

    def __init__(self, personas_dir: str = "personas"):
        self.personas_dir = Path(personas_dir)
        self._personas: dict[str, dict] = {}
        self._load_all()

    def _load_all(self):
        """启动时加载所有人设"""
        for f in self.personas_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                pid = data.get("id", f.stem)
                self._personas[pid] = data
                logger.info(f"加载人设: {pid} ({data.get('name', '')})")
            except Exception as e:
                logger.error(f"人设加载失败 {f}: {e}")

    def get_all(self) -> list[dict]:
        """返回所有人设列表（不含 system_prompt）"""
        result = []
        for p in self._personas.values():
            result.append({
                "id": p["id"],
                "name": p.get("name", ""),
                "avatar": p.get("emoji", "🤖"),
                "description": p.get("tagline", ""),
                "greeting": p.get("greeting", "你好！"),
                "color": p.get("color", "#666"),
                "avatar_bg": p.get("avatar_bg", ""),
            })
        return result

    def get(self, persona_id: str) -> dict | None:
        """获取完整人设配置（含 system_prompt）"""
        return self._personas.get(persona_id)

    def get_name(self, persona_id: str) -> str:
        p = self._personas.get(persona_id)
        return p.get("name", persona_id) if p else persona_id
