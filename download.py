#!/usr/bin/env python3
import os
import re
import sys
import time
import argparse
from urllib.parse import urlparse, unquote

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("نصب requests لازم است: pip install requests")
    sys.exit(1)

# تلاش برای استفاده از curl_cffi در صورت نصب بودن
try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
    "Connection": "keep-alive",
}

def extract_real_url(html):
    """استخراج لینک واقعی از متا رفرش یا جاوااسکریپت"""
    # متا رفرش
    m = re.search(r'<meta[^>]+http-equiv=["\']refresh["\'][^>]+content=["\']\d+;\s*url=([^"\']+)', html, re.I)
    if m:
        return m.group(1).strip()
    # window.location
    m = re.search(r'(?:window\.location|location\.href)\s*=\s*["\']([^"\']+)', html, re.I)
    if m:
        return m.group(1).strip()
    # لینک مستقیم داخل تگ a با متن Download
    m = re.search(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>\s*(?:Download|دانلود)', html, re.I)
    if m:
        return m.group(1).strip()
    return None

def download_with_requests(url, output_dir):
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)

    resp = session.get(url, stream=True, timeout=60, allow_redirects=True)
    resp.raise_for_status()

    # اگر HTML بود، لینک واقعی را پیدا کن
    if "text/html" in resp.headers.get("Content-Type", ""):
        html = resp.text
        real_url = extract_real_url(html)
        if real_url:
            print(f"لینک واقعی پیدا شد: {real_url}")
            resp = session.get(real_url, stream=True, timeout=60, allow_redirects=True)
            resp.raise_for_status()
        else:
            raise RuntimeError("پاسخ HTML است اما لینک واقعی یافت نشد")

    # تعیین نام فایل
    filename = None
    cd = resp.headers.get("Content-Disposition")
    if cd:
        fname_match = re.findall(r'filename="?([^";]+)', cd)
        if fname_match:
            filename = fname_match[-1]
    if not filename:
        filename = os.path.basename(urlparse(resp.url).path)
    if not filename:
        filename = "download.file"
    filename = unquote(filename)

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    print(f"✅ دانلود شد: {filepath}")
    return filepath

def download_with_curl_cffi(url, output_dir):
    """نسخه پشتیبان با curl_cffi برای دور زدن محافظت‌های TLS"""
    if not HAS_CURL_CFFI:
        raise ImportError("curl_cffi نصب نیست")
    resp = curl_requests.get(url, headers=HEADERS, impersonate="chrome", timeout=60)
    resp.raise_for_status()

    if "text/html" in resp.headers.get("Content-Type", ""):
        html = resp.text
        real_url = extract_real_url(html)
        if real_url:
            resp = curl_requests.get(real_url, headers=HEADERS, impersonate="chrome", timeout=60)
            resp.raise_for_status()
        else:
            raise RuntimeError("پاسخ HTML است اما لینک واقعی یافت نشد")

    filename = None
    cd = resp.headers.get("Content-Disposition")
    if cd:
        fname_match = re.findall(r'filename="?([^";]+)', cd)
        if fname_match:
            filename = fname_match[-1]
    if not filename:
        filename = os.path.basename(urlparse(resp.url).path)
    if not filename:
        filename = "download.file"
    filename = unquote(filename)

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "wb") as f:
        f.write(resp.content)
    print(f"✅ دانلود شد (curl_cffi): {filepath}")
    return filepath

def download(url, output_dir):
    try:
        return download_with_requests(url, output_dir)
    except Exception as e:
        print(f"⚠️ خطا با requests: {e}")
        if HAS_CURL_CFFI:
            print("تلاش با curl_cffi...")
            try:
                return download_with_curl_cffi(url, output_dir)
            except Exception as e2:
                print(f"❌ خطا با curl_cffi هم: {e2}")
                raise
        else:
            raise

def main():
    parser = argparse.ArgumentParser(description="دانلود فایل از لیست لینک‌ها")
    parser.add_argument("links_file", help="فایل متنی شامل لینک‌ها (هر خط یک لینک)")
    parser.add_argument("output_dir", nargs="?", default="downloads", help="پوشه خروجی")
    args = parser.parse_args()

    with open(args.links_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("هیچ لینکی در فایل نیست")
        sys.exit(1)

    failed = []
    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] دانلود: {url}")
        try:
            download(url, args.output_dir)
        except Exception as e:
            print(f"❌ شکست: {e}")
            failed.append(url)

    if failed:
        print(f"\n❗ {len(failed)} لینک ناموفق بود:")
        for u in failed:
            print(f"  - {u}")
        sys.exit(1)
    else:
        print("\n🎉 همه فایل‌ها با موفقیت دانلود شدند")

if __name__ == "__main__":
    main()
