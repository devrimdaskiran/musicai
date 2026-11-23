"""Trend radarı (isteğe bağlı, ücretsiz): YOUTUBE_API_KEY varsa Türkiye'de son 10 günde en çok izlenen
müzik Shorts başlıklarını toplar. Söz yazarına sadece tema/duygu ilhamı olarak verilir, hiçbir şey kopyalanmaz.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger(__name__)
API = "https://www.googleapis.com/youtube/v3"
QUERIES = ["türkçe şarkı", "yeni şarkı", "akustik cover türkçe", "türkçe rap", "duygusal şarkı edit"]


def fetch(limit: int = 20) -> list[str]:
    key = re.sub(r"\s+", "", os.environ.get("YOUTUBE_API_KEY", ""))
    if not key:
        return []
    after = (datetime.now(timezone.utc) - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen: dict[str, str] = {}
    for q in QUERIES:
        try:
            r = requests.get(f"{API}/search", params={
                "part": "snippet", "q": q, "type": "video", "videoDuration": "short", "order": "viewCount",
                "publishedAfter": after, "maxResults": 15, "regionCode": "TR", "relevanceLanguage": "tr",
                "videoCategoryId": "10", "key": key}, timeout=30)
            if not r.ok:
                log.warning("Trend araması %s: %s", r.status_code, r.text[:150])
                continue
            for it in r.json().get("items", []):
                seen.setdefault(it["id"]["videoId"], it["snippet"]["title"])
        except Exception as e:
            log.warning("Trend araması başarısız: %s", e)
    titles = list(seen.values())[:limit]
    log.info("Trend başlıkları: %d", len(titles))
    return titles
