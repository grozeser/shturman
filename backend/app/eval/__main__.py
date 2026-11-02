"""Эталонный прогон агента: доводит каждый запрос до корзины и меряет качество.

    python -m app.eval                      # режим, который настроен (LLM или правила)
    python -m app.eval --min-completed 0.9  # для CI: код выхода 1, если доведено меньше 90%

Сценарий для каждого запроса: первое сообщение → ответ на уточнение (если агент спросил) → первое направление
→ «а если на два дня позже?» → «оформляй». Метрики пишутся в app/data/eval_report.json и видны на странице «Метрики».
"""

import argparse
import json
import os
import statistics
import sys
import time
from datetime import date, datetime
from pathlib import Path

if not os.environ.get("TODAY"):  # в .env переменная есть, но пустая — setdefault её бы не заменил
    os.environ["TODAY"] = "2026-10-24"  # прогон воспроизводим: те же даты, цены и рейсы
os.environ["GEO_OFFLINE"] = "1"  # каталог без сети: результат не зависит от доступности геокодера

from app.agent import llm  # noqa: E402
from app.agent.core import new_state, run_turn  # noqa: E402

CASES = Path(__file__).with_name("cases.json")
REPORT = Path(__file__).resolve().parents[1] / "data" / "eval_report.json"
TODAY = date.fromisoformat(os.environ["TODAY"])


def turn(state: dict, **body) -> float:
    started = time.perf_counter()
    for _ in run_turn(state, today=TODAY, profile={}, **body):
        pass
    return (time.perf_counter() - started) * 1000


def field_hits(brief: dict, expect: dict) -> tuple[int, int, list[str]]:
    hits, misses = 0, []
    for key, value in expect.items():
        if key == "children":
            ok = len(brief["children"]) == value
        elif key in ("kinds", "exclude"):
            ok = set(value) <= set(brief[key])
        else:
            ok = brief.get(key) == value
        hits += ok
        if not ok:
            misses.append(f"{key}: ждали {value}, получили {brief.get(key) if key != 'children' else len(brief['children'])}")
    return hits, len(expect), misses


def violations(must: list[str], brief: dict, bundle: dict) -> list[str]:
    out, back, hotel = bundle["outbound"], bundle["inbound"], bundle["hotel"]
    problems = []
    for rule in must:
        if rule == "no_night_with_kids" and (brief["children"] or brief["seniors"]) and (out["night"] or back["night"]):
            problems.append("ночной рейс с ребёнком/пожилыми")
        if rule == "no_night" and (out["night"] or back["night"]):
            problems.append("ночной рейс")
        if rule == "max_hours" and brief["max_hours"] and out["mode"] == "flight" and out["duration_min"] > brief["max_hours"] * 60:
            problems.append(f"в пути {out['duration_min']} мин при лимите {brief['max_hours']} ч")
        if rule == "within_budget" and brief["budget"] and bundle["total"] > brief["budget"]:
            problems.append(f"дороже бюджета: {bundle['total']} > {brief['budget']}")
        if rule == "pets_ok" and not (hotel["features"]["pets"] and out["pets_cabin"] and back["pets_cabin"]):
            problems.append("питомцу нельзя")
        if rule == "train_only" and brief["transport"] == "train" and out["mode"] != "train":
            problems.append("хотели поезд")
        if rule == "refundable" and not hotel["refundable"]:
            problems.append("тариф невозвратный")
    return problems


def run_case(case: dict) -> dict:
    state = new_state(f"eval-{case['id']}", "eval", {})
    ms_total = 0.0
    ms_first_rec = None
    ms_total += turn(state, text=case["text"])
    brief_after_first = json.loads(json.dumps(state["brief"]))
    for _ in range(3):
        if state["stage"] in ("inspire", "plan"):
            break
        ms_total += turn(state, text=case.get("answer", "в ноябре вдвоём"))
    if state["stage"] in ("inspire", "plan"):
        ms_first_rec = ms_total
    if state["stage"] == "inspire" and state["suggestions"]["items"]:
        ms_total += turn(state, action={"type": "select_destination", "id": state["suggestions"]["items"][0]["id"]})
    problems: list[str] = []
    kept = None
    if state["stage"] == "plan":
        hotel_before = state["plan"]["bundles"][0]["hotel"]["id"]
        turn(state, text="а если на два дня позже?")
        if state["stage"] == "plan":
            kept = state["plan"]["bundles"][0]["hotel"]["id"] == hotel_before
            turn(state, text="оформляй")
    completed = state["stage"] == "checkout"
    errors = 0
    if completed:
        bundle = state["plan"]["bundles"][state["selected"]]
        errors = sum(1 for c in bundle["checks"] if c["status"] == "error" and c["id"] not in ("visa",))
        problems += violations(case.get("must", []), state["brief"], bundle)
    else:
        problems.append(f"не дошли до корзины, этап {state['stage']}: {state['messages'][-1]['text'][:90]}")
    hits, total, misses = field_hits(brief_after_first, case.get("expect", {}))
    m = state["metrics"]
    return {
        "id": case["id"],
        "text": case["text"],
        "ok": completed and not problems and errors == 0,
        "completed": completed,
        "turns": m["turns"],
        "clarifications": m["clarifications"],
        "turns_to_first_rec": m["first_rec_turn"],
        "ms_to_first_rec": round(ms_first_rec) if ms_first_rec is not None else None,
        "connection_errors": errors,
        "violations": len([p for p in problems if not p.startswith("не дошли")]),
        "field_hits": hits,
        "field_total": total,
        "replan_kept_hotel": kept,
        "llm_fallbacks": m["llm_fallbacks"],
        "number_violations": m["number_violations"],
        "problems": problems + misses,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-completed", type=float, default=0.0)
    args = parser.parse_args()
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    results = [run_case(case) for case in cases]
    n = len(results)
    first = [r["turns_to_first_rec"] for r in results if r["turns_to_first_rec"]]
    ms = [r["ms_to_first_rec"] for r in results if r["ms_to_first_rec"] is not None]
    kept = [r["replan_kept_hotel"] for r in results if r["replan_kept_hotel"] is not None]
    summary = {
        "cases": n,
        "completed_rate": round(sum(r["completed"] for r in results) / n, 3),
        "avg_clarifications": round(statistics.mean(r["clarifications"] for r in results), 2),
        "max_clarifications": max(r["clarifications"] for r in results),
        "avg_turns_to_first_rec": round(statistics.mean(first), 2) if first else None,
        "median_ms_to_first_rec": round(statistics.median(ms)) if ms else None,
        "connection_errors": sum(r["connection_errors"] for r in results),
        "constraint_violations": sum(r["violations"] for r in results),
        "field_accuracy": round(sum(r["field_hits"] for r in results) / max(1, sum(r["field_total"] for r in results)), 3),
        "replan_kept_rate": round(sum(kept) / len(kept), 3) if kept else None,
    }
    if llm.enabled():
        summary["llm_fallbacks"] = sum(r["llm_fallbacks"] for r in results)
        summary["number_violations_blocked"] = sum(r["number_violations"] for r in results)
    report = {
        "generated": datetime.now().isoformat(timespec="minutes"),
        "mode": f"LLM {llm.settings()['model']}" if llm.enabled() else "правила (без LLM)",
        "summary": summary,
        "cases": results,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in results:
        mark = "✓" if r["ok"] else "✕"
        print(
            f"{mark} {r['id']:<20} ходов {r['turns']}, уточнений {r['clarifications']}, поля {r['field_hits']}/{r['field_total']}  {'; '.join(r['problems'])[:150]}"
        )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["completed_rate"] >= args.min_completed else 1


if __name__ == "__main__":
    sys.exit(main())
