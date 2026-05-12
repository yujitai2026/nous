"""
Auth — 用户注册、登录、JWT Token 管理
"""
import os
import re
import time
import bcrypt
import jwt
import logging
from pathlib import Path
from .store import FileStore

logger = logging.getLogger("nous.auth")

JWT_SECRET = os.getenv("NOUS_JWT_SECRET", "nous-secret-change-me-in-prod")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = 7 * 24 * 3600  # 7天


class AuthManager:
    """用户认证管理"""

    def __init__(self, store: FileStore):
        self.store = store

    async def _load_users(self) -> dict:
        return await self.store.read_json(self.store.users_db_path(), {})

    async def _save_users(self, users: dict):
        await self.store.write_json(self.store.users_db_path(), users)

    def _hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def _verify_password(self, password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

    def _sign_token(self, username: str) -> str:
        payload = {
            "sub": username,
            "iat": int(time.time()),
            "exp": int(time.time()) + JWT_EXPIRE_SECONDS,
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    def verify_token(self, token: str) -> str | None:
        """验证 JWT，返回 username 或 None"""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload.get("sub")
        except jwt.ExpiredSignatureError:
            logger.info("Token 已过期")
            return None
        except jwt.InvalidTokenError as e:
            logger.info(f"Token 无效: {e}")
            return None

    @staticmethod
    def validate_username(username: str) -> str | None:
        """校验用户名，返回错误信息或 None"""
        if not username or len(username) < 2 or len(username) > 20:
            return "用户名需要 2-20 个字符"
        if not re.match(r"^[\w\u4e00-\u9fff]+$", username):
            return "用户名只支持中英文、数字和下划线"
        return None

    @staticmethod
    def validate_password(password: str) -> str | None:
        """校验密码，返回错误信息或 None"""
        if not password or len(password) < 6:
            return "密码至少 6 个字符"
        if len(password) > 50:
            return "密码最长 50 个字符"
        return None

    async def register(self, username: str, password: str) -> dict:
        """
        注册用户
        返回 {"token": ..., "username": ...} 或抛出 ValueError
        """
        # 校验
        if err := self.validate_username(username):
            raise ValueError(err, "USERNAME_INVALID")
        if err := self.validate_password(password):
            raise ValueError(err, "PASSWORD_TOO_SHORT")

        users = await self._load_users()
        if username in users:
            raise ValueError("用户名已被注册", "USERNAME_EXISTS")

        # 创建用户
        users[username] = {
            "password_hash": self._hash_password(password),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        await self._save_users(users)

        # 创建用户目录
        user_dir = self.store.user_dir(username)
        (user_dir / "messages").mkdir(parents=True, exist_ok=True)
        (user_dir / "memories").mkdir(parents=True, exist_ok=True)

        token = self._sign_token(username)
        logger.info(f"新用户注册: {username}")
        return {"token": token, "username": username}

    async def login(self, username: str, password: str) -> dict:
        """
        登录
        返回 {"token": ..., "username": ...} 或抛出 ValueError
        """
        users = await self._load_users()
        user = users.get(username)
        if not user or not self._verify_password(password, user["password_hash"]):
            raise ValueError("用户名或密码错误", "LOGIN_FAILED")

        token = self._sign_token(username)
        logger.info(f"用户登录: {username}")
        return {"token": token, "username": username}
