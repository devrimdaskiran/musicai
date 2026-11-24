"""Yedek tetik: GitHub'ın zamanlayıcısı gecikir ya da çalışmayı atlarsa, saatlik onay işi bu kontrolü yapar.

Üretim günü (Salı/Cuma, TR) saat 16:00'yı geçmiş ve bugün henüz otomatik üretim denenmemişse "run" yazar;
workflow bu durumda produce.yml'i auto=1 ile başlatır.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from . import state

PRODUCE_DAYS = {1, 4}  # Pazartesi=0 → Salı=1, Cuma=4
START_HOUR = 16


def tr_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=3)


def due() -> bool:
    now = tr_now()
    if now.weekday() not in PRODUCE_DAYS or now.hour < START_HOUR:
        return False
    return state.load().get("last_auto_date") != now.strftime("%Y-%m-%d")


def main() -> None:
    result = "run" if due() else "skip"
    print(result)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"result={result}\n")


if __name__ == "__main__":
    main()
