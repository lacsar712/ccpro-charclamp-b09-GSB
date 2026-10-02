from __future__ import annotations

from datetime import timedelta

from charclamp.domain.models import BurnShift, Clamp, Site, User, utcnow
from charclamp.infra.db import SyncSessionLocal
from charclamp.infra.security import hash_password


def seed_demo() -> None:
    with SyncSessionLocal() as session:
        admin = session.query(User).filter_by(username="admin").first()
        if not admin:
            admin = User(username="admin", role="admin", password_hash=hash_password("123456"))
            session.add(admin)
        else:
            admin.password_hash = hash_password("123456")
            admin.role = "admin"

        worker = session.query(User).filter_by(username="worker").first()
        if not worker:
            worker = User(username="worker", role="worker", password_hash=hash_password("123456"))
            session.add(worker)
        else:
            worker.password_hash = hash_password("123456")
            worker.role = "worker"

        if session.query(Site).first():
            session.commit()
            return

        site = Site(name="乌石岗焖烧坞", location="河谷台地北侧", notes="青冈为主，夜班闷窑")
        session.add(site)
        session.flush()

        # 两座窑：班次炭品分别为 A、B 两种字母，分属两窑；
        # 窑态一座焖烧中、一座已码窑，便于核对「其中焖烧中座数」是去重窑数的子集。
        c1 = Clamp(site=site, code="坞东-甲", status=Clamp.STATUS_BURNING, wood_species="青冈")
        c2 = Clamp(site=site, code="坞东-乙", status=Clamp.STATUS_STACKED, wood_species="松木")
        session.add_all([c1, c2])
        session.flush()

        now = utcnow()
        session.add_all(
            [
                BurnShift(
                    clamp=c1,
                    started_at=now - timedelta(hours=10),
                    peak_temp_c=455.0,
                    charcoal_grade="A",
                    notes="甲窑班次，炭品字母 A",
                ),
                BurnShift(
                    clamp=c2,
                    started_at=now - timedelta(hours=3),
                    peak_temp_c=None,
                    charcoal_grade="B",
                    notes="乙窑班次，炭品字母 B；刚码窑未点火",
                ),
            ]
        )
        session.commit()
