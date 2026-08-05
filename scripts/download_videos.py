#!/usr/bin/env python3
"""
دانلود موازی ویدیو از لینک‌های مختلف.
روش اول: yt-dlp (هزاران سایت را پشتیبانی می‌کند و مرتب آپدیت می‌شود)
روش دوم (fallback): استخراج عمومی لینک مستقیم mp4/m3u8 از HTML صفحه + ffmpeg
"""
import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

DOWNLOAD_DIR = "downloads"
DEFAULT_WORKERS = 4


def slugify(url: str) -> str:
    parsed = urlparse(url)
    base = re.sub(r"[^a-zA-Z0-9_-]+", "_", parsed.path.strip("/")) or "video"
    return f"{parsed.netloc.replace('.', '_')}_{base}"


def download_with_ytdlp(url: str, out_path: str) -> bool:
    """تلاش اول: yt-dlp"""
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--merge-output-format", "mp4",
        "-f", "bv*+ba/b",
        "-o", out_path,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[yt-dlp] {url} -> {result.stderr.strip()[-300:]}")
    return result.returncode == 0 and os.path.exists(out_path)


def download_generic(url: str, out_path: str) -> bool:
    """
    Fallback عمومی: صفحه HTML را می‌گیرد و به دنبال لینک مستقیم mp4/m3u8 می‌گردد.
    فقط برای سایت‌هایی کار می‌کند که ویدیو را بدون رمزگذاری/محافظت ویژه سرو می‌کنند.
    """
    import requests

    headers = {"User-Agent": "Mozilla/5.0", "Referer": url}
    try:
        resp = requests.get(url, headers=headers, timeout=25)
        resp.raise_for_status()
    except Exception as e:
        print(f"[generic] خطا در دریافت صفحه {url}: {e}")
        return False

    html = resp.text
    mp4_matches = re.findall(r"https?://[^\s\"'<>]+\.mp4[^\s\"'<>]*", html)
    m3u8_matches = re.findall(r"https?://[^\s\"'<>]+\.m3u8[^\s\"'<>]*", html)

    source_url = None
    if mp4_matches:
        source_url = mp4_matches[0]
    elif m3u8_matches:
        source_url = m3u8_matches[0]

    if not source_url:
        print(f"[generic] هیچ لینک ویدیوی مستقیمی در {url} پیدا نشد.")
        return False

    cmd = [
        "ffmpeg", "-y",
        "-headers", f"Referer: {url}\r\n",
        "-i", source_url,
        "-c", "copy",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ffmpeg] {url} -> {result.stderr.strip()[-300:]}")
    return result.returncode == 0 and os.path.exists(out_path)


def process_link(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    filename = slugify(url) + ".mp4"
    out_path = os.path.join(DOWNLOAD_DIR, filename)

    print(f"[>] شروع: {url}")
    ok = download_with_ytdlp(url, out_path)
    if not ok:
        print(f"[i] yt-dlp ناموفق بود؛ تلاش با روش عمومی برای {url}")
        ok = download_generic(url, out_path)

    if ok:
        print(f"[OK] {out_path}")
        return out_path
    print(f"[FAIL] {url}")
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--links-file", required=True)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    args = parser.parse_args()

    with open(args.links_file, "r", encoding="utf-8") as f:
        links = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]

    if not links:
        print("هیچ لینکی پیدا نشد.")
        sys.exit(0)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_link, u): u for u in links}
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())

    successful = [r for r in results if r]
    print(f"\n{len(successful)} از {len(links)} لینک با موفقیت دانلود شد.")
    if not successful:
        sys.exit(1)


if __name__ == "__main__":
    main()
