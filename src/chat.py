"""
Chat — 核心对话模块（支持多对话）
"""
import json
import time
import logging
from .store import FileStore
from .llm import LLMClient
from .personas import PersonaManager
from .profile import ProfileManager
from .memory import MemoryManager
from .conversation import ConversationManager

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
        self.conv_mgr = ConversationManager(store)

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
        self, username: str, persona_id: str, conv_id: str = None,
        limit: int = 30, offset: int = 0
    ) -> dict:
        """获取对话历史"""
        if conv_id:
            return await self.conv_mgr.get_messages(
                username, persona_id, conv_id, limit, offset
            )
        # 兼容旧逻辑：获取最新对话
        conv = await self.conv_mgr.get_or_create_active(username, persona_id)
        result = await self.conv_mgr.get_messages(
            username, persona_id, conv["id"], limit, offset
        )
        result["conversation_id"] = conv["id"]
        return result

    async def clear_history(
        self, username: str, persona_id: str, conv_id: str = None
    ) -> None:
        """清空对话历史（不影响记忆）"""
        if conv_id:
            await self.conv_mgr.clear_messages(username, persona_id, conv_id)
        else:
            conv = await self.conv_mgr.get_or_create_active(username, persona_id)
            await self.conv_mgr.clear_messages(username, persona_id, conv["id"])

    def _count_rounds(self, messages: list) -> int:
        """计算对话轮数（每对 user+assistant 算一轮）"""
        return sum(1 for m in messages if m.get("role") == "user")

    async def stream_reply(
        self, username: str, persona_id: str, content: str,
        conv_id: str = None
    ):
        """
        流式回复生成器
        yields: (event_type, data_dict)
        """
        # 1. 加载人设（含用户自定义人设）
        persona = self.persona_mgr.get(persona_id, username)
        if not persona:
            yield ("error", {"message": f"人设不存在: {persona_id}"})
            return

        # 2. 确保有对话
        if not conv_id:
            conv = await self.conv_mgr.get_or_create_active(username, persona_id)
            conv_id = conv["id"]

        # 3. 加载用户数据
        profile = await self.profile_mgr.get_profile(username)
        memory = await self.memory_mgr.get_memory(username, persona_id)
        history = await self.conv_mgr.get_all_messages(
            username, persona_id, conv_id
        )

        # 4. 保存用户消息
        user_msg = {
            "role": "user",
            "content": content,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        history = await self.conv_mgr.append_message(
            username, persona_id, conv_id, user_msg
        )

        # 5. 构建 LLM 消息
        system_prompt = self._build_system_prompt(persona, profile, memory)
        llm_messages = [{"role": "system", "content": system_prompt}]

        # 最近20轮
        recent_history = history[-CONTEXT_WINDOW:]
        for m in recent_history:
            llm_messages.append({"role": m["role"], "content": m["content"]})

        # 6. 流式调用 LLM
        full_reply = ""
        async for token in self.llm.chat_stream(llm_messages):
            full_reply += token
            yield ("delta", {"content": token})

        # 7. 保存 AI 回复
        assistant_msg = {
            "role": "assistant",
            "content": full_reply,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        history = await self.conv_mgr.append_message(
            username, persona_id, conv_id, assistant_msg
        )

        # 8. 计算轮数，判断是否提取记忆
        round_count = self._count_rounds(history)
        memory_extracted = round_count > 0 and round_count % 5 == 0

        if memory_extracted:
            persona_name = self.persona_mgr.get_name(persona_id, username)
            await self.memory_mgr.maybe_extract(
                username, persona_id, persona_name, round_count
            )

        # 9. 发送完成事件
        yield ("done", {
            "round_count": round_count,
            "memory_extracted": memory_extracted,
            "conversation_id": conv_id,
        })
