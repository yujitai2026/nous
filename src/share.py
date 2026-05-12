"""
Nous 神智 — 对话导出 & 分享
"""
import json
import uuid
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("nous.share")

SHARE_EXPIRE_DAYS = 7


class ShareManager:
    def __init__(self, store, chat_mgr, persona_mgr):
        self.store = store
        self.chat_mgr = chat_mgr
        self.persona_mgr = persona_mgr
        self.shares_dir = Path(store.base_dir) / "shares"
        self.shares_dir.mkdir(parents=True, exist_ok=True)

    def _get_persona_name(self, persona_id: str, username: str) -> str:
        """获取人设显示名"""
        persona = self.persona_mgr.get(persona_id, username)
        if persona:
            emoji = persona.get("emoji", "")
            name = persona.get("name", persona_id)
            return f"{emoji} {name}".strip()
        return persona_id

    async def export_markdown(self, username: str, persona_id: str, conversation_id: str = None) -> str:
        """导出对话为 Markdown 文本"""
        result = await self.chat_mgr.get_history(username, persona_id, conversation_id, limit=9999)
        messages = result.get("messages", []) if isinstance(result, dict) else result
        persona_name = self._get_persona_name(persona_id, username)

        lines = []
        lines.append(f"# 与{persona_name}的对话")
        lines.append(f"")
        lines.append(f"> 导出时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(f"> 用户：{username}")
        lines.append(f"")
        lines.append("---")
        lines.append("")

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            if ts:
                try:
                    t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    time_str = t.strftime("%m-%d %H:%M")
                except Exception:
                    time_str = ts[:16]
            else:
                time_str = ""

            if role == "user":
                lines.append(f"### 🧑 {username}  `{time_str}`")
            else:
                lines.append(f"### 🤖 {persona_name}  `{time_str}`")
            lines.append("")
            lines.append(content)
            lines.append("")

        return "\n".join(lines)

    async def create_share(self, username: str, persona_id: str, conversation_id: str = None) -> dict:
        """创建分享链接，返回 share_id"""
        result = await self.chat_mgr.get_history(username, persona_id, conversation_id, limit=9999)
        messages = result.get("messages", []) if isinstance(result, dict) else result
        if not messages:
            raise ValueError("对话为空，无法分享")

        share_id = uuid.uuid4().hex[:10]
        persona_name = self._get_persona_name(persona_id, username)
        expire_at = (datetime.now(timezone.utc) + timedelta(days=SHARE_EXPIRE_DAYS)).isoformat()

        share_data = {
            "id": share_id,
            "username": username,
            "persona_id": persona_id,
            "persona_name": persona_name,
            "conversation_id": conversation_id,
            "messages": messages,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expire_at": expire_at,
            "message_count": len(messages),
        }

        share_path = self.shares_dir / f"{share_id}.json"
        share_path.write_text(json.dumps(share_data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"创建分享: {share_id} by {username}, {len(messages)} 条消息")

        return {
            "share_id": share_id,
            "expire_at": expire_at,
            "message_count": len(messages),
        }

    def get_share(self, share_id: str) -> dict | None:
        """获取分享数据，检查过期"""
        share_path = self.shares_dir / f"{share_id}.json"
        if not share_path.exists():
            return None

        data = json.loads(share_path.read_text(encoding="utf-8"))

        # 检查过期
        expire_at = data.get("expire_at", "")
        if expire_at:
            try:
                exp = datetime.fromisoformat(expire_at)
                if datetime.now(timezone.utc) > exp:
                    share_path.unlink(missing_ok=True)
                    logger.info(f"分享已过期并删除: {share_id}")
                    return None
            except Exception:
                pass

        return data
