"""
Nous 神智 — 主应用入口
"""
import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, JSONResponse, PlainTextResponse, HTMLResponse
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
from .share import ShareManager, SHARE_EXPIRE_DAYS

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
persona_mgr = PersonaManager(str(BASE_DIR / "personas"), store=store)
memory_mgr = MemoryManager(store, llm)
chat_mgr = ChatManager(store, llm, persona_mgr, profile_mgr, memory_mgr)
share_mgr = ShareManager(store, chat_mgr, persona_mgr)


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


class PersonaCreateRequest(BaseModel):
    name: str
    emoji: str = "🤖"
    tagline: str = ""
    color: str = "#7c5bf5"
    avatar_bg: str = ""
    greeting: str = "你好！有什么想聊的？"
    system_prompt: str = "你是一个友好的AI助手，请用中文回复。"


class PersonaUpdateRequest(BaseModel):
    name: str | None = None
    emoji: str | None = None
    tagline: str | None = None
    color: str | None = None
    avatar_bg: str | None = None
    greeting: str | None = None
    system_prompt: str | None = None


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
    return await persona_mgr.get_all(username)


@app.post("/api/personas/custom")
async def create_custom_persona(
    req: PersonaCreateRequest, username: str = Depends(get_current_user)
):
    """创建自定义人设"""
    persona = await persona_mgr.create_custom(username, req.model_dump())
    return persona


@app.put("/api/personas/custom/{persona_id}")
async def update_custom_persona(
    persona_id: str,
    req: PersonaUpdateRequest,
    username: str = Depends(get_current_user),
):
    """更新自定义人设"""
    data = req.model_dump(exclude_none=True)
    updated = await persona_mgr.update_custom(username, persona_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail={"detail": "人设不存在或无权修改"})
    return updated


@app.delete("/api/personas/custom/{persona_id}")
async def delete_custom_persona(
    persona_id: str, username: str = Depends(get_current_user)
):
    """删除自定义人设"""
    deleted = await persona_mgr.delete_custom(username, persona_id)
    if not deleted:
        raise HTTPException(status_code=404, detail={"detail": "人设不存在或无权删除"})
    return {"message": "人设已删除", "persona_id": persona_id}


@app.get("/api/personas/custom/{persona_id}")
async def get_custom_persona_detail(
    persona_id: str, username: str = Depends(get_current_user)
):
    """获取自定义人设详情（含 system_prompt，用于编辑）"""
    persona = persona_mgr.get(persona_id, username)
    if not persona or persona_id not in (persona.get("id", "")):
        raise HTTPException(status_code=404, detail={"detail": "人设不存在"})
    return persona


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
#  7. 导出 & 分享 API
# ═══════════════════════════════════════════

@app.get("/api/export/{persona_id}")
async def export_conversation(
    persona_id: str,
    conversation_id: str = Query(None),
    username: str = Depends(get_current_user),
):
    """导出对话为 Markdown"""
    md = await share_mgr.export_markdown(username, persona_id, conversation_id)
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="nous_{persona_id}.md"'
    })


@app.post("/api/share/{persona_id}")
async def create_share(
    persona_id: str,
    conversation_id: str = Query(None),
    username: str = Depends(get_current_user),
):
    """创建分享链接"""
    try:
        result = await share_mgr.create_share(username, persona_id, conversation_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"detail": str(e)})


@app.get("/s/{share_id}")
async def view_share(share_id: str):
    """查看分享页面（免登录）"""
    data = share_mgr.get_share(share_id)
    if not data:
        return HTMLResponse(SHARE_EXPIRED_HTML, status_code=404)
    return HTMLResponse(render_share_page(data))


# ═══════════════════════════════════════════
#  8. 静态文件
# ═══════════════════════════════════════════

SHARE_EXPIRED_HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>分享已过期</title>
<style>body{background:#0a0a1a;color:#e0e0e0;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;font-family:system-ui}
.box{text-align:center;padding:40px}.box h2{font-size:48px;margin:0}.box p{color:#888;margin-top:16px}</style>
</head><body><div class="box"><h2>⏳</h2><p>该分享链接已过期或不存在</p></div></body></html>"""


def render_share_page(data: dict) -> str:
    """渲染分享对话页面"""
    import html as html_mod
    persona_name = html_mod.escape(data.get("persona_name", "AI"))
    created = data.get("created_at", "")[:10]
    expire = data.get("expire_at", "")[:10]
    msg_count = data.get("message_count", 0)
    username = html_mod.escape(data.get("username", "用户"))

    messages_html = []
    for msg in data.get("messages", []):
        role = msg.get("role", "user")
        content = html_mod.escape(msg.get("content", ""))
        # 保留换行
        content = content.replace("\n", "<br>")
        ts = msg.get("timestamp", "")
        if ts:
            try:
                from datetime import datetime as dt
                t = dt.fromisoformat(ts.replace("Z", "+00:00"))
                time_str = t.strftime("%m-%d %H:%M")
            except Exception:
                time_str = ts[:16]
        else:
            time_str = ""

        if role == "user":
            cls = "msg-user"
            label = f'🧑 {username}'
        else:
            cls = "msg-bot"
            label = f'🤖 {persona_name}'

        messages_html.append(f'''<div class="msg {cls}">
<div class="msg-header"><span class="msg-name">{label}</span><span class="msg-time">{time_str}</span></div>
<div class="msg-body">{content}</div></div>''')

    msgs_joined = "\n".join(messages_html)

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>与{persona_name}的对话 — 神智 Nous</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a1a;color:#e0e0e0;font-family:system-ui,-apple-system,sans-serif;line-height:1.6}}
.container{{max-width:720px;margin:0 auto;padding:20px 16px;padding-top:env(safe-area-inset-top,20px)}}
.header{{text-align:center;padding:24px 0;border-bottom:1px solid #1e1e3a;margin-bottom:24px}}
.header h1{{font-size:20px;color:#c4b5fd;margin-bottom:8px}}
.header .meta{{font-size:13px;color:#666}}
.msg{{margin-bottom:16px;padding:14px 16px;border-radius:12px;border:1px solid #1e1e3a}}
.msg-user{{background:#111128}}
.msg-bot{{background:#0f1a2e}}
.msg-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}}
.msg-name{{font-weight:600;font-size:14px;color:#a78bfa}}
.msg-user .msg-name{{color:#60a5fa}}
.msg-time{{font-size:12px;color:#555}}
.msg-body{{font-size:15px;line-height:1.7;color:#d0d0d0}}
.footer{{text-align:center;padding:24px 0;color:#444;font-size:12px;border-top:1px solid #1e1e3a;margin-top:24px}}
.badge{{display:inline-block;background:#1e1e3a;padding:4px 12px;border-radius:20px;font-size:12px;color:#888;margin:0 4px}}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>🧠 与{persona_name}的对话</h1>
  <div class="meta">
    <span class="badge">📝 {msg_count} 条消息</span>
    <span class="badge">📅 {created}</span>
    <span class="badge">⏳ {expire} 过期</span>
  </div>
</div>
{msgs_joined}
<div class="footer">由 <b>神智 Nous</b> 生成 · 分享链接 {SHARE_EXPIRE_DAYS} 天后自动失效</div>
</div>
</body>
</html>'''

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"message": "Nous 神智 API", "docs": "/docs"}
