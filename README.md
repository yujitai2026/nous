# 🧠 神智 Nous

> 多人格 AI 智能体平台 — 五个性格迥异的 AI 伙伴，越聊越懂你

## ✨ 特性

- 🎭 **5 个人设** — 小暖（育儿）、Code（技术）、毛毛（宠物）、铁哥（健身）、漫游（旅行）
- 💬 **流式对话** — SSE 实时打字效果，毫秒级响应
- 🧩 **智能记忆** — LLM 每 5 轮自动提取对话记忆，越聊越懂你
- 👤 **用户档案** — 自填年龄、职业、兴趣，所有人设共享上下文
- 🔐 **用户隔离** — 独立账号体系，数据互不可见
- 📱 **移动适配** — 响应式设计，手机平板通吃
- 🌙 **暗色主题** — 护眼深色 UI，渐变视觉

## 🏗 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python FastAPI + Uvicorn |
| LLM | DashScope qwen-plus（流式 SSE） |
| 存储 | 文件系统 JSON（带并发锁） |
| 认证 | bcrypt 密码哈希 + JWT Token |
| 前端 | 原生 HTML/CSS/JS 单页应用 |

## 🚀 快速开始

```bash
# 克隆项目
git clone https://github.com/yujitai2026/nous.git
cd nous

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 设置环境变量
export DASHSCOPE_API_KEY="your-api-key"
export JWT_SECRET="your-secret"

# 启动
uvicorn src.app:app --host 0.0.0.0 --port 8767
```

访问 `http://localhost:8767` 即可使用。

## 📁 项目结构

```
nous/
├── src/
│   ├── app.py          # FastAPI 主入口（13 个 API）
│   ├── store.py        # 文件存储层（带并发锁）
│   ├── llm.py          # DashScope LLM 封装
│   ├── auth.py         # 注册/登录/JWT
│   ├── profile.py      # 用户档案
│   ├── personas.py     # 人设配置加载
│   ├── memory.py       # 记忆提取与管理
│   └── chat.py         # 核心对话引擎
├── static/
│   └── index.html      # 前端 SPA
├── personas/           # 5 个人设 JSON 配置
├── docs/               # 设计文档
│   ├── SPEC.md         # 产品规格书
│   ├── ARCHITECTURE.md # 技术架构
│   ├── API.md          # API 接口文档
│   └── TASKS.md        # 开发任务拆分
├── requirements.txt
└── start.sh            # 启动脚本
```

## 📡 API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录 |
| GET | `/api/personas` | 人设列表 |
| POST | `/api/chat/stream` | 流式对话（SSE） |
| GET | `/api/chat/history/{pid}` | 对话历史 |
| GET/PUT | `/api/profile` | 用户档案 |
| GET/PUT/DELETE | `/api/memory/{pid}` | 记忆管理 |

## 📄 License

MIT
