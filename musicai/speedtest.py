"""ACE-Step hız ve Türkçe vokal testi: kısa bir deneme şarkısı üretir, süreyi ölçer."""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from . import music, telegram

SONG = {
    "title": "Deneme Turu",
    "vocal": "female",
    "caption": ("bright Turkish pop, acoustic guitar strums, warm bass, light claps and snaps, "
                "catchy sing-along chorus, clear female vocal, summer afternoon mood"),
    "bpm": 104,
    "keyscale": "G major",
    "lyrics": """[Verse 1]
Sabah erken kalktım bugün
Pencereden güneş güldü
Çayı koydum, şarkı açtım
Bütün yorgunluğum düştü

[Chorus]
Hadi gel, bu gün bizim
Kahkahamız rüzgâra karışsın
Hadi gel, bu gün bizim
Her adımda bir şarkı başlasın
""",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=45)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = Path("out/test")
    t0 = time.time()
    music._load()
    load_s = time.time() - t0
    t1 = time.time()
    wav = music.generate(SONG, out, seed=42, duration=a.seconds)
    gen_s = time.time() - t1
    mp3 = music.to_mp3(wav, out / "deneme.mp3")
    msg = (f"🧪 ACE-Step CPU testi: {a.seconds:.0f} sn şarkı\n"
           f"Model yükleme: {load_s / 60:.1f} dk · Üretim: {gen_s / 60:.1f} dk\n"
           f"Tahmini 3 dk'lık şarkı: ~{gen_s * 180 / a.seconds / 60:.0f} dk")
    print(msg)
    if telegram.enabled():
        try:
            telegram.send_file("sendAudio", "audio", mp3, msg, mime="audio/mpeg",
                               extra={"title": "Deneme Turu", "performer": "MUSİCAİ test"})
        except Exception as e:
            print("Telegram'a gönderilemedi (şarkı Artifacts'ta):", e)


if __name__ == "__main__":
    main()
