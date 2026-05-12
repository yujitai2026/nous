# 神智 / Nous — API 接口文档 (API)

> 版本: v0.1.0 | 最后更新: 2026-05-12  
> 状态: 草案，待评审  
> 前置文档: [SPEC.md](./SPEC.md) | [ARCHITECTURE.md](./ARCHITECTURE.md)

---

## 概述

- **Base URL**：`http://81.70.241.116:8767`
- **协议**：HTTP/1.1
- **内容类型**：`application/json`（除 SSE 端点外）
- **认证方式**：Bearer Token（JWT）
- **字符编码**：UTF-8

### 认证

除 `POST /api/auth/register` 和 `POST /api/auth/login` 外，所有 API 都需要在请求头携带 JWT：

```
Authorization: Bearer <token>
```

Token 无效或过期时返回：
```json
{"detail": "认证失败，请重新登录", "code": "AUTH_EXPIRED"}
```

### 通用错误格式

```json
{
  "detail": "错误描述",
  "code": "ERROR_CODE"
}
```

---

## 1. 认证 (Auth)

### 1.1 注册

```
POST /api/auth/register
```

**请求体**：
```json
{
  "username": "xiaoming",
  "password": "mypassword123"
}
```

**校验规则**：
- `username`：2-20 字符，支持中英文、数字、下划线，不可重复
- `password`：6-50 字符

**成功响应** `200`：
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "username": "xiaoming"
}
```

**失败响应**：
| 状态码 | code | 场景 |
|---|---|---|
| 400 | `USERNAME_INVALID` | 昵称格式不合法 |
| 400 | `PASSWORD_TOO_SHORT` | 密码少于6位 |
| 409 | `USERNAME_EXISTS` | 昵称已被注册 |

---

### 1.2 登录

```
POST /api/auth/login
```

**请求体**：
```json
{
  "username": "xiaoming",
  "password": "mypassword123"
}
```

**成功响应** `200`：
```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "username": "xiaoming"
}
```

**失败响应**：
| 状态码 | code | 场景 |
|---|---|---|
| 401 | `LOGIN_FAILED` | 用户名或密码错误 |

---

## 2. 用户档案 (Profile)

### 2.1 获取档案

```
GET /api/profile
```

**响应** `200`：
```json
{
  "nickname": "小明",
  "age": 28,
  "gender": "男",
  "occupation": "程序员",
  "interests": ["健身", "养猫", "旅行"],
  "bio": "坐标北京，喜欢折腾新技术"
}
```

档案未填写时返回空对象 `{}`。

---

### 2.2 更新档案

```
PUT /api/profile
```

**请求体**（部分更新，只传需要修改的字段）：
```json
{
  "age": 29,
  "interests": ["健身", "养猫", "旅行", "摄影"]
}
```

**字段校验**：
| 字段 | 类型 | 校验规则 |
|---|---|---|
| `nickname` | string | 不可修改（即注册用户名） |
| `age` | number | 1-150 |
| `gender` | string | 男/女/其他/不愿透露 |
| `occupation` | string | 最长50字符 |
| `interests` | string[] | 最多20个标签，每个最长20字符 |
| `bio` | string | 最长500字符 |

**成功响应** `200`：返回更新后的完整档案。

---

## 3. 人设 (Personas)

### 3.1 获取人设列表

```
GET /api/personas
```

**响应** `200`：
```json
[
  {
    "id": "tech_buddy",
    "name": "Code（码上聊）",
    "avatar": "💻",
    "description": "技术极客，专业、简洁、偶尔幽默",
    "greeting": "Hey！有什么技术问题来聊聊？"
  },
  {
    "id": "fitness_coach",
    "name": "铁哥",
    "avatar": "💪",
    "description": "健身教练，热血、鼓励、直接",
    "greeting": "兄弟！今天打算练什么？"
  },
  {
    "id": "pet_expert",
    "name": "毛毛",
    "avatar": "🐾",
    "description": "宠物专家，温柔、耐心、专业",
    "greeting": "你好呀～你家毛孩子还好吗？"
  },
  {
    "id": "parenting",
    "name": "小暖",
    "avatar": "🌸",
    "description": "育儿顾问，温暖、共情、不说教",
    "greeting": "嗨，当父母不容易，随时可以聊聊～"
  },
  {
    "id": "traveler",
    "name": "漫游",
    "avatar": "🌍",
    "description": "旅行达人，随性、见多识广、爱分享",
    "greeting": "嘿！最近有什么旅行计划吗？"
  }
]
```

---

## 4. 对话 (Chat)

### 4.1 发送消息（流式）

```
POST /api/chat/stream
```

**请求体**：
```json
{
  "persona_id": "fitness_coach",
  "content": "我想开始减脂，有什么建议？"
}
```

**响应**：`text/event-stream`（SSE）

```
data: {"type": "token", "content": "兄"}

data: {"type": "token", "content": "弟"}

data: {"type": "token", "content": "！"}

data: {"type": "token", "content": "减脂"}

...

data: {"type": "done", "round_count": 5, "memory_extracted": true}

```

**SSE 事件类型**：
| type | 说明 | 内容 |
|---|---|---|
| `token` | 流式文本片段 | `{"type": "token", "content": "..."}` |
| `done` | 回复完成 | `{"type": "done", "round_count": N, "memory_extracted": bool}` |
| `error` | 出错 | `{"type": "error", "message": "..."}` |

**字段说明**：
- `round_count`：当前是第几轮对话
- `memory_extracted`：本轮是否触发了记忆提取（每5轮为 true）

---

### 4.2 获取对话历史

```
GET /api/chat/history/{persona_id}?limit=30&offset=0
```

**参数**：
| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | number | 30 | 返回消息数量 |
| `offset` | number | 0 | 偏移量（从最新往前数） |

**响应** `200`：
```json
{
  "messages": [
    {
      "role": "user",
      "content": "我想开始减脂",
      "timestamp": "2026-05-12T14:30:00Z"
    },
    {
      "role": "assistant",
      "content": "兄弟！减脂第一步是...",
      "timestamp": "2026-05-12T14:30:05Z"
    }
  ],
  "total": 42,
  "has_more": true
}
```

---

### 4.3 清空对话历史

```
DELETE /api/chat/history/{persona_id}
```

**响应** `200`：
```json
{
  "message": "对话历史已清空",
  "memory_preserved": true
}
```

注意：清空对话**不会**清空记忆。

---

## 5. 记忆 (Memory)

### 5.1 获取记忆

```
GET /api/memory/{persona_id}
```

**响应** `200`：
```json
{
  "memories": {
    "体重": "75kg",
    "目标": "减脂增肌",
    "膝伤": "左膝半月板，避免深蹲",
    "训练频率": "每周3次"
  },
  "updated_at": "2026-05-12T15:00:00Z"
}
```

记忆为空时：
```json
{
  "memories": {},
  "updated_at": null
}
```

---

### 5.2 修改单条记忆

```
PUT /api/memory/{persona_id}/{key}
```

**请求体**：
```json
{
  "value": "80kg"
}
```

**响应** `200`：
```json
{
  "message": "记忆已更新",
  "key": "体重",
  "value": "80kg"
}
```

---

### 5.3 删除单条记忆

```
DELETE /api/memory/{persona_id}/{key}
```

**响应** `200`：
```json
{
  "message": "记忆已删除",
  "key": "体重"
}
```

---

### 5.4 清空记忆

```
DELETE /api/memory/{persona_id}
```

**响应** `200`：
```json
{
  "message": "所有记忆已清空",
  "persona_id": "fitness_coach"
}
```

---

## 6. 静态资源

```
GET /                    → static/index.html (SPA 入口)
GET /static/{file}       → 静态文件
```

---

## 7. 健康检查

```
GET /api/health
```

**响应** `200`：
```json
{
  "status": "ok",
  "version": "0.1.0",
  "name": "Nous 神智"
}
```

---

## 附录：API 速查表

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| POST | `/api/auth/register` | ❌ | 注册 |
| POST | `/api/auth/login` | ❌ | 登录 |
| GET | `/api/profile` | ✅ | 获取档案 |
| PUT | `/api/profile` | ✅ | 更新档案 |
| GET | `/api/personas` | ✅ | 人设列表 |
| POST | `/api/chat/stream` | ✅ | 发消息（SSE流式） |
| GET | `/api/chat/history/{persona_id}` | ✅ | 对话历史 |
| DELETE | `/api/chat/history/{persona_id}` | ✅ | 清空对话 |
| GET | `/api/memory/{persona_id}` | ✅ | 获取记忆 |
| PUT | `/api/memory/{persona_id}/{key}` | ✅ | 修改记忆 |
| DELETE | `/api/memory/{persona_id}/{key}` | ✅ | 删除记忆 |
| DELETE | `/api/memory/{persona_id}` | ✅ | 清空记忆 |
| GET | `/api/health` | ❌ | 健康检查 |
