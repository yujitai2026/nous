# 神智 / Nous — 任务拆分与排期 (TASKS)

> 版本: v0.1.0 | 最后更新: 2026-05-12  
> 状态: 草案，待评审  
> 前置文档: [SPEC.md](./SPEC.md) | [ARCHITECTURE.md](./ARCHITECTURE.md) | [API.md](./API.md)

---

## 开发原则

1. **自底向上**：先底层模块，再上层功能
2. **每步可验证**：每个任务完成后都能测试
3. **前后端交替**：后端接口写完立刻配前端页面，即时可见效果
4. **从 persona-chat 复用**：能搬的搬，该重写的重写

---

## 阶段总览

```
阶段1：项目骨架与底层         ████░░░░░░  预估 30min
阶段2：用户认证               ████░░░░░░  预估 40min
阶段3：用户档案               ██░░░░░░░░  预估 20min
阶段4：核心对话               ██████░░░░  预估 50min
阶段5：记忆系统               ████░░░░░░  预估 40min
阶段6：前端整合与美化          ██████░░░░  预估 50min
阶段7：测试与部署             ████░░░░░░  预估 30min
                                         ─────────
                                         总计约 4.5h
```

---

## 阶段1：项目骨架与底层

> 目标：搭建项目结构，完成 FileStore 和 LLMClient 两个底层模块

### T1.1 项目初始化
- [ ] 创建 `nous/src/` 下的模块文件结构
- [ ] 创建 `requirements.txt`（fastapi, uvicorn, httpx, bcrypt, pyjwt）
- [ ] 创建 `src/__init__.py`, `src/app.py`（FastAPI 入口骨架）
- [ ] 从 persona-chat 复制 5 个人设 JSON 到 `nous/personas/`
- **验证**：`uvicorn src.app:app` 能启动，访问 `/api/health` 返回 OK

### T1.2 FileStore 实现
- [ ] 创建 `src/store.py`
- [ ] 实现 `FileStore` 类：带 asyncio.Lock 的 read_json / write_json
- [ ] 单元测试：并发读写不冲突
- **验证**：测试脚本通过

### T1.3 LLMClient 实现
- [ ] 创建 `src/llm.py`
- [ ] 实现 `LLMClient`：`chat_stream`（流式）和 `chat`（非流式）
- [ ] 从 persona-chat 的 app.py 迁移 DashScope 调用逻辑
- **验证**：简单脚本调用 chat("你好") 能返回

---

## 阶段2：用户认证

> 目标：用户能注册、登录，API 有认证保护

### T2.1 Auth 后端
- [ ] 创建 `src/auth.py`
- [ ] 实现 `register(username, password)` → 校验 + bcrypt + 写 users.json + 签 JWT
- [ ] 实现 `login(username, password)` → 验证 + 签 JWT
- [ ] 实现 `verify_token(token)` → 解码 + 校验过期
- [ ] 实现 `auth_required` FastAPI 依赖注入
- **验证**：curl 注册 → 登录 → 用 token 访问受保护接口

### T2.2 Auth API 路由
- [ ] `POST /api/auth/register`
- [ ] `POST /api/auth/login`
- [ ] 错误码：USERNAME_EXISTS, USERNAME_INVALID, PASSWORD_TOO_SHORT, LOGIN_FAILED
- **验证**：curl 完整流程测试

### T2.3 登录/注册前端页面
- [ ] 创建 `static/index.html`（SPA 入口）
- [ ] 实现登录/注册表单 UI
- [ ] 前端 JS：调用注册/登录 API，存 token 到 localStorage
- [ ] 未登录自动跳转登录页
- **验证**：浏览器能注册、登录、看到跳转

---

## 阶段3：用户档案

> 目标：用户能填写和修改个人档案

### T3.1 Profile 后端
- [ ] 创建 `src/profile.py`
- [ ] 实现 `get_profile(username)` / `update_profile(username, data)`
- [ ] 字段校验（age 范围、interests 长度等）
- [ ] API 路由：`GET /api/profile`、`PUT /api/profile`
- **验证**：curl 读写档案

### T3.2 Profile 前端页面
- [ ] 个人设置页面 UI（表单：年龄、性别、职业、爱好、自由文本）
- [ ] 兴趣爱好做标签式输入（输入后回车添加标签）
- [ ] 保存按钮调 PUT API
- **验证**：浏览器填写、保存、刷新后数据仍在

---

## 阶段4：核心对话

> 目标：用户能选人设、发消息、收到流式回复

### T4.1 人设加载
- [ ] 创建 `src/personas.py`
- [ ] 从 `personas/` 目录加载所有人设配置
- [ ] API 路由：`GET /api/personas`
- **验证**：curl 返回 5 个人设列表

### T4.2 对话后端（核心）
- [ ] 创建 `src/chat.py`
- [ ] 实现上下文构建：人设 prompt + 用户档案 + 人设记忆 + 最近20轮 + 当前输入
- [ ] 实现 SSE 流式端点 `POST /api/chat/stream`
- [ ] 消息持久化（保存 user 和 assistant 消息到文件）
- [ ] 轮数计算（为记忆提取做准备）
- [ ] 实现 `GET /api/chat/history/{persona_id}`
- [ ] 实现 `DELETE /api/chat/history/{persona_id}`
- **验证**：curl 发消息，收到 SSE 流式回复

### T4.3 人设选择前端页面
- [ ] 5 个人设卡片展示（头像 emoji + 名称 + 描述）
- [ ] 点击卡片进入对话页
- **验证**：浏览器看到5个卡片，能点击进入

### T4.4 对话前端页面
- [ ] 聊天界面 UI（消息气泡、输入框、发送按钮）
- [ ] SSE 流式接收与逐字渲染
- [ ] 页面加载时拉取历史消息
- [ ] 清空对话按钮
- [ ] 从 persona-chat 前端复用流式渲染逻辑
- **验证**：浏览器能完整对话，流式显示

---

## 阶段5：记忆系统

> 目标：每5轮自动提取记忆，用户可查看/编辑

### T5.1 记忆提取后端
- [ ] 创建 `src/memory.py`
- [ ] 实现记忆提取 prompt 模板
- [ ] 实现 `extract_memory(username, persona_id)`：调 LLM 提取 → 合并写入
- [ ] 实现 `maybe_extract_memory()`：判断轮数 % 5，异步触发
- [ ] 在 chat 流程末尾挂上 `maybe_extract_memory`
- **验证**：对话5轮后，检查 memories 文件有内容

### T5.2 记忆 CRUD 后端
- [ ] API 路由：`GET /api/memory/{persona_id}`
- [ ] API 路由：`PUT /api/memory/{persona_id}/{key}`
- [ ] API 路由：`DELETE /api/memory/{persona_id}/{key}`
- [ ] API 路由：`DELETE /api/memory/{persona_id}`（清空）
- **验证**：curl 读写删记忆

### T5.3 记忆注入验证
- [ ] 确认记忆正确注入 system prompt
- [ ] 测试：先聊出记忆 → 清空对话 → 新对话中 AI 仍记得用户信息
- **验证**：对话中 AI 自然引用记忆内容

### T5.4 记忆面板前端
- [ ] 对话页侧边栏/弹窗，展示当前人设记忆
- [ ] 每条记忆显示 key-value，带编辑和删除按钮
- [ ] 编辑：点击后变为输入框，确认保存
- [ ] 清空所有记忆按钮（二次确认）
- [ ] SSE done 事件中 `memory_extracted: true` 时，自动刷新记忆面板
- **验证**：浏览器操作记忆，刷新后生效

---

## 阶段6：前端整合与美化

> 目标：完整的用户体验，移动端友好

### T6.1 导航与路由
- [ ] SPA hash 路由完善（#/login, #/, #/chat/{id}, #/profile）
- [ ] 顶栏导航（返回、设置）
- [ ] 未登录保护（自动跳转登录）
- [ ] Token 过期处理（自动跳转登录）

### T6.2 响应式适配
- [ ] 移动端布局优化（对话页、人设卡片、档案表单）
- [ ] 触摸手势友好（滑动、点击区域）
- [ ] 字体大小、间距调优

### T6.3 视觉美化
- [ ] 品牌元素：名称"神智"、配色方案
- [ ] 人设卡片美化（渐变背景、hover 效果）
- [ ] 对话气泡美化（区分用户/AI、时间戳）
- [ ] 加载动画（流式回复中的打字指示器）
- [ ] 空状态设计（无对话、无记忆时的提示）

---

## 阶段7：测试与部署

> 目标：确保稳定，正式上线

### T7.1 端到端测试
- [ ] 完整流程：注册 → 填档案 → 选人设 → 对话5轮 → 检查记忆 → 编辑记忆 → 清空对话 → 验证记忆保留
- [ ] 多用户隔离测试：用户 A 和用户 B 数据互不可见
- [ ] Token 过期测试
- [ ] 边界情况：空输入、超长输入、特殊字符

### T7.2 部署
- [ ] 确认端口 8767 可用
- [ ] 启动服务，验证公网可访问
- [ ] 日志配置
- [ ] 进程管理（确保稳定运行）

### T7.3 文档更新
- [ ] 更新 CHANGELOG.md
- [ ] 根据实际实现修正 SPEC / ARCHITECTURE / API 文档中的偏差

---

## 任务依赖关系图

```
T1.1 项目初始化
 ├── T1.2 FileStore
 │    └── T2.1 Auth 后端
 │         ├── T2.2 Auth API
 │         │    └── T2.3 登录前端
 │         │         └── T3.2 Profile 前端
 │         └── T3.1 Profile 后端
 │              └── T4.2 对话后端
 │                   ├── T4.4 对话前端
 │                   └── T5.1 记忆提取
 │                        ├── T5.2 记忆 CRUD
 │                        │    └── T5.4 记忆面板前端
 │                        └── T5.3 记忆注入验证
 └── T1.3 LLMClient
      └── T4.2 对话后端（合流）

T4.1 人设加载（独立）
 └── T4.3 人设选择前端

T6.x 前端整合 ← 依赖阶段2-5全部完成
T7.x 测试部署 ← 依赖阶段1-6全部完成
```

---

## 执行策略

建议由 **Luna（露娜）** 按阶段顺序执行，每阶段完成后向阿太汇报进展。

关键检查点（需要阿太确认）：
1. **阶段2完成后** — 注册登录跑通，确认交互体验
2. **阶段4完成后** — 核心对话跑通，确认对话效果
3. **阶段5完成后** — 记忆系统跑通，确认提取质量
4. **阶段7部署后** — 全流程验收
