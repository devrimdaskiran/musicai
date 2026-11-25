"""Günlük üretim: tarz -> sözler (kural denetimli) -> şarkı (ACE-Step) -> kapak -> videolar -> Telegram onayı.

Kullanım:
  python -m musicai.main                  # tam üretim
  python -m musicai.main --style phonk    # belirli tarz
  python -m musicai.main --song paket.json --fake-audio --dry   # yerel deneme (model ve Telegram yok)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import catchup, checks, cover, publish, state, telegram, trends, video, writer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
log = logging.getLogger("musicai")


def slug(s: str) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")
    return re.sub(r"[^a-z0-9]+", "-", s.translate(tr).lower()).strip("-")[:40]


def package_text(song: dict) -> str:
    """Bizim standart 5 bölümlük çıktı formatımız (Telegram'a dosya olarak da gider)."""
    return f"""🎵 {writer.full_title(song)}

1) KONSEPT VE TREND ANALİZİ
{song.get('concept', '')}

2) MÜZİK ÜRETİM PROMPTU (EN)
{song['caption']}
BPM: {song.get('bpm')} · Key: {song.get('keyscale', '')} · Vokal: {song.get('vocal')} · Süre: {song.get('duration')} sn

3) ŞARKI SÖZLERİ
{song['lyrics']}

4) KAPAK VE VİDEO BAŞLIĞI
{writer.full_title(song)}

5) YOUTUBE / TIKTOK / REELS AÇIKLAMA METNİ
{writer.description(song)}

— Hece dökümü —
{checks.syllable_report(song['lyrics'])}
"""


def fake_audio(path: Path, seconds: int) -> Path:
    """Model olmadan deneme: basit bir akor dizisi sentezler."""
    expr = "0.2*sin(2*PI*220*t)+0.15*sin(2*PI*277*t)*gt(mod(t\\,2)\\,1)+0.1*sin(2*PI*330*t)*(1+sin(t/4))"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"aevalsrc={expr}:s=44100:d={seconds}",
                    "-ac", "2", str(path)], check=True)
    return path


def run(args) -> dict:
    st = state.load()
    telegram.set_chat(st.get("chat_id"))
    if telegram.enabled() and not args.dry:
        try:
            st["chat_id"] = telegram.chat_id()
        except Exception as e:
            log.warning("%s", e)

    # 1) sözler
    if args.song:
        song = json.loads(Path(args.song).read_text(encoding="utf-8"))
        song.setdefault("style_label", "Test")
    else:
        song = writer.write_song(st, trends.fetch(), args.style or None)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    sid = f"{stamp}-{slug(song['title'])}"
    d = OUT / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "song.json").write_text(json.dumps(song, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "paket.txt").write_text(package_text(song), encoding="utf-8")
    log.info("Paket hazır: %s", writer.full_title(song))
    if not args.dry:
        telegram.send_text(f"🎼 Yeni şarkı yazıldı, müzik üretiliyor (CPU'da 15-40 dk sürebilir):\n{writer.full_title(song)}")

    # 2) müzik
    if args.fake_audio:
        wav = fake_audio(d / "song.wav", int(song.get("duration", 60)))
    else:
        from . import music
        wav = music.generate(song, d)
    from .music import to_mp3
    mp3 = to_mp3(wav, d / f"{slug(song['title'])}.mp3")

    # 3) kapak ve videolar
    cv = cover.make_cover(song, d / "cover.jpg", cover.seed_for(song["title"]))
    art = cv.with_name("cover_art.jpg")
    full = video.full_video(mp3, cv, art, song, d / "full.mp4")
    short = video.short_video(mp3, cv, art, song, d / "short.mp4")
    log.info("Videolar hazır: %s, %s", full.name, short.name)
    if args.dry:
        return {"dir": str(d), "song": song}

    # 4) yayın öncesi: dosyaları Zernio deposuna koy (onay anında hızlı yükleme için)
    key = sid
    item = {"key": key, "title": writer.full_title(song), "description": writer.description(song),
            "short_description": writer.description(song, short=True), "tags": song.get("hashtags", []),
            "date": state.now(), "style": song["style_label"]}
    if publish.enabled():
        try:
            item["full_url"] = publish.upload_file(full, "video/mp4")
            item["short_url"] = publish.upload_file(short, "video/mp4")
            item["thumb_url"] = publish.upload_file(cv, "image/jpeg")
        except Exception as e:
            log.error("Zernio deposuna yüklenemedi: %s", e)
            telegram.send_text(f"⚠️ Zernio deposuna yüklenemedi, otomatik yayın olmayacak: {e}")

    # 5) Telegram: kapak + tam şarkı + paket + butonlu Short önizleme
    auto = bool(item.get("full_url"))
    concept = song.get("concept", "")
    telegram.send_file("sendPhoto", "photo", cv, f"🎵 {item['title']}\n\n{concept}"[:1024], mime="image/jpeg")
    telegram.send_file("sendAudio", "audio", mp3, "🎧 Tam şarkı", mime="audio/mpeg",
                       extra={"title": song["title"], "performer": "MUSİCAİ"})
    telegram.send_file("sendDocument", "document", d / "paket.txt",
                       "📋 5 bölümlük paket: sözler, açıklama, hashtag'ler (TikTok/Reels için kopyala)", mime="text/plain")
    cap = (f"📱 Short / TikTok / Reels kesiti\n{item['title']}\n\n"
           + ("Beğendiysen ✅ Yayınla: tam şarkı + Short YouTube'a yüklenir (en geç 1 saat)."
              if auto else "Otomatik yükleme kapalı: videoları buradan indirip elle yükleyebilirsin."))
    sent = telegram.send_file("sendVideo", "video", short, cap, key=key if auto else None, mime="video/mp4",
                              extra={"supports_streaming": "true", "width": 1080, "height": 1920})
    if full.stat().st_size < 49 * 1024 * 1024:
        telegram.send_file("sendDocument", "document", full, "🖥️ Tam şarkı videosu (YouTube)", mime="video/mp4")
    if auto:
        item["message_id"] = sent.get("message_id")
        state.add_pending(key, item)

    # 6) hafıza
    state.add_song(sid, {k: song.get(k) for k in ("title", "style_id", "style_label", "vocal", "lyrics", "caption",
                                                 "bpm", "keyscale", "concept", "hook", "story", "hashtags")}
                   | {"id": sid, "date": state.now(), "full_title": item["title"]})
    st["recent_styles"] = (st.get("recent_styles", []) + [song["style_id"]])[-12:]
    st["last_vocal"] = song.get("vocal")
    state.pop_queue(song["style_id"])
    state.save(st)
    return {"dir": str(d), "song": song}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--style", default=os.environ.get("MUSICAI_STYLE", ""))
    ap.add_argument("--song", default="", help="Hazır paket JSON'u (söz yazımını atlar)")
    ap.add_argument("--fake-audio", action="store_true", help="Model yerine deneme sesi")
    ap.add_argument("--dry", action="store_true", help="Telegram/Zernio yok, hafızaya yazma")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    auto = os.environ.get("MUSICAI_AUTO") == "1"
    today = catchup.tr_now().strftime("%Y-%m-%d")
    if auto:
        # Zamanlanmış/yedek tetik: gün başarıyla tamamlandıysa ya da 3 deneme dolduysa atla
        st = state.load()
        tries = st.get("auto_tries", {})
        if not catchup.due(st=st):
            log.info("Şu an (%s) üretim zamanı değil, bugünkü şarkı tamam ya da deneme hakkı doldu; atlandı", today)
            return
        st["auto_tries"] = {today: tries.get(today, 0) + 1}
        state.save(st)
    try:
        run(a)
        if auto:
            st = state.load()
            st["last_auto_date"] = today
            state.save(st)
    except Exception as e:
        log.exception("Üretim başarısız")
        if not a.dry:
            telegram.send_text(f"⚠️ MUSİCAİ üretimi başarısız: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
