"""Kurulum yardımcısı: Zernio'daki bağlı hesapları (ZERNIO_ACCOUNT_ID için) ve Telegram botunu kontrol eder."""
from __future__ import annotations

import logging

import requests

from . import publish, telegram


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("=== Zernio hesapları ===")
    if publish._key():
        try:
            for a in publish.accounts():
                print(f"{a.get('platform'):10} {a.get('displayName') or a.get('username')!s:30}  ID: {a.get('_id')}")
            print("\nMUSİCAİ YouTube kanalının ID'sini ZERNIO_ACCOUNT_ID secret'ına yaz.")
        except Exception as e:
            print("Zernio hatası:", e)
    else:
        print("ZERNIO_API_KEY yok")
    print("\n=== Telegram ===")
    if telegram.enabled():
        try:
            me = requests.get(telegram._api("getMe"), timeout=30).json()["result"]["username"]
            print(f"Bot: @{me}")
            print("Sohbet:", telegram.chat_id())
            telegram.send_text("🎵 MUSİCAİ botu bağlandı! Yeni şarkılar buraya gelecek.")
        except Exception as e:
            print("Telegram:", e)
    else:
        print("TELEGRAM_BOT_TOKEN yok")


if __name__ == "__main__":
    main()
