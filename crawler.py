#!/usr/bin/env python3
"""
crawler - a tiny, dependency-free website crawler.

Usage:
    python crawler.py http://example.com
    python crawler.py http://example.com -p 100 -o out.json
    python crawler.py https://spa.example.com --render        # JS-rendered sites

By default it fetches raw HTML with the standard library (no deps). For
JavaScript-rendered sites (React/Vue/Angular SPAs, where the real <form>s,
<img>s and links are built in the browser and the served HTML is just an
empty <div id="root">), pass --render to drive a headless browser instead,
so the crawler parses the rendered DOM. --render needs Playwright:

    pip install playwright && playwright install chromium

Crawls one website (staying on its domain), then writes everything it finds
to a JSON file shaped like:

    {
      "tar_name": "example.com",
      "data": {
        "pages":          [...],   # HTML pages actually crawled
        "links":          [...],   # every <a href> (on- and off-site)
        "emails":         [...],
        "phones":         [...],
        "css":            [...],   # <link rel=stylesheet> / *.css
        "js_files":       [...],   # <script src>
        "external_files": [...],   # linked docs: pdf/doc(x)/xls(x) + non-text hits
        "form_fields":    [...],   # names of every input/textarea/select
        "images":         [...],   # <img src>
        "videos":         [...],   # <video>/<source> src
        "audio":          [...],   # <audio>/<source> src
        "comments":       [...],   # <!-- ... -->
        "forms":          [...]    # structured: action, method, inputs
      }
    }

Standard library only. No pip install needed (unless you opt into --render).
"""

import argparse
import json
import re
import sys
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

# --- patterns -------------------------------------------------------------
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-\s().]{7,}\d")
# linked documents worth pulling out separately (stops before any ?query/#frag)
DOC_EXT_RE = re.compile(r"\.(css|pdf|docx?|xlsx?)(?:[?#]|$)", re.I)
UA = "Mozilla/5.0 (compatible; crawler/1.0)"

# every bucket the crawler fills (sets, de-duplicated). "forms" is a list.
SET_KEYS = ("pages", "links", "emails", "phones", "css", "js_files",
            "external_files", "form_fields", "images", "videos", "audio",
            "comments")


class Extractor(HTMLParser):
    """Pulls links, assets, media, forms and comments out of one HTML page."""

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.links = set()
        self.css = set()
        self.js_files = set()
        self.external_files = set()
        self.form_fields = set()
        self.images = set()
        self.videos = set()
        self.audio = set()
        self.comments = set()
        self.forms = []
        self._form = None      # currently-open <form> dict, or None
        self._media = None     # "video" | "audio" | None — parent of a <source>

    def _abs(self, url):
        return urljoin(self.base, url)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        href = a.get("href")
        src = a.get("src")

        if tag == "a" and href:
            absu = self._abs(href)
            self.links.add(absu)
            if DOC_EXT_RE.search(href):
                self.external_files.add(absu)
        elif tag == "link" and href:
            rel = (a.get("rel") or "").lower()
            absu = self._abs(href)
            if "stylesheet" in rel or href.split("?")[0].lower().endswith(".css"):
                self.css.add(absu)
            elif DOC_EXT_RE.search(href):
                self.external_files.add(absu)
        elif tag == "script" and src:
            self.js_files.add(self._abs(src))
        elif tag == "img" and src:
            self.images.add(self._abs(src))
        elif tag == "video":
            self._media = "video"
            if src:
                self.videos.add(self._abs(src))
        elif tag == "audio":
            self._media = "audio"
            if src:
                self.audio.add(self._abs(src))
        elif tag == "source" and src:
            (self.audio if self._media == "audio" else self.videos).add(self._abs(src))
        elif tag == "form":
            self._form = {
                "action": self._abs(a.get("action", "")),
                "method": (a.get("method") or "get").lower(),
                "inputs": [],
            }
        elif tag in ("input", "textarea", "select"):
            name = a.get("name", "")
            if name:
                self.form_fields.add(name)
            if self._form is not None:
                self._form["inputs"].append({"name": name, "type": a.get("type", "text")})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in ("video", "audio"):   # self-closing media tag holds no <source>
            self._media = None

    def handle_endtag(self, tag):
        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None
        elif tag in ("video", "audio"):
            self._media = None

    def handle_comment(self, data):
        text = data.strip()
        if text:
            self.comments.add(text)


def fetch(url):
    """Return (html_text, content_type) or (None, content_type) on non-HTML/failure."""
    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=10) as resp:
            ctype = resp.headers.get_content_type()
            if ctype != "text/html":
                return None, ctype
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, "replace"), ctype
    except Exception as exc:  # noqa: BLE001 - keep the crawl going
        print(f"  ! skip {url} ({exc})", file=sys.stderr)
        return None, None


def make_renderer(wait_ms):
    """Return (get_html, close) backed by a headless Chromium via Playwright.

    get_html(url) navigates the browser to url, lets client-side JS run, and
    returns (rendered_dom, None) — or (None, None) on failure. One browser is
    launched and reused for the whole crawl. close() tears it down.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError:
        sys.exit(
            "error: --render needs Playwright. Install it with:\n"
            "    pip install playwright && playwright install chromium"
        )

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)

    def get_html(url):
        try:
            # 'load' (not 'networkidle') — widgets like reCAPTCHA keep the
            # network busy forever and would otherwise time out.
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_timeout(wait_ms)  # let the SPA paint into #root
            return page.content(), None
        except Exception as exc:  # noqa: BLE001 - keep the crawl going
            print(f"  ! skip {url} ({exc})", file=sys.stderr)
            return None, None

    def close():
        browser.close()
        pw.stop()

    return get_html, close


def crawl(start, max_pages, render=False, render_wait=2500):
    domain = urlparse(start).netloc
    seen, queue = set(), deque([start])
    data = {k: set() for k in SET_KEYS}
    forms = []

    if render:
        get_html, close = make_renderer(render_wait)
    else:
        get_html, close = fetch, (lambda: None)

    try:
        while queue and len(data["pages"]) < max_pages:
            url = queue.popleft()
            if url in seen:
                continue
            seen.add(url)

            html, ctype = get_html(url)
            if html is None:
                # a reachable but non-text response (pdf, zip, ...) is still an asset
                if ctype and not ctype.startswith("text"):
                    data["external_files"].add(url)
                continue
            print(f"[+] {url}")
            data["pages"].add(url)

            ext = Extractor(url)
            ext.feed(html)

            data["links"].update(ext.links)
            data["css"].update(ext.css)
            data["js_files"].update(ext.js_files)
            data["external_files"].update(ext.external_files)
            data["form_fields"].update(ext.form_fields)
            data["images"].update(ext.images)
            data["videos"].update(ext.videos)
            data["audio"].update(ext.audio)
            data["comments"].update(ext.comments)
            data["emails"].update(EMAIL_RE.findall(html))
            data["phones"].update(p.strip() for p in PHONE_RE.findall(html))
            forms.extend(ext.forms)

            # queue new, same-domain, http(s) links
            for link in ext.links:
                p = urlparse(link)
                if p.scheme in ("http", "https") and p.netloc == domain and link not in seen:
                    queue.append(link)
    finally:
        close()

    out = {k: sorted(v) for k, v in data.items()}
    out["forms"] = forms
    return {"tar_name": domain, "data": out}


def safe_name(name):
    """Make a netloc safe to use as a filename (e.g. host:port on Windows/HGFS)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def main():
    ap = argparse.ArgumentParser(prog="crawler", description="Tiny dependency-free web crawler.")
    ap.add_argument("url", help="start URL, e.g. http://example.com")
    ap.add_argument("-p", "--max-pages", type=int, default=50, help="max pages to crawl (default 50)")
    ap.add_argument("-o", "--output", help="output JSON file (default <tar_name>.json)")
    ap.add_argument("-r", "--render", action="store_true",
                    help="drive a headless browser so JS-rendered SPAs are parsed (needs Playwright)")
    ap.add_argument("--render-wait", type=int, default=2500, metavar="MS",
                    help="ms to wait after load for the SPA to paint (default 2500; --render only)")
    args = ap.parse_args()

    start = args.url if "://" in args.url else "http://" + args.url
    result = crawl(start, args.max_pages, render=args.render, render_wait=args.render_wait)

    out_file = args.output or safe_name(result["tar_name"]) + ".json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    d = result["data"]
    print(f"\n[done] {len(d['pages'])} pages -> {out_file}")
    print("  " + " | ".join(f"{k}:{len(v)}" for k, v in d.items()))


if __name__ == "__main__":
    main()
