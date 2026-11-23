"""Kapak: görseli Pollinations (ücretsiz) çizer, başlığı kod basar.

Kapaktaki yazı writer.full_title() ile aynı kaynaktan gelir: üstte şarkı adı, altında
"<Tarz> [AI Generated]". Böylece kapak, YouTube başlığı ve Shorts başlığı asla çelişmez.
Pollinations cevap vermezse tarzın renklerinden kodla bir kapak üretilir.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import random
import re
import time
import urllib.parse
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
BOLD = str(ROOT / "assets/fonts/Poppins-Bold.ttf")
MED = str(ROOT / "assets/fonts/Poppins-Medium.ttf")
STYLE = ("album cover art, cinematic, highly detailed, striking composition, rich colors, "
         "absolutely no text, no letters, no words, no logos, no watermark")


def fetch_art(prompt: str, seed: int, size: int = 1024) -> Image.Image | None:
    if os.environ.get("MUSICAI_NO_ART"):
        return None
    q =urllib.parse.quote(f"{prompt}, {STYLE}")
    token = re.sub(r"\s+", "", os.environ.get("POLLINATIONS_TOKEN", ""))
    params = {"width": size, "height": size, "seed": seed, "nologo": "true", "model": "flux", "safe": "true"}
    routes = []
    if token:
        routes.append(("https://gen.pollinations.ai/image/" + q, {"Authorization": f"Bearer {token}"}))
    routes.append(("https://image.pollinations.ai/prompt/" + q, {}))
    for url, headers in routes:
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=180)
                if r.ok and r.headers.get("content-type", "").startswith("image"):
                    img = Image.open(io.BytesIO(r.content)).convert("RGB")
                    w, h = img.size  # köşe filigranı olasılığına karşı hafif kırp
                    return img.crop((int(w * .04), int(h * .04), int(w * .96), int(h * .96))).resize((size, size))
                log.warning("Pollinations %s: %s", r.status_code, r.text[:120])
                if r.status_code in (401, 402, 403) and headers:
                    break
            except Exception as e:
                log.warning("Pollinations hatası: %s", e)
            time.sleep(20 * (attempt + 1))
    return None


def fallback_art(seed: int, size: int = 1024) -> Image.Image:
    rnd = random.Random(seed)
    c1 = tuple(rnd.randint(20, 120) for _ in range(3))
    c2 = tuple(rnd.randint(120, 255) for _ in range(3))
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
    d = ImageDraw.Draw(img)
    for _ in range(14):
        r = rnd.randint(60, 300)
        x, y = rnd.randint(0, size), rnd.randint(0, size)
        d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255), width=rnd.randint(2, 6))
    return img.filter(ImageFilter.GaussianBlur(2))


def _fit(draw: ImageDraw.ImageDraw, text: str, font_path: str, max_w: int, start: int, min_size: int = 40):
    size = start
    while size > min_size:
        f = ImageFont.truetype(font_path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return ImageFont.truetype(font_path, min_size)


def _wrap(draw, text: str, font_path: str, max_w: int, start: int) -> tuple[list[str], ImageFont.FreeTypeFont]:
    """Başlığı en fazla 2 satıra böler, sığacak en büyük puntoyu seçer."""
    f = _fit(draw, text, font_path, max_w, start, min_size=72)
    if draw.textlength(text, font=f) <= max_w or " " not in text:
        return [text], f
    w = text.split()
    best = min(range(1, len(w)), key=lambda i: abs(len(" ".join(w[:i])) - len(" ".join(w[i:]))))
    lines = [" ".join(w[:best]), " ".join(w[best:])]
    f = _fit(draw, max(lines, key=len), font_path, max_w, start)
    return lines, f


def make_cover(song: dict, out: Path, seed: int) -> Path:
    """1080x1080 kapak (YouTube kapak görseli ve videoların temeli)."""
    art = fetch_art(song.get("cover_prompt") or song["caption"], seed) or fallback_art(seed)
    S = 1080
    img = art.resize((S, S), Image.LANCZOS)
    # alt kısma okunurluk için koyu geçiş
    shade = Image.new("L", (1, S))
    for y in range(S):
        shade.putpixel((0, y), int(max(0, (y - S * 0.52) / (S * 0.48)) * 215))
    black = Image.new("RGB", (S, S), (0, 0, 0))
    img = Image.composite(black, img, shade.resize((S, S)))
    d = ImageDraw.Draw(img)
    lines, f = _wrap(d, song["title"], BOLD, S - 140, 150)
    sub = f"{song['style_label']} [AI Generated]"
    fs = _fit(d, sub, MED, S - 160, 46, 30)
    lh = f.size * 1.08
    y = S - 90 - fs.size - 18 - lh * len(lines)
    for ln in lines:
        w = d.textlength(ln, font=f)
        d.text(((S - w) / 2, y), ln, font=f, fill="white", stroke_width=3, stroke_fill=(0, 0, 0))
        y += lh
    w = d.textlength(sub, font=fs)
    d.text(((S - w) / 2, y + 18), sub, font=fs, fill=(255, 214, 90), stroke_width=2, stroke_fill=(0, 0, 0))
    brand = ImageFont.truetype(BOLD, 34)
    d.text((44, 36), "MUSİCAİ", font=brand, fill="white", stroke_width=2, stroke_fill=(0, 0, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)
    art.save(out.with_name(out.stem + "_art.jpg"), quality=95)  # yazısız hali videolarda arka plan için
    return out


def seed_for(title: str) -> int:
    return int(hashlib.sha1(title.encode()).hexdigest()[:6], 16)
