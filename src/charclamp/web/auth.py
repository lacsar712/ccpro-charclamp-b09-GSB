from __future__ import annotations

from litestar.connection import ASGIConnection
from litestar.middleware.session.server_side import ServerSideSessionBackend, ServerSideSessionConfig
from litestar.security.session_auth import SessionAuth
from sqlalchemy import select

from charclamp.domain.models import User
from charclamp.infra.db import SessionLocal


async def retrieve_user_handler(session: dict, connection: ASGIConnection) -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    async with SessionLocal() as db:
        result = await db.execute(select(User).where(User.id == int(user_id)))
        return result.scalar_one_or_none()


session_auth = SessionAuth[User, ServerSideSessionBackend](
    retrieve_user_handler=retrieve_user_handler,
    session_backend_config=ServerSideSessionConfig(
        session_id_bytes=32,
    ),
    # 禁止放裸 "/"：Litestar SessionAuth 会按模式匹配，"/" 会跳过几乎全部路由的鉴权中间件，
    # 首页再读 request.user 会直接 500（user not in scope）。
    exclude=["/login", "/logout", "/static", "/schema", "/favicon.ico"],
)
