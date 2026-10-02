from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

from litestar import Controller, MediaType, Request, get, post
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.response import Redirect, Template
from sqlalchemy import select, update
from sqlalchemy.orm import joinedload, selectinload

from charclamp.domain.models import BurnShift, Clamp, User
from charclamp.domain.rules import RuleError, assert_can_set_clamp_status, can_mark_clamp_drawn
from charclamp.infra.db import SessionLocal
from charclamp.infra.security import verify_password

STATUS_LABELS = {
    Clamp.STATUS_STACKED: "已码窑",
    Clamp.STATUS_BURNING: "焖烧中",
    Clamp.STATUS_DRAWN: "已出炭",
}


def _set_flash(request: Request, message: str, category: str = "ok") -> None:
    data = dict(request.session or {})
    data["flash"] = message
    data["flash_cat"] = category
    request.set_session(data)


def _pop_flash(request: Request) -> tuple[str | None, str | None]:
    data = dict(request.session or {})
    message = data.pop("flash", None)
    category = data.pop("flash_cat", None)
    if message is not None or category is not None:
        request.set_session(data)
    return message, category


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _parse_grade(raw: str | None) -> str | None:
    """炭品字母筛选值：精确匹配，空串视为不筛选。"""
    if raw is None:
        return None
    grade = raw.strip()
    return grade or None


def _timeline_redirect(clamp_id: int | None, grade: str | None) -> str:
    params: list[str] = []
    if clamp_id is not None:
        params.append(f"clamp_id={clamp_id}")
    if grade:
        params.append(f"grade={quote_plus(grade)}")
    return "/?" + "&".join(params) if params else "/"


async def _load_timeline_context(
    clamp_id: int | None = None, grade: str | None = None
) -> dict[str, Any]:
    async with SessionLocal() as db:
        clamps = list(
            (
                await db.execute(
                    select(Clamp).options(joinedload(Clamp.site)).order_by(Clamp.code)
                )
            )
            .scalars()
            .all()
        )
        # 班次 + 所属窑用 joinedload 压成同一条 SELECT：
        # 三组数（班次张数 / 去重窑数 / 焖烧中窑数）取自同一快照，互不互殴。
        query = (
            select(BurnShift)
            .options(joinedload(BurnShift.clamp).joinedload(Clamp.site))
            .order_by(BurnShift.started_at.desc())
        )
        if clamp_id is not None:
            query = query.where(BurnShift.clamp_id == clamp_id)
        if grade is not None:
            # 精确匹配：必须 =，不能用 LIKE/contains。
            query = query.where(BurnShift.charcoal_grade == grade)
        shifts = list((await db.execute(query)).scalars().all())

        hit_clamp_ids: set[int] = set()
        burning_clamp_ids: set[int] = set()
        for shift in shifts:
            hit_clamp_ids.add(shift.clamp_id)
            if shift.clamp.status == Clamp.STATUS_BURNING:
                burning_clamp_ids.add(shift.clamp_id)

        site_name = clamps[0].site.name if clamps else "乌石岗焖烧坞"

    return {
        "clamps": clamps,
        "shifts": shifts,
        "active_clamp_id": clamp_id,
        "grade": grade,
        # 三组数：与筛后卡片、剪影点亮、焖烧中点亮子集一一对应。
        "hit_clamp_ids": hit_clamp_ids,
        "burning_clamp_ids": burning_clamp_ids,
        "shift_count": len(shifts),
        "clamp_count": len(hit_clamp_ids),
        "burning_count": len(burning_clamp_ids),
        "status_labels": STATUS_LABELS,
        "site_name": site_name,
    }


class AuthController(Controller):
    path = ""
    tags = ["auth"]

    @get("/login", media_type=MediaType.HTML)
    async def login_page(self, request: Request) -> Template:
        flash, flash_cat = _pop_flash(request)
        return Template(
            template_name="login.html",
            context={"flash": flash, "flash_cat": flash_cat},
        )

    @post("/login")
    async def login(
        self,
        request: Request,
        data: dict[str, Any] = Body(media_type=RequestEncodingType.URL_ENCODED),
    ) -> Redirect:
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        async with SessionLocal() as db:
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if not user or not verify_password(password, user.password_hash):
                request.set_session({"flash": "用户名或密码错误", "flash_cat": "error"})
                return Redirect("/login")
            request.set_session({"user_id": user.id})
        return Redirect("/")

    @get("/logout")
    async def logout(self, request: Request) -> Redirect:
        request.clear_session()
        return Redirect("/login")


class TimelineController(Controller):
    path = ""
    tags = ["timeline"]

    @get("/", media_type=MediaType.HTML)
    async def timeline(self, request: Request) -> Template | Redirect:
        if not request.user:
            return Redirect("/login")
        flash, flash_cat = _pop_flash(request)
        clamp_id = _parse_optional_int(request.query_params.get("clamp_id"))
        grade = _parse_grade(request.query_params.get("grade"))
        ctx = await _load_timeline_context(clamp_id, grade)
        return Template(
            template_name="timeline.html",
            context={
                **ctx,
                "user": request.user,
                "flash": flash,
                "flash_cat": flash_cat,
            },
        )

    @get("/timeline/partial", media_type=MediaType.HTML)
    async def timeline_partial(self, request: Request) -> Template | Redirect:
        if not request.user:
            return Redirect("/login")
        clamp_id = _parse_optional_int(request.query_params.get("clamp_id"))
        grade = _parse_grade(request.query_params.get("grade"))
        ctx = await _load_timeline_context(clamp_id, grade)
        return Template(
            template_name="partials/board.html",
            context={
                **ctx,
                "user": request.user,
            },
        )

    @get("/drawer/shift-new", media_type=MediaType.HTML)
    async def drawer_shift_new(self, request: Request) -> Template | Redirect:
        if not request.user:
            return Redirect("/login")
        clamp_id = _parse_optional_int(request.query_params.get("clamp_id"))
        async with SessionLocal() as db:
            clamps = list((await db.execute(select(Clamp).order_by(Clamp.code))).scalars().all())
        return Template(
            template_name="partials/drawer_shift.html",
            context={
                "clamps": clamps,
                "preselect_clamp_id": clamp_id,
                "user": request.user,
            },
        )

    @get("/drawer/clamp/{clamp_id:int}", media_type=MediaType.HTML)
    async def drawer_clamp(self, request: Request, clamp_id: int) -> Template | Redirect:
        if not request.user:
            return Redirect("/login")
        async with SessionLocal() as db:
            result = await db.execute(
                select(Clamp)
                .where(Clamp.id == clamp_id)
                .options(selectinload(Clamp.shifts), joinedload(Clamp.site))
            )
            clamp = result.scalar_one_or_none()
            if not clamp:
                return Redirect("/")
        can_drawn, drawn_msg = can_mark_clamp_drawn(clamp)
        return Template(
            template_name="partials/drawer_clamp.html",
            context={
                "clamp": clamp,
                "status_labels": STATUS_LABELS,
                "can_drawn": can_drawn,
                "drawn_msg": drawn_msg,
                "user": request.user,
            },
        )


class ShiftController(Controller):
    path = "/shifts"
    tags = ["shifts"]

    @post("/new")
    async def create_shift(
        self,
        request: Request,
        data: dict[str, Any] = Body(media_type=RequestEncodingType.URL_ENCODED),
    ) -> Redirect:
        if not request.user:
            return Redirect("/login")
        started_raw = data.get("started_at") or ""
        started_at = datetime.fromisoformat(started_raw) if started_raw else datetime.utcnow()
        peak_raw = (data.get("peak_temp_c") or "").strip()
        peak = float(peak_raw) if peak_raw else None
        clamp_id = int(data["clamp_id"])
        async with SessionLocal() as db:
            shift = BurnShift(
                clamp_id=clamp_id,
                started_at=started_at,
                peak_temp_c=peak,
                charcoal_grade=(data.get("charcoal_grade") or "B").strip(),
                notes=(data.get("notes") or "").strip(),
            )
            db.add(shift)
            clamp = (
                await db.execute(select(Clamp).where(Clamp.id == clamp_id))
            ).scalar_one_or_none()
            if clamp and clamp.status == Clamp.STATUS_STACKED:
                clamp.status = Clamp.STATUS_BURNING
            await db.commit()
        _set_flash(request, "焖烧班次已登记", "ok")
        return Redirect(f"/?clamp_id={clamp_id}")

    @post("/{shift_id:int}/grade")
    async def set_grade(
        self,
        request: Request,
        shift_id: int,
        data: dict[str, Any] = Body(media_type=RequestEncodingType.URL_ENCODED),
    ) -> Redirect:
        """改某班次的炭品字母。单行原子 UPDATE，两人各改各的班次互不覆盖。"""
        if not request.user:
            return Redirect("/login")
        grade = (data.get("charcoal_grade") or "").strip()
        ret_clamp_id = _parse_optional_int(data.get("clamp_id"))
        ret_grade = _parse_grade(data.get("grade"))
        if not grade:
            _set_flash(request, "炭品字母不能为空", "error")
            return Redirect(_timeline_redirect(ret_clamp_id, ret_grade))
        if len(grade) > 40:
            _set_flash(request, "炭品字母过长（最多 40 字符）", "error")
            return Redirect(_timeline_redirect(ret_clamp_id, ret_grade))
        async with SessionLocal() as db:
            result = await db.execute(
                update(BurnShift)
                .where(BurnShift.id == shift_id)
                .values(charcoal_grade=grade)
            )
            await db.commit()
        if result.rowcount == 0:
            _set_flash(request, "班次不存在，炭品未改", "error")
        else:
            _set_flash(request, f"班次炭品已改为 {grade}", "ok")
        return Redirect(_timeline_redirect(ret_clamp_id, ret_grade))


class ClampController(Controller):
    path = "/clamps"
    tags = ["clamps"]

    @post("/{clamp_id:int}/status")
    async def set_status(
        self,
        request: Request,
        clamp_id: int,
        data: dict[str, Any] = Body(media_type=RequestEncodingType.URL_ENCODED),
    ) -> Redirect:
        if not request.user:
            return Redirect("/login")
        new_status = (data.get("status") or "").strip()
        async with SessionLocal() as db:
            result = await db.execute(
                select(Clamp)
                .where(Clamp.id == clamp_id)
                .options(joinedload(Clamp.shifts))
            )
            clamp = result.scalar_one_or_none()
            if not clamp:
                return Redirect("/")
            try:
                assert_can_set_clamp_status(clamp, new_status)
                clamp.status = new_status
                await db.commit()
                _set_flash(request, f"窑 {clamp.code} 状态已更新", "ok")
            except RuleError as exc:
                _set_flash(request, str(exc), "error")
        return Redirect(f"/?clamp_id={clamp_id}")
