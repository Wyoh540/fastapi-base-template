# 开发指南

本仓库在最佳实践文档之外，还包含一个可运行的参考实现（`src/`）。

## 环境准备

```shell
uv sync --extra dev
copy .env.example .env   # Windows；macOS/Linux 用 cp
```

要求 Python >= 3.11（`uv sync` 会依据 `.python-version` 自动准备）。

## 运行

```shell
uv run alembic upgrade head      # 建表（Alembic 是 schema 的唯一来源）
uv run uvicorn src.main:app --reload
```

- 交互式文档：<http://127.0.0.1:8000/docs>
- OpenAPI：<http://127.0.0.1:8000/openapi.json>
- 健康检查：<http://127.0.0.1:8000/health>

> `AUTO_CREATE_TABLES` 默认为 `false`。让 lifespan 用 `create_all` 建表会与迁移冲突——
> 表已存在时 `alembic upgrade` 会报 `table already exists`，且 `alembic_version` 留空。

## 数据库迁移

迁移脚本位于 `alembic/versions/`，配置在 `alembic.ini`（`script_location` 指向 `alembic/`）。

```shell
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic stamp head      # 把现有库标记为某个版本，不执行迁移
```

切换到 PostgreSQL 只需修改 `.env` 中的 `DATABASE_URL`：

```
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/appdb
```

## 认证：FastAPI 内置 OAuth2

登录使用 FastAPI 自带的 OAuth2 password flow，无需任何第三方 OAuth 库：

- `src/auth/dependencies.py` — `OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")`
- `src/auth/router.py` — `OAuth2PasswordRequestForm`（`username` + `password`，表单编码）

打开 <http://127.0.0.1:8000/docs>，点右上角 **Authorize** 按钮即可用账号密码登录，
之后所有受保护端点都会自动带上 `Authorization: Bearer <access_token>`。

命令行调用：

```shell
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&username=alice@example.com&password=sup3r-s3cret&scope="
```

`username` 字段同时接受**邮箱**或**用户名**。

刷新令牌走 OAuth2 `refresh_token` grant（FastAPI 未内置该 form 类，这里用
`Form` 实现等价语义），令牌来源优先取 `refresh_token` Cookie，其次取表单字段：

```shell
curl -X POST http://127.0.0.1:8000/api/v1/auth/refresh \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token&refresh_token=<refresh_token>"
```

| 端点 | 载荷形式 |
| --- | --- |
| `POST /api/v1/auth/signup` | JSON body |
| `POST /api/v1/auth/login` | OAuth2 password form |
| `POST /api/v1/auth/refresh` | OAuth2 refresh_token form（或 Cookie） |

## 授权：Casbin RBAC

`src/permission/` 是独立领域，用 [Casbin](https://casbin.org) 做 RBAC 授权。
依赖 `pycasbin`（导入名是 `casbin`）与官方异步适配器 `casbin-async-sqlalchemy-adapter`。

### 存储分工

| 表 | 内容 | 说明 |
| --- | --- | --- |
| `role` | 角色定义（name + description） | name 即 Casbin 策略的主体名 |
| `user_role` | 谁拥有哪个角色 | **唯一真相**，双外键 CASCADE |
| `casbin_rule` | 角色 → 权限（`p` 策略） | Casbin 原生结构：`ptype` + `v0..v5` |

Casbin 的 `g`（角色归属）策略**不落库**：每次请求从 `user_role` 读出关联，注入 enforcer
内存中的 g 段。因此不存在两份"谁是什么角色"的真相，也不需要双写同步。

`casbin_rule` 用适配器提供的 `create_casbin_rule_model(Base, "casbin_rule")` 挂到项目自己的
`Base` 上，所以 Alembic 照常管理它。

### 请求管线

受保护端点声明自己需要的权限（方法 + 路径模式）：

```python
CanListRoles = Annotated[
    User, Depends(require_permission("GET", "/api/v1/permission/roles"))
]


@router.get("/roles", response_model=list[RoleRead])
async def list_roles(_: CanListRoles, session: DbSession) -> list[dict]:
    ...
```

判定过程见 `src/permission/enforcer.py`：

1. 读 `casbin_rule` 的 `p` 策略（一次全表 SELECT）
2. 读当前用户的 `user_role` 关联
3. `enable_auto_save(False)` 后把关联注入内存 g 段，再显式 `build_role_links()`
4. `enforce(sub, obj, act)` —— 同步、纯内存

策略每请求加载，改完立即生效，也不存在多进程缓存不一致的问题。代价是每个受保护请求多两次
查询；策略表变大时可换成带 TTL 的单例缓存。

### 模型

`src/permission/model.conf`：

```ini
[request_definition]
r = sub, obj, act

[policy_definition]
p = sub, obj, act

[role_definition]
g = _, _

[policy_effect]
e = some(where (p.eft == allow))

[matchers]
m = g(r.sub, p.sub) && keyMatch(r.obj, p.obj) && r.act == p.act
```

`sub` 是用户 UUID，`obj` 是路径模式（`keyMatch` 做通配），`act` 是 HTTP 方法。

### 种子

启动时（`PERMISSION_SEED_ENABLED=true`）幂等写入，重复执行无副作用：

| 角色 | 权限 |
| --- | --- |
| `admin` | `/api/v1/permission/*` 与 `/api/v1/posts/*` 的 GET/POST/PUT/DELETE |
| `editor` | `/api/v1/posts/*` 的 GET/POST/PUT |
| `reader` | `/api/v1/posts/*` 的 GET |

`PERMISSION_SEED_ADMIN_EMAIL` 对应的账号会被授予 `admin` 角色；账号不存在则自动创建，密码取
`PERMISSION_SEED_ADMIN_PASSWORD`，未配置则随机生成并打印一次。生产环境应在角色就位后把
`PERMISSION_SEED_ENABLED` 关掉。

`admin` 角色不可删除（服务层拒绝），避免把最后一个管理员降权后无人能再管理策略。
`posts` 的权限策略目前只是预置——`posts` 端点仍用所有权判断，尚未接入 RBAC 判定。

### 踩坑清单

- **不要调用 `adapter.create_table()`**：适配器会把自己的 `Base.metadata` 指向我们的 metadata，
  调用它会按项目模型建出**全部**表。本项目的 schema 一律由 Alembic 管理。
- **不要调用 `save_policy()`**：它先 `DELETE` 全表再重写，是全量覆盖而非增量保存。本模块的
  策略增删改走 ORM（`src/permission/service.py`）。
- `casbin_rule` 的 `v0..v5` 不能出现空洞：适配器按 `str(row)` 解析，遇 `None` 即截断。
- `add_grouping_policy()` 之后必须显式 `build_role_links()`，Casbin 不会自动重建角色链。
- `enforce()` 是同步的；异步的只有 `load_policy()` / `add_policy()` 这些 I/O。

## 分页

分页是横切关注点，不归属任何单一领域，因此放在全局模块 `src/pagination.py`，
配置项（`DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE`）也在全局 `src/config.py` 中。

任何领域直接复用全局依赖与响应信封：

```python
from src.pagination import PaginatedResponse, Pagination


@router.get("", response_model=PaginatedResponse[PostSummary])
async def index(session: DbSession, params: Pagination) -> dict:
    rows, total = await list_posts(session, params=params)
    return {"items": rows, "total": total, "page": params.page, "page_size": params.page_size}
```

- `page` 从 1 开始，`page_size` 省略时取 `DEFAULT_PAGE_SIZE`
- 超过 `MAX_PAGE_SIZE` 的请求会被截断而非报错
- `PaginationParams.offset` / `.limit` 供 service 层直接拼 SQL

## 目录结构

```
src/
├── auth/            # 认证领域：JWT、密码哈希、令牌轮换
│   ├── router.py    # HTTP 端点
│   ├── schemas.py   # Pydantic 模型
│   ├── models.py    # SQLAlchemy ORM 模型
│   ├── service.py   # 业务逻辑
│   ├── dependencies.py  # 依赖（CurrentUser / DbSession）
│   ├── config.py    # 领域配置（env 前缀 AUTH_）
│   ├── constants.py # 常量与错误码
│   ├── exceptions.py# 领域异常
│   └── utils.py     # 纯工具函数
├── posts/           # 帖子领域：CRUD、分页、所有权校验
├── permission/      # 授权领域：Casbin RBAC、角色与策略管理
│   ├── router.py    # 策略管理端点
│   ├── schemas.py   # Pydantic 模型
│   ├── models.py    # role / user_role / casbin_rule ORM 模型
│   ├── service.py   # 业务逻辑
│   ├── dependencies.py  # require_permission(...) 依赖
│   ├── enforcer.py  # enforcer 构建与每请求判定管线
│   ├── config.py    # 领域配置（env 前缀 PERMISSION_）
│   ├── constants.py # 常量与错误码
│   ├── exceptions.py# 领域异常
│   └── model.conf   # Casbin 模型定义
├── config.py        # 全局配置
├── pagination.py    # 全局分页：PaginationParams / PaginatedResponse / 分页依赖
├── models.py        # 共享 ORM 基类与 mixin
├── database.py      # 异步引擎与会话工厂
├── exceptions.py    # 全局异常与错误响应格式
└── main.py          # 应用装配、lifespan、路由注册

alembic/             # Alembic 迁移
├── env.py           # 异步 env，target_metadata 取自 src.models.Base
├── script.py.mako
└── versions/        # 迁移脚本

tests/               # 测试目录镜像 src/ 的领域划分
├── conftest.py      # 共享 fixtures（内存库、HTTP client、注册 helper）
├── auth/            # ↔ src/auth/
│   └── test_auth.py
├── posts/           # ↔ src/posts/
│   └── test_posts.py
├── permission/      # ↔ src/permission/
│   ├── conftest.py  # 领域 fixtures（种子管理员、普通成员）
│   └── test_permissions.py
├── pagination/      # ↔ src/pagination.py（全局模块）
│   └── test_pagination.py
└── test_health.py   # ↔ src/main.py 的运维端点
```

跨领域引用一律使用模块名导入：

```python
from src.auth import service as auth_service
from src.posts.constants import ErrorCode as PostsErrorCode
```

## API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/v1/auth/signup` | 注册（JSON），返回令牌对 |
| POST | `/api/v1/auth/login` | OAuth2 password form 登录，返回令牌对 |
| POST | `/api/v1/auth/refresh` | OAuth2 refresh_token grant 轮换令牌 |
| GET | `/api/v1/auth/me` | 当前用户 |
| POST | `/api/v1/auth/logout` | 清除刷新 Cookie |
| POST | `/api/v1/posts` | 创建帖子（需认证） |
| GET | `/api/v1/posts` | 分页列表，可按 `status` 过滤 |
| GET | `/api/v1/posts/mine` | 当前用户的帖子 |
| GET | `/api/v1/posts/{id}` | 帖子详情 |
| PATCH | `/api/v1/posts/{id}` | 更新（仅作者） |
| DELETE | `/api/v1/posts/{id}` | 删除（仅作者） |
| POST | `/api/v1/posts/{id}/views` | 浏览计数 +1 |
| GET | `/api/v1/permission/roles` | 角色列表（含各自权限） |
| POST | `/api/v1/permission/roles` | 创建角色 |
| GET | `/api/v1/permission/roles/{role}` | 角色详情 |
| DELETE | `/api/v1/permission/roles/{role}` | 删除角色（`admin` 不可删） |
| GET | `/api/v1/permission/roles/{role}/permissions` | 角色权限列表 |
| PUT | `/api/v1/permission/roles/{role}/permissions` | 授予权限（幂等） |
| DELETE | `/api/v1/permission/roles/{role}/permissions/{id}` | 撤销权限 |
| GET | `/api/v1/permission/users/{id}/roles` | 用户的角色 |
| PUT | `/api/v1/permission/users/{id}/roles/{role}` | 授予角色（幂等） |
| DELETE | `/api/v1/permission/users/{id}/roles/{role}` | 撤销角色 |
| GET | `/health` `/ready` | 运维探针 |

## 错误响应

所有错误（含 FastAPI 自身的 422 校验错误）统一为同一信封：

```json
{
  "code": "post_not_found",
  "message": "That post does not exist.",
  "details": null
}
```

## 测试与代码质量

```shell
uv run pytest -q
uv run ruff check src tests alembic
uv run ruff format src tests alembic
```

测试使用真实的 SQLite 内存库（`tests/conftest.py`），只通过 `app.dependency_overrides`
替换数据库依赖，不 mock ORM。

测试目录与 `src/` 的领域划分一一对应：领域代码在 `src/auth/`，对应测试就在 `tests/auth/`；
全局模块 `src/pagination.py` 的测试放在 `tests/pagination/`；根级运维端点（`src/main.py`）
的测试留在 `tests/` 根目录。新增领域时，同时新建 `tests/<domain>/` 目录。
