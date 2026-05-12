# 神智 / Nous — 技术架构设计 (ARCHITECTURE)

> 版本: v0.1.0 | 最后更新: 2026-05-12  
> 状态: 草案，待评审  
> 前置文档: [SPEC.md](./SPEC.md)

---

## 1. 系统全景

```
┌──────────────────────────────────────────────────────────────────┐
│                        用户浏览器                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ 登录/注册 │  │ 人设选择  │  │  对话页   │  │ 档案/记忆面板   │ │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └────────┬─────────┘ │
│        └──────────────┴────────────┴─────────────────┘           │
│                            │ HTTP / SSE                          │
└────────────────────────────┼─────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                     FastAPI 后端 (Python)                          │
│                                                                    │
│  ┌────────────┐  ┌────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │  Auth 模块  │  │  Chat 模块  │  │ Memory 模块  │  │ Profile模块│ │
│  │ 注册/登录   │  │ 对话/流式   │  │ 提取/读写    │  │ 档案CRUD  │ │
│  │ JWT签发验证 │  │ 上下文管理  │  │ 每5轮触发    │  │           │ │
│  └──────┬─────┘  └──────┬─────┘  └──────┬──────┘  └─────┬──────┘ │
│         │               │               │               │        │
│         │               ▼               ▼               │        │
│         │        ┌─────────────────────────────┐        │        │
│         │        │     DashScope qwen-plus      │        │        │
│         │        │     (LLM 调用层)              │        │        │
│         │        └─────────────────────────────┘        │        │
│         │               │               │               │        │
│         ▼               ▼               ▼               ▼        │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │                   文件存储层 (JSON)                           │ │
│  │  data/users.json    data/users/{name}/messages/              │ │
│  │                     data/users/{name}/memories/              │ │
│  │                     data/users/{name}/profile.json           │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. 模块设计

### 2.1 Auth 模块

**职责**：用户注册、登录、Token 签发与验证

```python
# 核心组件
class AuthManager:
    """管理用户认证"""
    
    def register(username, password) -> token
        # 1. 校验昵称唯一性和格式（2-20字符）
        # 2. bcrypt 哈希密码
        # 3. 写入 users.json
        # 4. 创建用户目录 data/users/{username}/
        # 5. 签发 JWT 返回
    
    def login(username, password) -> token
        # 1. 查找用户
        # 2. bcrypt 验证密码
        # 3. 签发 JWT 返回
    
    def verify_token(token) -> username
        # 1. 解码 JWT
        # 2. 检查过期
        # 3. 返回 username
```

**JWT Payload**：
```json
{
  "sub": "xiaoming",
  "iat": 1715500000,
  "exp": 1716104800
}
```

**安全中间件**：
```python
async def auth_required(request):
    """FastAPI 依赖注入，从 Header 提取并验证 token"""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    username = auth_manager.verify_token(token)
    return username
```

---

### 2.2 Chat 模块

**职责**：管理对话流程，调用 LLM，流式输出

```
用户发消息
    │
    ▼
验证 Token → 获取 username
    │
    ▼
加载数据（并行）
├── 人设配置 (persona.json)
├── 用户档案 (profile.json)
├── 人设记忆 (memories/{persona}.json)
└── 对话历史 (messages/{persona}.json，最近20轮)
    │
    ▼
构建 LLM Messages
├── system: 人设设定 + 用户档案 + 人设记忆
├── history: 最近20轮
└── user: 当前输入
    │
    ▼
调用 DashScope (stream=True)
    │
    ▼
SSE 逐字推送给前端
    │
    ▼
回复完成后
├── 保存消息到历史
├── 检查是否第 5/10/15... 轮 → 触发记忆提取（异步）
└── 返回完成信号
```

**上下文构建详细规则**：

```python
def build_messages(persona, profile, memory, history, user_input):
    system = persona["system_prompt"]
    
    # 注入用户档案
    if profile:
        system += "\n\n【用户档案】\n"
        system += f"昵称：{profile.get('nickname', '未知')}\n"
        if profile.get('age'): system += f"年龄：{profile['age']}\n"
        if profile.get('occupation'): system += f"职业：{profile['occupation']}\n"
        if profile.get('interests'): system += f"兴趣：{', '.join(profile['interests'])}\n"
        if profile.get('bio'): system += f"其他：{profile['bio']}\n"
    
    # 注入人设记忆
    if memory:
        system += "\n\n【你对这位用户的记忆】\n"
        for key, value in memory.items():
            if key != 'updated_at':
                system += f"- {key}：{value}\n"
        system += "\n请自然地运用这些记忆，不要生硬地复述。"
    
    messages = [{"role": "system", "content": system}]
    
    # 最近20轮历史
    recent = history[-40:]  # 20轮 = 40条消息（user+assistant各一条）
    messages.extend(recent)
    
    messages.append({"role": "user", "content": user_input})
    return messages
```

**消息轮数计算**：

```python
def get_round_count(username, persona_id):
    """计算当前是第几轮对话，用于判断是否触发记忆提取"""
    messages = load_messages(username, persona_id)
    # 每一对 user+assistant 算一轮
    user_count = sum(1 for m in messages if m["role"] == "user")
    return user_count
```

---

### 2.3 Memory 模块

**职责**：记忆提取、存储、读写、用户编辑

#### 记忆提取流程

```
每5轮触发
    │
    ▼
收集最近5轮对话内容
    │
    ▼
加载现有记忆
    │
    ▼
调用 LLM 提取
├── prompt: 提取指令（见 SPEC.md 4.2节）
├── input: 现有记忆 + 最近5轮对话
└── output: {add: {}, update: {}, remove: []}
    │
    ▼
合并记忆
├── add → 直接写入
├── update → 覆盖旧值
├── remove → 删除 key
└── 更新 updated_at 时间戳
    │
    ▼
写入文件
```

**异步提取**（不阻塞用户对话）：

```python
async def maybe_extract_memory(username, persona_id, round_count):
    """检查是否需要提取记忆，异步执行"""
    if round_count % 5 != 0 or round_count == 0:
        return
    
    # 异步任务，不阻塞当前请求
    asyncio.create_task(
        extract_memory(username, persona_id)
    )

async def extract_memory(username, persona_id):
    """调用 LLM 提取记忆"""
    try:
        messages = load_messages(username, persona_id)
        recent = messages[-10:]  # 最近5轮 = 10条消息
        existing = load_memory(username, persona_id)
        
        # 调用 LLM
        result = await call_llm_extract(existing, recent, persona_id)
        
        # 合并
        merge_memory(username, persona_id, existing, result)
    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")
        # 提取失败不影响用户体验，静默处理
```

#### 记忆用户编辑

用户可以：
- **查看**所有记忆条目（key-value 列表）
- **修改**某条记忆的值
- **删除**某条记忆
- **清空**某个人设的全部记忆（二次确认）

---

### 2.4 Profile 模块

**职责**：用户档案的 CRUD

```python
class ProfileManager:
    
    def get_profile(username) -> dict
        # 读取 data/users/{username}/profile.json
        # 不存在则返回空档案模板
    
    def update_profile(username, data) -> dict
        # 合并更新（不是覆盖，只更新传入的字段）
        # 校验字段格式
        # 写入文件
```

---

## 3. 文件存储层

### 3.1 并发安全

```python
class FileStore:
    """带锁的文件存储"""
    
    _locks: dict[str, asyncio.Lock] = {}
    
    def _get_lock(self, path: str) -> asyncio.Lock:
        """每个文件路径一把锁"""
        if path not in self._locks:
            self._locks[path] = asyncio.Lock()
        return self._locks[path]
    
    async def read_json(self, path) -> dict | list:
        """读取 JSON 文件"""
        async with self._get_lock(path):
            if not path.exists():
                return {} if path.suffix == '.json' else []
            return json.loads(path.read_text())
    
    async def write_json(self, path, data):
        """写入 JSON 文件"""
        async with self._get_lock(path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
```

### 3.2 消息归档

当单个对话文件超过 200 条消息时：
1. 将前 100 条移入归档文件 `messages/{persona}_archive_{timestamp}.json`
2. 保留最近 100 条在主文件中
3. 归档文件只读，不参与上下文构建（记忆已覆盖关键信息）

---

## 4. LLM 调用层

### 4.1 统一封装

```python
class LLMClient:
    """统一的 LLM 调用封装"""
    
    def __init__(self):
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        self.model = "qwen-plus"
    
    async def chat_stream(self, messages) -> AsyncGenerator[str, None]:
        """流式对话，yield 每个 token"""
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions",
                json={"model": self.model, "messages": messages, "stream": True},
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        chunk = json.loads(line[6:])
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
    
    async def chat(self, messages) -> str:
        """非流式对话（用于记忆提取等内部调用）"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={"model": self.model, "messages": messages},
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            return response.json()["choices"][0]["message"]["content"]
```

### 4.2 两种调用场景

| 场景 | 方法 | 说明 |
|---|---|---|
| 对话回复 | `chat_stream` | 流式 SSE，面向用户 |
| 记忆提取 | `chat`（非流式） | 后台异步，返回完整 JSON |

---

## 5. 前端架构

### 5.1 SPA 路由

```
index.html (入口)
    │
    ├── #/login       → 登录/注册页
    ├── #/             → 人设选择页（需登录）
    ├── #/chat/{id}   → 对话页（需登录）
    └── #/profile     → 个人设置页（需登录）
```

使用 hash 路由（`#/path`），无需后端路由配合，纯静态文件即可。

### 5.2 状态管理

```javascript
const AppState = {
    token: localStorage.getItem('nous_token'),
    username: null,       // 从 token 解码
    currentPersona: null, // 当前选中的人设
    messages: [],         // 当前对话消息
    profile: {},          // 用户档案
};
```

### 5.3 认证流程（前端）

```
页面加载
    │
    ▼
检查 localStorage 有无 token
    │
    ├── 无 → 跳转 #/login
    │
    └── 有 → 解码检查过期
              │
              ├── 过期 → 清除，跳转 #/login
              └── 有效 → 进入应用
```

### 5.4 对话页布局

```
┌─────────────────────────────────────┐
│  ← 返回    铁哥(健身教练)    ⚙️记忆  │  顶栏
├─────────────────────────────────────┤
│                                     │
│  🤖 铁哥：兄弟今天练什么？           │
│                          我想练胸 👤 │
│  🤖 铁哥：好！先来3组卧推...         │
│                                     │
│                                     │  消息区
│                                     │
├─────────────────────────────────────┤
│  [输入消息...]              [发送]   │  输入栏
└─────────────────────────────────────┘
```

**记忆面板**（点击 ⚙️记忆 展开侧边栏）：
```
┌──────────────────────┐
│  铁哥的记忆           │
│                      │
│  体重：75kg     [✏️❌] │
│  膝伤：左膝     [✏️❌] │
│  频率：周3次    [✏️❌] │
│                      │
│  [清空所有记忆]       │
└──────────────────────┘
```

---

## 6. 错误处理

### 6.1 策略

| 场景 | 处理方式 |
|---|---|
| LLM 调用失败 | 返回友好提示"抱歉，我走神了，请再说一遍" |
| 记忆提取失败 | 静默忽略，不影响用户体验，记日志 |
| Token 过期 | 前端自动跳转登录页 |
| 文件写入失败 | 返回 500，记日志 |
| 并发写冲突 | asyncio.Lock 串行化，不会发生 |

### 6.2 日志

```python
import logging

logger = logging.getLogger("nous")
# 记录：LLM 调用耗时、记忆提取结果、认证失败、文件操作异常
# 日志文件：nous/logs/nous.log
```

---

## 7. 部署

### 7.1 V1 部署方案

```bash
# 单机部署，uvicorn 直接运行
cd /home/agentuser/nous
uvicorn src.app:app --host 0.0.0.0 --port 8767 --workers 1
```

- **端口**：8767（避开 8765 旅行博客、8766 persona-chat Demo）
- **Workers**：1（文件锁在多 worker 下不生效，单 worker 足够）
- **进程管理**：后续可加 systemd 或 supervisor

### 7.2 环境变量

```bash
DASHSCOPE_API_KEY=xxx        # LLM API Key
NOUS_JWT_SECRET=xxx          # JWT 签名密钥
NOUS_DATA_DIR=./data         # 数据目录（默认）
NOUS_LOG_LEVEL=INFO          # 日志级别
```

---

## 8. 从 persona-chat 迁移

### 需要复用的：
- 人设配置文件（5个 persona JSON）
- SSE 流式推送逻辑
- DashScope 调用封装
- 前端对话 UI 基础样式

### 需要重写的：
- 用户认证（全新）
- 路由结构（多页面）
- 记忆系统（自动提取替代 Hermes 巡检）
- 文件存储层（加锁、按用户隔离）
- 前端（多页面 SPA、登录流程、记忆面板）

### 不迁移的：
- Hermes 巡检相关代码（V1 不含深度层）
- demo_user 随机 ID 逻辑
- 旧的无认证 API

---

## 9. 模块依赖关系

```
Auth 模块 ──────────────────────────┐
    │                               │
    │ 依赖 Auth 的 Token 验证         │
    ▼                               │
Profile 模块                        │
    │                               │
    │ Profile 数据注入对话            │
    ▼                               ▼
Chat 模块 ──────────────────► Memory 模块
    │         每5轮触发提取          ▲
    │                               │
    └───────── 对话数据 ─────────────┘
    
底层支撑：
FileStore (并发安全文件读写)
LLMClient (统一 LLM 调用)
```

**开发顺序建议**（下游依赖上游，先开发底层）：

```
第1步：FileStore + LLMClient（底层）
第2步：Auth 模块（用户能注册登录）
第3步：Profile 模块（用户能填档案）
第4步：Chat 模块（核心对话，注入档案）
第5步：Memory 模块（每5轮提取）
第6步：前端整合
```
