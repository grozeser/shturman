"""Прогон «злых» запросов: незнакомые формулировки, опечатки, сленг, разговоры не о поездке.

    cd backend && python ../scripts/redteam.py                 # весь набор из redteam_queries.txt
    cd backend && python ../scripts/redteam.py --only-flagged  # только подозрительные

Одна строка файла — один диалог, реплики через « | ». Строка, начинающаяся с «~», — не про поездку:
агент должен ответить, но не собирать план. Режим тот, что настроен (без ключа — правила), даты и каталог
фиксированы как в eval. Выход 1, если какой-то ход упал с исключением.
"""

import os
import sys
import traceback
from pathlib import Path

if not os.environ.get("TODAY"):
    os.environ["TODAY"] = "2026-10-24"
os.environ["GEO_OFFLINE"] = "1"
sys.path.insert(0, os.getcwd())

from datetime import date  # noqa: E402

from app.agent.core import new_state, run_turn  # noqa: E402
from app.travel.brief import chips  # noqa: E402

QUERIES = Path(__file__).with_name("redteam_queries.txt")
TODAY = date.fromisoformat(os.environ["TODAY"])
PROGRESS = {"clarify", "inspire", "compare", "plan", "checkout", "booked"}  # стадии, на которых агент двинулся вперёд


def run(line: str) -> tuple[list[str], dict, str | None]:
    """Возвращает флаги, итоговое состояние и последний ответ агента."""
    offtopic = line.startswith("~")
    state, flags = new_state("redteam", "redteam", {}), []
    for text in line.lstrip("~").split(" | "):
        try:
            for _ in run_turn(state, text=text.strip(), today=TODAY, profile={}):
                pass
        except Exception:  # noqa: BLE001 — собираем все падения в отчёт, а не останавливаемся на первом
            return ["EXCEPTION " + traceback.format_exc(limit=-3).strip().splitlines()[-1]], state, None
    last = next((m for m in reversed(state["messages"]) if m["role"] == "agent"), None)
    if offtopic and state["stage"] in ("plan", "checkout"):
        flags.append("собрал план на запрос не о поездке")
    if not offtopic and state["stage"] not in PROGRESS:
        flags.append(f"не двинулся: стадия {state['stage']}")
    if not offtopic and last and last.get("kind") in ("error", "info") and "не до конца понял" in last["text"].lower():
        flags.append("не понял")
    return flags, state, last["text"] if last else None


def main() -> int:
    only_flagged = "--only-flagged" in sys.argv
    lines = [s.strip() for s in QUERIES.read_text(encoding="utf-8").splitlines() if s.strip() and not s.startswith("#")]
    crashed = flagged = 0
    for line in lines:
        flags, state, answer = run(line)
        crashed += any(f.startswith("EXCEPTION") for f in flags)
        flagged += bool(flags)
        if only_flagged and not flags:
            continue
        mark = "✕" if flags else "·"
        labels = ", ".join(c["label"] for c in chips(state["brief"], state["sources"]))
        print(f"{mark} {line}\n    стадия: {state['stage']} | бриф: {labels or '—'}")
        if answer:
            print("    ответ:", answer.splitlines()[0][:160])
        for flag in flags:
            print("    !", flag)
    print(f"\nИтого: {len(lines)} диалогов, подозрительных {flagged}, падений {crashed}")
    return 1 if crashed else 0


if __name__ == "__main__":
    sys.exit(main())
