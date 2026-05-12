"""
Nous 神智 — 主应用入口
"""
import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .store import FileStore
from .llm import LLMClient
from .auth import AuthManager
from .profile import ProfileManager
from .personas import PersonaManager
from .memory import MemoryManager
from .chat import ChatManager

# ─── 日志 ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/nous.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("nous")

# ─── 全局实例 ───
BASE_DIR = Path(__file__).resolve().parent.parent
store = FileStore(str(BASE_DIR / "data"))
llm = LLMClient()
auth_mgr = AuthManager(store)
profile_mgr = ProfileManager(store)
persona_mgr = PersonaManager(str(BASE_DIR / "personas"))
memory_mgr = MemoryManager(store, llm)
chat_mgr = ChatManager(store, llm, persona_mgr, profile_mgr, memory_mgr)


# ─── App ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    (BASE_DIR / "logs").mkdir(exist_ok=True)
    logger.info("🧠 Nous 神智 启动")
    yield
    logger.info("🧠 Nous 神智 关闭")


app = FastAPI(title="Nous 神智", version="0.2.0", lifespan=lifespan)


# ─── 认证依赖 ───
async def get_current_user(request: Request) -> str:
    """从 Authorization header 提取并验证 token"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"detail": "未提供认证信息", "code": "AUTH_REQUIRED"},
        )
    token = auth_header[7:]
    username = auth_mgr.verify_token(token)
    if not username:
        raise HTTPException(
            status_code=401,
            detail={"detail": "认证失败，请重新登录", "code": "AUTH_EXPIRED"},
        )
    return username


# ─── Request Models ───
class AuthRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    persona_id: str
    content: str
    conversation_id: str | None = None


class ConversationCreateRequest(BaseModel):
    title: str = ""


class ProfileUpdateRequest(BaseModel):
    age: int | None = None
    gender: str | None = None
    occupation: str | None = None
    interests: list[str] | None = None
    bio: str | None = None


class MemoryUpdateRequest(BaseModel):
    value: str


# ═══════════════════════════════════════════
#  1. 认证 API
# ═══════════════════════════════════════════

@app.post("/api/auth/register")
async def register(req: AuthRequest):
    try:
        result = await auth_mgr.register(req.username, req.password)
        return result
    except ValueError as e:
        args = e.args
        detail = args[0] if args else "注册失败"
        code = args[1] if len(args) > 1 else "REGISTER_ERROR"
        raise HTTPException(
            status_code=409 if code == "USERNAME_EXISTS" else 400,
            detail={"detail": detail, "code": code},
        )


@app.post("/api/auth/login")
async def login(req: AuthRequest):
    try:
        result = await auth_mgr.login(req.username, req.password)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail={"detail": str(e.args[0]), "code": "LOGIN_FAILED"},
        )


# ═══════════════════════════════════════════
#  2. 用户档案 API
# ═══════════════════════════════════════════

@app.get("/api/profile")
async def get_profile(username: str = Depends(get_current_user)):
    return await profile_mgr.get_profile(username)


@app.put("/api/profile")
async def update_profile(
    req: ProfileUpdateRequest, username: str = Depends(get_current_user)
):
    try:
        data = req.model_dump(exclude_none=True)
        profile = await profile_mgr.update_profile(username, data)
        return profile
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"detail": str(e)})


# ═══════════════════════════════════════════
#  3. 人设 API
# ═══════════════════════════════════════════

@app.get("/api/personas")
async def get_personas(username: str = Depends(get_current_user)):
    return persona_mgr.get_all()


# ═══════════════════════════════════════════
#  4. 对话 API
# ═══════════════════════════════════════════

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, username: str = Depends(get_current_user)):
    """流式对话（SSE），支持 conversation_id"""

    async def event_generator():
        async for event_type, data in chat_mgr.stream_reply(
            username, req.persona_id, req.content, req.conversation_id
        ):
            yield f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/chat/history/{persona_id}")
async def get_history(
    persona_id: str,
    conversation_id: str = Query(None),
    limit: int = 50,
    offset: int = 0,
    username: str = Depends(get_current_user),
):
    return await chat_mgr.get_history(
        username, persona_id, conversation_id, limit, offset
    )


@app.delete("/api/chat/history/{persona_id}")
async def clear_history(
    persona_id: str,
    conversation_id: str = Query(None),
    username: str = Depends(get_current_user),
):
    await chat_mgr.clear_history(username, persona_id, conversation_id)
    return {"message": "对话历史已清空", "memory_preserved": True}


# ═══════════════════════════════════════════
#  4.5 多对话管理 API
# ═══════════════════════════════════════════

@app.get("/api/conversations/{persona_id}")
async def list_conversations(
    persona_id: str, username: str = Depends(get_current_user)
):
    """列出某人设下的所有对话"""
    convs = await chat_mgr.conv_mgr.list_conversations(username, persona_id)
    return {"conversations": convs}


@app.post("/api/conversations/{persona_id}")
async def create_conversation(
    persona_id: str,
    req: ConversationCreateRequest,
    username: str = Depends(get_current_user),
):
    """创建新对话"""
    conv = await chat_mgr.conv_mgr.create_conversation(
        username, persona_id, req.title
    )
    return conv


@app.delete("/api/conversations/{persona_id}/{conversation_id}")
async def delete_conversation(
    persona_id: str,
    conversation_id: str,
    username: str = Depends(get_current_user),
):
    """删除对话"""
    deleted = await chat_mgr.conv_mgr.delete_conversation(
        username, persona_id, conversation_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail={"detail": "对话不存在"})
    return {"message": "对话已删除"}


# ═══════════════════════════════════════════
#  5. 记忆 API
# ═══════════════════════════════════════════

@app.get("/api/memory/{persona_id}")
async def get_memory(
    persona_id: str, username: str = Depends(get_current_user)
):
    memory = await memory_mgr.get_memory(username, persona_id)
    updated_at = memory.pop("updated_at", None)
    return {"memories": memory, "updated_at": updated_at}


@app.put("/api/memory/{persona_id}/{key}")
async def update_memory_key(
    persona_id: str,
    key: str,
    req: MemoryUpdateRequest,
    username: str = Depends(get_current_user),
):
    await memory_mgr.update_memory_key(username, persona_id, key, req.value)
    return {"message": "记忆已更新", "key": key, "value": req.value}


@app.delete("/api/memory/{persona_id}/{key}")
async def delete_memory_key(
    persona_id: str, key: str, username: str = Depends(get_current_user)
):
    deleted = await memory_mgr.delete_memory_key(username, persona_id, key)
    if not deleted:
        raise HTTPException(status_code=404, detail={"detail": "记忆条目不存在"})
    return {"message": "记忆已删除", "key": key}


@app.delete("/api/memory/{persona_id}")
async def clear_memory(
    persona_id: str, username: str = Depends(get_current_user)
):
    await memory_mgr.clear_memory(username, persona_id)
    return {"message": "所有记忆已清空", "persona_id": persona_id}


# ═══════════════════════════════════════════
#  6. 健康检查
# ═══════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.2.0", "name": "Nous 神智"}


# ═══════════════════════════════════════════
#  7. 静态文件
# ═══════════════════════════════════════════

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Nous 神智 API", "docs": "/docs"}
