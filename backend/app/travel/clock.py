"""«Сегодня» для всего приложения: TODAY=YYYY-MM-DD фиксирует дату для воспроизводимых демо и тестов."""

import os
from datetime import date


def today() -> date:
    fixed = os.getenv("TODAY")
    return date.fromisoformat(fixed) if fixed else date.today()
