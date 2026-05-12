"""
Chat — 核心对话模块
"""
import json
import time
import logging
from .store import FileStore
from .llm import LLMClient
from .personas import PersonaManager
from .profile import ProfileManager
from .memory import MemoryManager

logger = logging.getLogger("nous.chat")

# 上下文窗口：最近20轮 = 40条消息
CONTEXT_WINDOW = 40
# 消息归档阈值
ARCHIVE_THRESHOLD = 200


class ChatManager:
    """对话管理"""

    def __init__(
        self,
        store: FileStore,
        llm: LLMClient,
        persona_mgr: PersonaManager,
        profile_mgr: ProfileManager,
        memory_mgr: MemoryManager,
    ):
        self.store = store
        self.llm = llm
        self.persona_mgr = persona_mgr
        self.profile_mgr = profile_mgr
        self.memory_mgr = memory_mgr

    def _build_system_prompt(
        self, persona: dict, profile: dict, memory: dict
    ) -> str:
        """构建 system prompt：人设 + 档案 + 记忆"""
        system = persona.get("system_prompt", "你是一个AI助手。")

        # 注入用户档案
        profile_parts = []
        if profile.get("nickname"):
            profile_parts.append(f"昵称：{profile['nickname']}")
        if profile.get("age"):
            profile_parts.append(f"年龄：{profile['age']}")
        if profile.get("gender"):
            profile_parts.append(f"性别：{profile['gender']}")
        if profile.get("occupation"):
            profile_parts.append(f"职业：{profile['occupation']}")
        if profile.get("interests"):
            profile_parts.append(f"兴趣爱好：{', '.join(profile['interests'])}")
        if profile.get("bio"):
            profile_parts.append(f"其他信息：{profile['bio']}")

        if profile_parts:
            system += "\n\n【用户档案】\n" + "\n".join(profile_parts)

        # 注入人设记忆
        memory_clean = {k: v for k, v in memory.items() if k != "updated_at"}
        if memory_clean:
            system += "\n\n【你对这位用户的记忆】\n"
            for key, value in memory_clean.items():
                system += f"- {key}：{value}\n"
            system += "\n请自然地运用这些记忆，不要生硬地复述。"

        return system

    async def get_history(
        self, username: str, persona_id: str, limit: int = 30, offset: int = 0
    ) -> dict:
        """获取对话历史"""
        path = self.store.messages_path(username, persona_id)
        messages = await self.store.read_json(path, [])
        total = len(messages)
        # offset 从最新往前数
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

    async def clear_history(self, username: str, persona_id: str) -> None:
        """清空对话历史（不影响记忆）"""
        path = self.store.messages_path(username, persona_id)
        await self.store.write_json(path, [])

    def _count_rounds(self, messages: list) -> int:
        """计算对话轮数（每对 user+assistant 算一轮）"""
        return sum(1 for m in messages if m.get("role") == "user")

    async def stream_reply(self, username: str, persona_id: str, content: str):
        """
        流式回复生成器
        yields: (event_type, data_dict)
        """
        # 1. 加载人设
        persona = self.persona_mgr.get(persona_id)
        if not persona:
            yield ("error", {"message": f"人设不存在: {persona_id}"})
            return

        # 2. 加载用户数据（并行）
        profile = await self.profile_mgr.get_profile(username)
        memory = await self.memory_mgr.get_memory(username, persona_id)
        msg_path = self.store.messages_path(username, persona_id)
        history = await self.store.read_json(msg_path, [])

        # 3. 保存用户消息
        user_msg = {
            "role": "user",
            "content": content,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        history.append(user_msg)

        # 4. 构建 LLM 消息
        system_prompt = self._build_system_prompt(persona, profile, memory)
        llm_messages = [{"role": "system", "content": system_prompt}]

        # 最近20轮
        recent_history = history[-CONTEXT_WINDOW:]
        for m in recent_history:
            llm_messages.append({"role": m["role"], "content": m["content"]})

        # 5. 流式调用 LLM
        full_reply = ""
        async for token in self.llm.chat_stream(llm_messages):
            full_reply += token
            yield ("delta", {"content": token})

        # 6. 保存 AI 回复
        assistant_msg = {
            "role": "assistant",
            "content": full_reply,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        history.append(assistant_msg)
        await self.store.write_json(msg_path, history)

        # 7. 计算轮数，判断是否提取记忆
        round_count = self._count_rounds(history)
        memory_extracted = round_count > 0 and round_count % 5 == 0

        if memory_extracted:
            persona_name = self.persona_mgr.get_name(persona_id)
            await self.memory_mgr.maybe_extract(
                username, persona_id, persona_name, round_count
            )

        # 8. 发送完成事件
        yield ("done", {
            "round_count": round_count,
            "memory_extracted": memory_extracted,
        })

        # 9. 消息归档（超过200条时）
        if len(history) > ARCHIVE_THRESHOLD:
            await self._archive_old_messages(username, persona_id, history)

    async def _archive_old_messages(
        self, username: str, persona_id: str, history: list
    ) -> None:
        """归档旧消息，保留最近100条"""
        keep = 100
        archive = history[:-keep]
        remaining = history[-keep:]

        # 保存归档
        archive_path = (
            self.store.user_dir(username)
            / "messages"
            / f"{persona_id}_archive_{int(time.time())}.json"
        )
        await self.store.write_json(archive_path, archive)

        # 更新主文件
        msg_path = self.store.messages_path(username, persona_id)
        await self.store.write_json(msg_path, remaining)
        logger.info(
            f"消息归档: {username}/{persona_id}, "
            f"归档{len(archive)}条，保留{len(remaining)}条"
        )
