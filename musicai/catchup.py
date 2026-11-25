"""Yedek tetik: GitHub'ın zamanlayıcısı gecikir/atlarsa ya da üretim çökerse saatlik onay işi bu kontrolü yapar.

- Üretim günü (Salı/Cuma, TR) 16:00'dan sonra o günün şarkısı yoksa -> "run"
- Üretim gününün şarkısı hiç çıkmadıysa ertesi gün 10:00'dan sonra telafi -> "run"
- Aynı gün en fazla 3 otomatik deneme (sonsuz döngü olmasın)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from . import state

PRODUCE_DAYS = {1, 4}  # Pazartesi=0 -> Salı=1, Cuma=4
START_HOUR = 16
MAKEUP_HOUR = 10
MAX_TRIES = 3


def tr_now() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=3)


def last_song_day() -> str:
    """state/songs içindeki en yeni şarkının TR tarihi (elle başlatılan üretimler de sayılır)."""
    days = []
    for song in state.songs():
        d = song.get("date")  # "YYYY-MM-DD HH:MM" (UTC)
        if d:
            try:
                t = datetime.strptime(d, "%Y-%m-%d %H:%M") + timedelta(hours=3)
                days.append(t.strftime("%Y-%m-%d"))
            except ValueError:
                pass
    return max(days, default="")


def due(now: datetime | None = None, st: dict | None = None) -> bool:
    now = now or tr_now()
    st = st if st is not None else state.load()
    today = now.strftime("%Y-%m-%d")
    if st.get("auto_tries", {}).get(today, 0) >= MAX_TRIES:
        return False
    last = max(st.get("last_auto_date", ""), last_song_day())  # son BAŞARILI üretimin günü (elle olanlar dahil)
    if last == today:
        return False
    if now.weekday() in PRODUCE_DAYS and now.hour >= START_HOUR:
        return True
    yday = now - timedelta(days=1)
    if yday.weekday() in PRODUCE_DAYS and now.hour >= MAKEUP_HOUR:
        return last < yday.strftime("%Y-%m-%d")  # dünkü şarkı çıkmadıysa telafi
    return False


def main() -> None:
    result = "run" if due() else "skip"
    print(result)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"result={result}\n")


if __name__ == "__main__":
    main()
