"""
Profile — 用户档案管理
"""
import logging
from .store import FileStore

logger = logging.getLogger("nous.profile")

ALLOWED_GENDERS = {"男", "女", "其他", "不愿透露"}


class ProfileManager:
    """用户档案 CRUD"""

    def __init__(self, store: FileStore):
        self.store = store

    async def get_profile(self, username: str) -> dict:
        path = self.store.profile_path(username)
        return await self.store.read_json(path, {})

    async def update_profile(self, username: str, data: dict) -> dict:
        """合并更新档案（只更新传入的字段），返回完整档案"""
        path = self.store.profile_path(username)
        profile = await self.store.read_json(path, {})

        # 字段校验与合并
        if "age" in data:
            age = data["age"]
            if age is not None and (not isinstance(age, int) or age < 1 or age > 150):
                raise ValueError("年龄需要在 1-150 之间")
            profile["age"] = age

        if "gender" in data:
            gender = data["gender"]
            if gender and gender not in ALLOWED_GENDERS:
                raise ValueError(f"性别可选：{', '.join(ALLOWED_GENDERS)}")
            profile["gender"] = gender

        if "occupation" in data:
            occ = data["occupation"] or ""
            if len(occ) > 50:
                raise ValueError("职业最长 50 个字符")
            profile["occupation"] = occ

        if "interests" in data:
            interests = data["interests"] or []
            if not isinstance(interests, list) or len(interests) > 20:
                raise ValueError("兴趣最多 20 个标签")
            for tag in interests:
                if len(tag) > 20:
                    raise ValueError(f"单个兴趣标签最长 20 字符：{tag}")
            profile["interests"] = interests

        if "bio" in data:
            bio = data["bio"] or ""
            if len(bio) > 500:
                raise ValueError("个人简介最长 500 字符")
            profile["bio"] = bio

        await self.store.write_json(path, profile)
        logger.info(f"档案更新: {username}")
        return profile
