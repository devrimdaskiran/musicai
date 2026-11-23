"""Videolar (ffmpeg):

- full_video : 1920x1080 tam şarkı. Bulanık arka plan + kapak + başlık + sese göre oynayan dalga.
- short_video: 1080x1920, şarkının en enerjik 40 saniyesi (genelde nakarat) -> Shorts / TikTok / Reels.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .cover import BOLD, MED, _fit, _wrap

log = logging.getLogger(__name__)


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg hatası: {r.stderr[-800:]}")


def duration(audio: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def best_window(audio: Path, length: float = 40.0) -> float:
    """En yüksek ortalama enerjili `length` saniyelik bölümün başlangıcı (baştaki/sondaki %10 hariç)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    sec = len(x) // 8000
    if sec <= length + 4:
        return 0.0
    rms = np.sqrt(np.array([np.mean(x[i * 8000:(i + 1) * 8000] ** 2) for i in range(sec)]) + 1e-9)
    L = int(length)
    lo, hi = int(sec * 0.10), max(int(sec * 0.10) + 1, int(sec * 0.92) - L)
    sums = [rms[s:s + L].mean() for s in range(lo, hi)]
    return float(lo + int(np.argmax(sums)))


def _bg(art: Image.Image, size: tuple[int, int]) -> Image.Image:
    W, H = size
    s = max(W / art.width, H / art.height)
    bg = art.resize((int(art.width * s) + 2, int(art.height * s) + 2), Image.LANCZOS)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    return ImageEnhance.Brightness(bg).enhance(0.45)


def _rounded(img: Image.Image, r: int = 36) -> tuple[Image.Image, Image.Image]:
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, *img.size), r, fill=255)
    return img, m


def frame_full(cover: Path, art: Path, song: dict, out: Path) -> Path:
    W, H = 1920, 1080
    img = _bg(Image.open(art).convert("RGB"), (W, H))
    c = Image.open(cover).convert("RGB").resize((760, 760), Image.LANCZOS)
    c, m = _rounded(c)
    img.paste(c, (140, 120), m)
    d = ImageDraw.Draw(img)
    x0, maxw = 980, W - 980 - 100
    lines, f = _wrap(d, song["title"], BOLD, maxw, 120)
    y = 250
    for ln in lines:
        d.text((x0, y), ln, font=f, fill="white")
        y += f.size * 1.1
    fs = _fit(d, f"{song['style_label']} [AI Generated]", MED, maxw, 48, 28)
    d.text((x0, y + 20), f"{song['style_label']} [AI Generated]", font=fs, fill=(255, 214, 90))
    d.text((x0, y + 20 + fs.size + 40), "MUSİCAİ", font=ImageFont.truetype(BOLD, 40), fill=(255, 255, 255))
    img.save(out)
    return out


def frame_short(cover: Path, art: Path, song: dict, out: Path) -> Path:
    W, H = 1080, 1920
    img = _bg(Image.open(art).convert("RGB"), (W, H))
    c = Image.open(cover).convert("RGB").resize((900, 900), Image.LANCZOS)
    c, m = _rounded(c, 44)
    img.paste(c, (90, 420), m)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(BOLD, 44)
    t = "MUSİCAİ"
    d.text(((W - d.textlength(t, font=f)) / 2, 250), t, font=f, fill="white")
    tip = "Tam şarkı kanalda"
    ft = ImageFont.truetype(MED, 40)
    d.text(((W - d.textlength(tip, font=ft)) / 2, 1560), tip, font=ft, fill=(255, 214, 90))
    img.save(out)
    return out


def full_video(audio: Path, cover: Path, art: Path, song: dict, out: Path) -> Path:
    frame = frame_full(cover, art, song, out.with_suffix(".frame.png"))
    fc = ("[1:a]showwaves=s=760x150:mode=cline:rate=30:colors=0xFFFFFF:scale=sqrt:draw=full,format=rgba,colorchannelmixer=aa=0.9[w];"
          "[0:v][w]overlay=980:760:format=auto,format=yuv420p[v]")
    _run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", str(frame), "-i", str(audio),
          "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
          "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", str(out)])
    return out


def short_video(audio: Path, cover: Path, art: Path, song: dict, out: Path, length: float = 40.0) -> Path:
    start = best_window(audio, length)
    frame = frame_short(cover, art, song, out.with_suffix(".frame.png"))
    fc = (f"[1:a]atrim=start={start}:duration={length},asetpts=PTS-STARTPTS,"
          f"afade=t=in:d=0.6,afade=t=out:st={length - 1.5}:d=1.5,asplit[a1][a2];"
          "[a1]showwaves=s=900x170:mode=cline:rate=30:colors=0xFFFFFF:scale=sqrt:draw=full,format=rgba,colorchannelmixer=aa=0.9[w];"
          "[0:v][w]overlay=90:1360:format=auto,format=yuv420p[v]")
    _run(["ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-i", str(frame), "-i", str(audio),
          "-filter_complex", fc, "-map", "[v]", "-map", "[a2]", "-t", str(length), "-c:v", "libx264", "-preset",
          "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    log.info("Short kesiti: %.0f. saniyeden itibaren %.0f sn", start, length)
    return out
