"""
Memory — 记忆提取、存储、CRUD
"""
import json
import time
import asyncio
import logging
from .store import FileStore
from .llm import LLMClient

logger = logging.getLogger("nous.memory")

EXTRACT_PROMPT = """你是一个信息提取助手。根据以下对话内容，提取用户透露的关键个人信息。

当前人设：{persona_name}

已有记忆：
{existing_memory}

最近对话：
{recent_messages}

要求：
1. 只提取用户明确透露的事实性信息（如体重、宠物品种、训练频率等）
2. 与当前人设（{persona_name}）相关的信息优先
3. 如有冲突，以新信息为准（用户可能更新了情况）
4. 不要提取观点、情绪或闲聊内容
5. 用简短的中文 key-value 表示
6. 严格返回 JSON 格式：
{{
  "add": {{"key": "value"}},
  "update": {{"key": "new_value"}},
  "remove": ["key1"]
}}
7. 如果没有值得记住的新信息，返回：{{"add": {{}}, "update": {{}}, "remove": []}}

只返回 JSON，不要其他文字。"""


class MemoryManager:
    """记忆管理"""

    def __init__(self, store: FileStore, llm: LLMClient):
        self.store = store
        self.llm = llm

    async def get_memory(self, username: str, persona_id: str) -> dict:
        """获取记忆"""
        path = self.store.memory_path(username, persona_id)
        data = await self.store.read_json(path, {})
        return data

    async def update_memory_key(
        self, username: str, persona_id: str, key: str, value: str
    ) -> dict:
        """修改单条记忆"""
        path = self.store.memory_path(username, persona_id)
        data = await self.store.read_json(path, {})
        data[key] = value
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        await self.store.write_json(path, data)
        return data

    async def delete_memory_key(
        self, username: str, persona_id: str, key: str
    ) -> bool:
        """删除单条记忆"""
        path = self.store.memory_path(username, persona_id)
        data = await self.store.read_json(path, {})
        if key in data:
            del data[key]
            data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            await self.store.write_json(path, data)
            return True
        return False

    async def clear_memory(self, username: str, persona_id: str) -> None:
        """清空某个人设的全部记忆"""
        path = self.store.memory_path(username, persona_id)
        await self.store.write_json(path, {})

    async def maybe_extract(
        self,
        username: str,
        persona_id: str,
        persona_name: str,
        round_count: int,
    ) -> None:
        """判断是否需要提取记忆，异步执行"""
        if round_count <= 0 or round_count % 5 != 0:
            return
        # 异步执行，不阻塞
        asyncio.create_task(
            self._do_extract(username, persona_id, persona_name)
        )

    async def _do_extract(
        self, username: str, persona_id: str, persona_name: str
    ) -> None:
        """实际的记忆提取逻辑"""
        try:
            # 加载最近对话（5轮=10条消息）
            msg_path = self.store.messages_path(username, persona_id)
            messages = await self.store.read_json(msg_path, [])
            recent = messages[-10:]
            if not recent:
                return

            # 格式化对话
            recent_text = "\n".join(
                f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content']}"
                for m in recent
            )

            # 加载已有记忆
            existing = await self.get_memory(username, persona_id)
            existing_clean = {
                k: v for k, v in existing.items() if k != "updated_at"
            }

            # 构建 prompt
            prompt = EXTRACT_PROMPT.format(
                persona_name=persona_name,
                existing_memory=json.dumps(existing_clean, ensure_ascii=False)
                if existing_clean
                else "（暂无）",
                recent_messages=recent_text,
            )

            # 调用 LLM
            result_text = await self.llm.chat(
                [{"role": "user", "content": prompt}]
            )

            # 解析 JSON
            result_text = result_text.strip()
            # 去掉可能的 markdown 代码块标记
            if result_text.startswith("```"):
                lines = result_text.split("\n")
                result_text = "\n".join(lines[1:-1])

            result = json.loads(result_text)

            # 合并记忆
            changed = False
            for key, value in result.get("add", {}).items():
                if key and value:
                    existing[key] = value
                    changed = True
            for key, value in result.get("update", {}).items():
                if key and value:
                    existing[key] = value
                    changed = True
            for key in result.get("remove", []):
                if key in existing:
                    del existing[key]
                    changed = True

            if changed:
                existing["updated_at"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                )
                mem_path = self.store.memory_path(username, persona_id)
                await self.store.write_json(mem_path, existing)
                logger.info(
                    f"记忆提取完成: {username}/{persona_id}, "
                    f"add={len(result.get('add', {}))}, "
                    f"update={len(result.get('update', {}))}, "
                    f"remove={len(result.get('remove', []))}"
                )
            else:
                logger.info(f"记忆提取无新增: {username}/{persona_id}")

        except json.JSONDecodeError as e:
            logger.error(f"记忆提取 JSON 解析失败: {e}, raw={result_text[:200]}")
        except Exception as e:
            logger.error(f"记忆提取异常: {e}")
