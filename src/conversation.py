"""
Conversation — 多对话管理模块
每个用户+人设下可以有多个独立对话
"""
import time
import uuid
import logging
from .store import FileStore

logger = logging.getLogger("nous.conversation")


class ConversationManager:
    """管理用户对话列表"""

    def __init__(self, store: FileStore):
        self.store = store

    def _index_path(self, username: str, persona_id: str):
        """对话索引文件路径"""
        return self.store.user_dir(username) / "conversations" / f"{persona_id}.json"

    def _messages_path(self, username: str, persona_id: str, conv_id: str):
        """单个对话消息文件路径"""
        return self.store.user_dir(username) / "messages" / f"{persona_id}_{conv_id}.json"

    async def _ensure_migrated(self, username: str, persona_id: str) -> list:
        """
        懒迁移：如果存在旧格式消息文件但无对话索引，自动迁移。
        返回对话列表。
        """
        index_path = self._index_path(username, persona_id)
        raw = await self.store.read_json(index_path, None)

        # read_json returns {} when file not found (default=None quirk)
        # We only accept a list as valid index data
        if isinstance(raw, list):
            return raw

        # 检查旧格式文件
        old_path = self.store.messages_path(username, persona_id)
        old_messages = await self.store.read_json(old_path, None)

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if old_messages and len(old_messages) > 0:
            # 迁移旧消息到 default 对话
            conv_id = "default"
            new_msg_path = self._messages_path(username, persona_id, conv_id)
            await self.store.write_json(new_msg_path, old_messages)

            # 从第一条消息生成标题
            first_user_msg = next(
                (m["content"] for m in old_messages if m.get("role") == "user"), ""
            )
            title = self._make_title(first_user_msg)
            msg_count = len(old_messages)

            conversations = [
                {
                    "id": conv_id,
                    "title": title,
                    "created_at": old_messages[0].get("timestamp", now),
                    "updated_at": old_messages[-1].get("timestamp", now),
                    "message_count": msg_count,
                }
            ]
            await self.store.write_json(index_path, conversations)

            # 删除旧文件
            await self.store.delete_file(old_path)
            logger.info(f"迁移旧对话: {username}/{persona_id}, {msg_count}条消息")
            return conversations

        # 全新用户，返回空列表
        return []

    def _make_title(self, first_message: str) -> str:
        """从第一条消息生成对话标题"""
        if not first_message:
            return "新对话"
        # 取前20个字符
        title = first_message.strip().replace("\n", " ")
        if len(title) > 20:
            title = title[:20] + "..."
        return title

    async def list_conversations(
        self, username: str, persona_id: str
    ) -> list:
        """列出某人设下的所有对话，按更新时间倒序"""
        conversations = await self._ensure_migrated(username, persona_id)
        # 按 updated_at 倒序
        conversations.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
        return conversations

    async def create_conversation(
        self, username: str, persona_id: str, title: str = ""
    ) -> dict:
        """创建新对话"""
        conversations = await self._ensure_migrated(username, persona_id)
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conv_id = uuid.uuid4().hex[:8]

        conv = {
            "id": conv_id,
            "title": title or "新对话",
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
        }
        conversations.append(conv)
        await self.store.write_json(
            self._index_path(username, persona_id), conversations
        )

        # 创建空消息文件
        await self.store.write_json(
            self._messages_path(username, persona_id, conv_id), []
        )
        return conv

    async def get_or_create_active(
        self, username: str, persona_id: str
    ) -> dict:
        """获取最新对话，没有则创建"""
        conversations = await self.list_conversations(username, persona_id)
        if conversations:
            return conversations[0]
        return await self.create_conversation(username, persona_id)

    async def delete_conversation(
        self, username: str, persona_id: str, conv_id: str
    ) -> bool:
        """删除对话"""
        conversations = await self._ensure_migrated(username, persona_id)
        original_len = len(conversations)
        conversations = [c for c in conversations if c["id"] != conv_id]
        if len(conversations) == original_len:
            return False

        await self.store.write_json(
            self._index_path(username, persona_id), conversations
        )
        # 删除消息文件
        msg_path = self._messages_path(username, persona_id, conv_id)
        await self.store.delete_file(msg_path)
        logger.info(f"删除对话: {username}/{persona_id}/{conv_id}")
        return True

    async def update_conversation(
        self, username: str, persona_id: str, conv_id: str, **kwargs
    ) -> dict | None:
        """更新对话元数据（标题、消息计数等）"""
        conversations = await self._ensure_migrated(username, persona_id)
        conv = next((c for c in conversations if c["id"] == conv_id), None)
        if not conv:
            return None

        for key, value in kwargs.items():
            if key in ("title", "updated_at", "message_count"):
                conv[key] = value

        await self.store.write_json(
            self._index_path(username, persona_id), conversations
        )
        return conv

    async def get_messages(
        self, username: str, persona_id: str, conv_id: str,
        limit: int = 50, offset: int = 0
    ) -> dict:
        """获取对话消息"""
        await self._ensure_migrated(username, persona_id)
        path = self._messages_path(username, persona_id, conv_id)
        messages = await self.store.read_json(path, [])
        total = len(messages)
        if offset > 0:
            end = max(total - offset, 0)
        else:
            end = total
        start = max(end - limit, 0)
        return {
            "messages": messages[start:end],
            "total": total,
            "has_more": start > 0,
        }

    async def append_message(
        self, username: str, persona_id: str, conv_id: str, message: dict
    ) -> list:
        """追加消息并更新索引"""
        path = self._messages_path(username, persona_id, conv_id)
        messages = await self.store.read_json(path, [])
        messages.append(message)
        await self.store.write_json(path, messages)

        # 更新对话索引
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        update_data = {"updated_at": now, "message_count": len(messages)}

        # 如果是第一条用户消息，自动更新标题
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if len(user_msgs) == 1 and message.get("role") == "user":
            update_data["title"] = self._make_title(message["content"])

        await self.update_conversation(
            username, persona_id, conv_id, **update_data
        )
        return messages

    async def clear_messages(
        self, username: str, persona_id: str, conv_id: str
    ):
        """清空对话消息（保留对话条目）"""
        path = self._messages_path(username, persona_id, conv_id)
        await self.store.write_json(path, [])
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        await self.update_conversation(
            username, persona_id, conv_id,
            updated_at=now, message_count=0
        )

    async def get_all_messages(
        self, username: str, persona_id: str, conv_id: str
    ) -> list:
        """获取全部消息（用于构建LLM上下文）"""
        path = self._messages_path(username, persona_id, conv_id)
        return await self.store.read_json(path, [])
