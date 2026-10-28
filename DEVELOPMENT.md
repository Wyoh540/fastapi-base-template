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
