from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from jinja2 import Environment, FileSystemLoader, select_autoescape
from litestar import Litestar, Request
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.response import Redirect
from litestar.static_files import create_static_files_router
from litestar.template.config import TemplateConfig

from charclamp.web.auth import session_auth
from charclamp.web.controllers import AuthController, ClampController, ShiftController, TimelineController

WEB_DIR = Path(__file__).parent / "web"
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

# grade 会进 URL（?grade=...），模板里必须用 urlencode 过滤器后再拼接，
# 否则字母含空格 / & 等字符时筛选链接会坏。
_jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(enabled_extensions=("html", "htm", "xml")),
)
_jinja_env.filters["urlencode"] = quote_plus


def _redirect_login(_: Request, __: Exception) -> Redirect:
    return Redirect("/login")


app = Litestar(
    route_handlers=[
        TimelineController,
        AuthController,
        ClampController,
        ShiftController,
        create_static_files_router(path="/static", directories=[STATIC_DIR]),
    ],
    template_config=TemplateConfig(directory=TEMPLATE_DIR, engine=JinjaTemplateEngine.from_environment(_jinja_env)),
    on_app_init=[session_auth.on_app_init],
    exception_handlers={
        NotAuthorizedException: _redirect_login,
        PermissionDeniedException: _redirect_login,
    },
    debug=True,
)
