"""Хранилище: диалоги, брони и память о пользователях. Postgres в Docker, SQLite для локальной разработки и тестов."""

import logging
import os
import time
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

log = logging.getLogger("store")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shturman.db")
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Account(Base):
    """Аккаунт поверх пользователя: вход по почте и паролю переключает браузер на его user_id."""

    __tablename__ = "accounts"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    password: Mapped[str] = mapped_column(String(200))  # scrypt: «соль$хеш», пароль не хранится
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[dict] = mapped_column(JSON)
    updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class HotelEvent(Base):
    """Журнал для взгляда отеля: кому отель рекомендован, кому отсеян и почему, кто забронировал."""

    __tablename__ = "hotel_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    hotel_id: Mapped[str] = mapped_column(String(64), index=True)
    event: Mapped[str] = mapped_column(String(16))
    segment: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(120), default="")
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Share(Base):
    """Ссылка для попутчиков: снимок вариантов поездки на момент «позвать», чтобы голоса относились к тем же вариантам."""

    __tablename__ = "shares"
    token: Mapped[str] = mapped_column(String(24), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(32), index=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Vote(Base):
    """Голос попутчика. Ключ — браузер и имя: двое в одной вкладке-демо голосуют под разными именами."""

    __tablename__ = "votes"
    token: Mapped[str] = mapped_column(String(24), primary_key=True)
    voter_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    choice: Mapped[int] = mapped_column()
    created: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


def init_db(attempts: int = 30) -> None:
    for attempt in range(attempts):
        try:
            Base.metadata.create_all(engine)
            return
        except OperationalError:
            log.warning("БД ещё не готова, попытка %s", attempt + 1)
            time.sleep(2)
    Base.metadata.create_all(engine)


def ping() -> bool:
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return True
    except OperationalError:
        return False


def get_profile(user_id: str) -> dict:
    with Session(engine) as session:
        user = session.get(User, user_id)
        return dict(user.profile) if user else {}


def save_profile(user_id: str, profile: dict) -> None:
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user:
            user.profile = dict(profile)  # новый объект — иначе SQLAlchemy не заметит изменение JSON
        else:
            session.add(User(id=user_id, profile=dict(profile)))
        session.commit()


def get_conversation(conv_id: str) -> dict | None:
    with Session(engine) as session:
        row = session.get(Conversation, conv_id)
        return dict(row.state) if row else None


def save_conversation(state: dict) -> None:
    with Session(engine) as session:
        row = session.get(Conversation, state["id"])
        if row:
            row.state = dict(state)
        else:
            session.add(Conversation(id=state["id"], user_id=state["user_id"], state=dict(state)))
        session.commit()


def handoffs() -> list[dict]:
    """Диалоги, которые хоть раз передавали менеджеру: очередь консоли оператора и доставка ответов в Telegram."""
    with Session(engine) as session:
        return [dict(row.state) for row in session.scalars(select(Conversation)) if row.state.get("handoff")]


def conversation_metrics() -> list[dict]:
    with Session(engine) as session:
        return [row.state.get("metrics", {}) | {"stage": row.state.get("stage")} for row in session.scalars(select(Conversation))]


def get_booking(booking_id: str) -> dict | None:
    with Session(engine) as session:
        row = session.get(Booking, booking_id)
        return dict(row.data) if row else None


def save_booking(booking: dict) -> None:
    with Session(engine) as session:
        row = session.get(Booking, booking["id"])
        if row:
            row.data = dict(booking)
        else:
            session.add(Booking(id=booking["id"], user_id=booking["user_id"], data=dict(booking)))
        session.commit()


def _account(row: Account | None) -> dict | None:
    if not row:
        return None
    return {"user_id": row.user_id, "email": row.email, "name": row.name, "password": row.password, "demo": row.demo}


def get_account(user_id: str) -> dict | None:
    with Session(engine) as session:
        return _account(session.get(Account, user_id))


def get_account_by_email(email: str) -> dict | None:
    with Session(engine) as session:
        return _account(session.scalars(select(Account).where(Account.email == email)).first())


def create_account(user_id: str, email: str, name: str, password: str, demo: bool = False) -> None:
    with Session(engine) as session:
        session.add(Account(user_id=user_id, email=email, name=name, password=password, demo=demo))
        session.commit()


def list_bookings(user_id: str) -> list[dict]:
    with Session(engine) as session:
        rows = session.scalars(select(Booking).where(Booking.user_id == user_id).order_by(Booking.created.desc()))
        return [dict(row.data) for row in rows]


def all_bookings() -> list[dict]:
    with Session(engine) as session:
        return [dict(row.data) for row in session.scalars(select(Booking))]


def create_share(token: str, conversation_id: str, owner_id: str, data: dict) -> None:
    with Session(engine) as session:
        session.add(Share(token=token, conversation_id=conversation_id, owner_id=owner_id, data=data))
        session.commit()


def get_share(token: str) -> dict | None:
    with Session(engine) as session:
        row = session.get(Share, token)
        return (
            {"token": row.token, "conversation_id": row.conversation_id, "owner_id": row.owner_id, "data": dict(row.data)} if row else None
        )


def latest_share(conversation_id: str) -> dict | None:
    with Session(engine) as session:
        row = session.scalars(select(Share).where(Share.conversation_id == conversation_id).order_by(Share.created.desc())).first()
        return {"token": row.token, "data": dict(row.data)} if row else None


def save_vote(token: str, voter_id: str, name: str, choice: int) -> None:
    with Session(engine) as session:
        row = session.get(Vote, (token, voter_id, name))
        if row:
            row.choice = choice
        else:
            session.add(Vote(token=token, voter_id=voter_id, name=name, choice=choice))
        session.commit()


def votes(token: str) -> list[dict]:
    with Session(engine) as session:
        rows = session.scalars(select(Vote).where(Vote.token == token).order_by(Vote.created))
        return [{"name": row.name, "choice": row.choice, "voter_id": row.voter_id} for row in rows]


def save_events(events: list[dict]) -> None:
    if not events:
        return
    with Session(engine) as session:
        session.add_all(HotelEvent(**e) for e in events)
        session.commit()


def hotel_stats(dest_prefix: str | None = None, hotel_id: str | None = None) -> dict[str, dict]:
    """{hotel_id: {"recommended": n, "rejected": n, "booked": n, "segments": {...}, "reasons": {...}}}"""
    query = select(HotelEvent)
    if hotel_id:
        query = query.where(HotelEvent.hotel_id == hotel_id)
    elif dest_prefix:
        query = query.where(HotelEvent.hotel_id.startswith(dest_prefix + "-"))
    result: dict[str, dict] = {}
    with Session(engine) as session:
        for e in session.scalars(query):
            row = result.setdefault(e.hotel_id, {"recommended": 0, "rejected": 0, "booked": 0, "segments": {}, "reasons": {}})
            row[e.event] = row.get(e.event, 0) + 1
            if e.event in ("recommended", "booked"):
                row["segments"][e.segment] = row["segments"].get(e.segment, 0) + 1
            if e.event == "rejected" and e.reason:
                row["reasons"][e.reason] = row["reasons"].get(e.reason, 0) + 1
    return result
