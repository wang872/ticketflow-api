# TicketFlow

一句话介绍：基于 FastAPI 的企业级工单/客服后端，内置 JWT 鉴权、RBAC 权限、工单有限状态机、SLA 超时扫描与全链路审计日志，默认 SQLite 零依赖部署。

## 技术栈

| 组件 | 版本 |
| --- | --- |
| FastAPI | 0.115.6 |
| SQLAlchemy | 2.0.36 |
| Pydantic | 2.10.3 |
| PyJWT | 2.10.1 |
| Uvicorn | 0.32.1 |
| 数据库 | SQLite（默认） |
| 密码哈希 | hashlib PBKDF2-HMAC-SHA256（无 passlib） |

## 架构与核心设计

### RBAC（基于角色的访问控制）

| 角色 | 能力 |
| --- | --- |
| **customer** | 注册、创建工单、公开评论、查看/取消自己的工单 |
| **agent** | 查看全部工单、认领未指派工单、指派给自己、按 FSM 推进已指派工单、公开/内部评论 |
| **admin** | agent 全部能力 + 创建 agent 用户 + 指派给任意 agent + 查看审计日志 |

客户访问他人工单返回 **404**（防枚举），权限不足返回 **403**。

### FSM（有限状态机）

```
open → assigned → in_progress → resolved → closed
  ↓        ↓            ↓
cancelled cancelled  cancelled

resolved → in_progress（重开）
```

- `open → assigned` 只能通过 **claim** 或 **assign**，不能直接改状态
- 非法跃迁返回 **409 Conflict** 并写入审计

### SLA（服务等级协议）

| 优先级 | 响应时限 |
| --- | --- |
| P1 | 1 小时 |
| P2 | 8 小时 |
| P3 | 24 小时 |

启动时开启 daemon 后台线程，每 30 秒扫描到期工单，标记 `sla_breached=True` 并写入 `sla.breached` 审计事件。测试可直接调用 `scan_overdue_tickets()`。

### 审计（Audit Log）

每次创建工单、状态变更、指派、认领、评论、SLA 违约均记录 `actor_id`、`action`、`ticket_id`、`extra`（JSON）。Admin 通过 `GET /admin/audit` 分页查询。

## 简历写法

**中文（3–4 条）**

- 基于 FastAPI + SQLAlchemy 2 实现工单系统后端，覆盖 RBAC 三角色权限、有限状态机流转、SLA 超时检测与全链路审计日志。
- 使用 JWT 鉴权与按角色数据隔离，内部评论对客户不可见，客户访问他人工单返回 404 防止枚举。
- 进程内 daemon 线程周期性扫描 SLA 到期工单，自动标记违约并写入审计，默认 SQLite 无需 Redis/Celery/PostgreSQL。
- 提供认领/指派、状态机校验、分页查询及 pytest 集成测试，覆盖注册登录、越权、FSM 409、内部评论隔离等场景。

**English**

- Built a FastAPI helpdesk backend with RBAC, a ticket finite-state machine, SLA breach detection, and immutable audit trails.
- Implemented JWT authentication with role-based data isolation; internal comments are hidden from customers and cross-user access returns 404.
- Added an in-process SLA scanner (daemon thread) that flags overdue tickets and records audit events on SQLite with zero external dependencies.

## 本地运行

Python 3.10+

```powershell
cd g:\自动编程\ticketflow-api
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
copy .env.example .env
.venv\Scripts\python -m uvicorn app.main:app --reload
```

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs
- 健康检查: `GET /health`

种子账号：

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| admin | admin123 | admin |
| agent1 | agent123 | agent |
| alice | alice123 | customer |

Alice 名下有一张未指派的 P2 示例工单。

```powershell
.venv\Scripts\python -m pytest
```

## API 表

| 方法 | 路径 | 说明 | 角色 |
| --- | --- | --- | --- |
| POST | `/auth/register` | `{username, password}` → customer | 公开 |
| POST | `/auth/login` | 返回 `{access_token, token_type}` | 公开 |
| GET | `/auth/me` | 当前用户信息 | 已登录 |
| POST | `/tickets` | `{title, body, priority?}` 创建工单 | customer |
| GET | `/tickets` | 分页列表 `page`, `page_size` | 全部（customer 仅自己的） |
| GET | `/tickets/{id}` | 工单详情 | 全部 |
| POST | `/tickets/{id}/claim` | 认领未指派工单 | agent/admin |
| POST | `/tickets/{id}/assign` | `{user_id}` 指派 | agent（仅自己）/ admin |
| POST | `/tickets/{id}/status` | `{status}` FSM 校验 | agent/admin；customer 仅 cancel |
| POST | `/tickets/{id}/comments` | `{body, is_internal?}` | 全部 |
| GET | `/tickets/{id}/comments` | 评论列表（客户看不到 internal） | 全部 |
| POST | `/admin/users` | 创建 agent 用户 | admin |
| GET | `/admin/audit` | 审计日志分页 | admin |
| GET | `/health` | 健康检查 | 公开 |

## 目录结构

```
ticketflow-api/
├── README.md
├── LICENSE
├── .gitignore
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
├── app/
│   ├── __init__.py
│   ├── main.py              # 启动、CORS、SLA 线程、种子
│   ├── config.py            # pydantic-settings
│   ├── db.py                # SQLAlchemy engine / session
│   ├── models.py            # User, Ticket, Comment, AuditLog
│   ├── schemas.py           # Pydantic 请求/响应
│   ├── security.py          # PBKDF2 + JWT
│   ├── deps.py              # 依赖注入 / RBAC
│   ├── errors.py            # 统一异常
│   ├── seed.py              # 种子数据
│   ├── services/
│   │   ├── tickets.py       # FSM、SLA、权限、业务逻辑
│   │   └── audit.py         # 审计写入
│   └── routers/
│       ├── auth.py
│       ├── tickets.py
│       └── admin.py
└── tests/
    ├── conftest.py
    └── test_api.py
```

## 面试可讲点

1. **状态机设计**：合法转移表 `TRANSITIONS` 集中定义，服务层统一校验；认领/指派与状态变更分离，避免绕过指派流程。
2. **越权防护**：JWT 只证明身份，每个接口二次校验角色；customer 对他人工单 404 而非 403，防止工单 ID 枚举。
3. **内部评论隔离**：写入时 RBAC 拦截，读取时按角色过滤，双层防护。
4. **SLA 扫描**：daemon 线程 + 可测试的 `scan_overdue_tickets()` 纯函数，测试环境关闭线程直接调用。
5. **审计不可变**：append-only 日志，`extra` JSON 存上下文，admin 分页查询构成完整处理链。
6. **密码安全**：PBKDF2-HMAC-SHA256 + 随机 salt，不引入 passlib 依赖。

## 配置

见 `.env.example`。生产环境务必修改 `SECRET_KEY`。默认数据库路径：`sqlite:///./data/ticketflow.db`。
