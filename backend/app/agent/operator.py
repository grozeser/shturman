"""Консоль оператора: очередь обращений, которые агент передал людям, ответ менеджера и возврат агенту.

Агент закрывает основной поток сам, людям достаются сложные случаи — уже с брифом, планом и следом агента.
"""

import time

from app.agent import replies
from app.agent.core import add_message


def queue_row(state: dict) -> dict:
    """Строка очереди: кто ждёт, сколько, последнее сообщение и что уже собрано."""
    handoff = state["handoff"]
    last = next((m for m in reversed(state["messages"]) if m["role"] == "user"), None)
    plan = state.get("plan")
    bundle = plan["bundles"][state["selected"]] if plan and plan.get("bundles") else None
    return {
        "id": state["id"],
        "channel": "telegram" if state["user_id"].startswith("tg-") else "web",
        "status": handoff["status"],
        "reason": handoff["reason"],
        "since": handoff["since"],
        "updated": handoff["updated"],
        "unread": handoff.get("unread", 0),
        "operator": handoff.get("operator"),
        "last_message": last["text"][:140] if last else "",
        "trip": f"{bundle['dest_name']}, {replies.money(bundle['total'])}" if bundle else None,
        "stage": state["stage"],
    }


def operator_reply(state: dict, text: str, operator: str) -> dict:
    """Ответ менеджера прямо в чат путешественника (и в Telegram, если диалог там)."""
    handoff = state.setdefault("handoff", {"reason": "менеджер написал сам", "since": time.time(), "unread": 0})
    handoff |= {"status": "active", "operator": operator, "updated": time.time(), "unread": 0}
    return add_message(state, "operator", text, kind="operator", author=operator, push=True)


def close_handoff(state: dict, operator: str) -> dict:
    state["handoff"] |= {"status": "closed", "updated": time.time(), "unread": 0}
    quick = replies.plan_quick(state["plan"]) if state["stage"] == "plan" and state["plan"] else []
    return add_message(
        state,
        "agent",
        f"Менеджер ({operator}) закрыл обращение — я снова на связи. Если что-то поменять, просто напишите.",
        kind="info",
        quick=quick,
        push=True,
    )
