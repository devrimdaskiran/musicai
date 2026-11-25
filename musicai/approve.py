"""Onay: Telegram'daki "✅ Yayınla / ❌ Atla" butonlarını işler (cron-job.org ile ~15 dk.da bir).

Yayınla -> tam şarkı videosu (kapak görseliyle) + 40 sn'lik Short, YouTube'a aynı başlıkla yüklenir.
"""
from __future__ import annotations

import logging
import os

from . import publish, state, telegram

log = logging.getLogger("musicai.approve")


def handle(action: str, key: str, msg_id: int | None, cb_id: str | None) -> bool:
    item = state.pending().get(key)
    if not item:
        if cb_id:
            telegram.answer_callback(cb_id, "Bu şarkı zaten işlendi.")
        return False
    msg_id = msg_id or item.get("message_id")
    if action == "skip":
        if cb_id:
            telegram.answer_callback(cb_id, "Atlandı")
        telegram.set_buttons(msg_id, "❌ Atlandı")
        state.remove_pending(key)
        state.add_history({"key": key, "title": item["title"], "status": "skipped", "date": state.now()})
        return True
    if action != "pub":
        return False
    if cb_id:
        telegram.answer_callback(cb_id, "Yükleniyor…")
    telegram.set_buttons(msg_id, "⏳ YouTube'a yükleniyor…")
    urls = {}
    try:
        if not item.get("full_done"):
            r = publish.post_youtube(item["full_url"], item["title"], item["description"], item["tags"],
                                     thumb_url=item.get("thumb_url"))
            urls["full"] = publish.post_url(r)
            item["full_done"] = True
            state.add_pending(key, item)  # Short başarısız olursa tam şarkı tekrar yüklenmesin
        r = publish.post_youtube(item["short_url"], item["title"], item["short_description"], item["tags"])
        urls["short"] = publish.post_url(r)
    except Exception as e:
        log.error("Yükleme başarısız: %s", e)
        telegram.set_buttons(msg_id, None)
        telegram.send_text(f"⚠️ Yüklenemedi: {e}\nBir saat içinde tekrar denenecek; istersen ✅ ile tekrar gönder.", msg_id)
        import requests  # butonları geri koy ki tekrar basılabilsin
        try:
            requests.post(telegram._api("editMessageReplyMarkup"), data={
                "chat_id": telegram.chat_id(), "message_id": msg_id, "reply_markup": telegram._buttons(key)}, timeout=30)
        except Exception:
            pass
        return False
    telegram.set_buttons(msg_id, "✅ YouTube'da yayında")
    telegram.send_text("✅ Yayında: " + item["title"] + "".join(f"\n{u}" for u in urls.values() if u), msg_id)
    state.remove_pending(key)
    state.add_history({"key": key, "title": item["title"], "status": "published", "urls": urls, "date": state.now()})
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    st = state.load()
    telegram.set_chat(st.get("chat_id"))
    manual = os.environ.get("MUSICAI_PUBLISH", "").strip()
    if manual:  # GitHub'dan elle: "son" = en yeni bekleyen şarkı, ya da şarkı anahtarı
        pend = state.pending()
        key = sorted(pend)[-1] if manual == "son" and pend else manual
        log.info("Elle yayın: %s -> %s", key, "tamam" if handle("pub", key, None, None) else "olmadı")
    if not telegram.enabled():
        log.info("Telegram kapalı")
        return
    info = telegram.webhook_info()
    log.info("Telegram: bekleyen güncelleme=%s, webhook=%s, son hata=%s", info.get("pending_update_count"),
             "VAR" if info.get("url") else "yok", info.get("last_error_message"))
    if info.get("url"):
        log.error("Bu bota bir webhook bağlı (%s); getUpdates çalışmaz. Webhook başka bir sisteme ait olabilir.",
                  info["url"].split("/")[2] if "//" in info["url"] else "?")
    updates = telegram.get_updates(st.get("tg_offset"))
    if not updates and st.get("tg_offset") and info.get("pending_update_count"):
        log.warning("Kayıtlı offset bekleyen güncellemeleri gizliyor; offset sıfırlanıyor")
        updates = telegram.get_updates(None)
    log.info("Gelen güncelleme: %d (%s)", len(updates),
             ", ".join(sorted({k for u in updates for k in u if k != "update_id"})) or "-")
    offset, done = st.get("tg_offset"), 0
    for u in updates:
        offset = u["update_id"] + 1
        cb = u.get("callback_query")
        if not cb or ":" not in cb.get("data", ""):
            if cb:
                telegram.answer_callback(cb["id"], "👍")
            continue
        action, key = cb["data"].split(":", 1)
        if handle(action, key, cb.get("message", {}).get("message_id"), cb["id"]):
            done += 1
    if offset != st.get("tg_offset"):
        st = state.load()
        st["tg_offset"] = offset
        state.save(st)
    log.info("%d buton işlendi", done)


if __name__ == "__main__":
    main()
