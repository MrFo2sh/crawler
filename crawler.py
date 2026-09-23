#!/usr/bin/env python3
"""
crawler - a tiny, dependency-free website crawler.

Usage:
    python crawler.py http://example.com
    python crawler.py http://example.com -p 100 -o out.json

Crawls one website (staying on its domain), then writes everything it finds
to a JSON file shaped like:

    {
      "tar_name": "example.com",
      "data": {
        "pages":    [...],
        "links":    [...],
        "css":      [...],
        "js":       [...],
        "images":   [...],
        "forms":    [...],
        "emails":   [...],
        "phones":   [...],
        "comments": [...]
      }
    }

Standard library only. No pip install needed.
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
UA = "Mozilla/5.0 (compatible; crawler/1.0)"


class Extractor(HTMLParser):
    """Pulls links, assets, forms and comments out of one HTML page."""

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.links, self.css, self.js, self.images = set(), set(), set(), set()
        self.comments = set()
        self.forms = []
        self._form = None

    def _abs(self, url):
        return urljoin(self.base, url)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.add(self._abs(a["href"]))
        elif tag == "link":
            href = a.get("href")
            rel = (a.get("rel") or "").lower()
            if href and ("stylesheet" in rel or href.lower().endswith(".css")):
                self.css.add(self._abs(href))
        elif tag == "script" and a.get("src"):
            self.js.add(self._abs(a["src"]))
        elif tag == "img" and a.get("src"):
            self.images.add(self._abs(a["src"]))
        elif tag == "form":
            self._form = {
                "action": self._abs(a.get("action", "")),
                "method": (a.get("method") or "get").lower(),
                "inputs": [],
            }
        elif tag in ("input", "textarea", "select") and self._form is not None:
            self._form["inputs"].append(
                {"name": a.get("name", ""), "type": a.get("type", "text")}
            )

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None

    def handle_comment(self, data):
        text = data.strip()
        if text:
            self.comments.add(text)


def fetch(url):
    """Return (html_text, content_type) or (None, None) on any failure."""
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


def crawl(start, max_pages):
    domain = urlparse(start).netloc
    seen, queue = set(), deque([start])
    data = {k: set() for k in ("pages", "links", "css", "js", "images",
                               "emails", "phones", "comments")}
    forms = []

    while queue and len(data["pages"]) < max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        html, _ = fetch(url)
        if html is None:
            continue
        print(f"[+] {url}")
        data["pages"].add(url)

        ext = Extractor(url)
        ext.feed(html)

        data["links"].update(ext.links)
        data["css"].update(ext.css)
        data["js"].update(ext.js)
        data["images"].update(ext.images)
        data["comments"].update(ext.comments)
        data["emails"].update(EMAIL_RE.findall(html))
        data["phones"].update(p.strip() for p in PHONE_RE.findall(html))
        forms.extend(ext.forms)

        # queue new, same-domain, http(s) links
        for link in ext.links:
            p = urlparse(link)
            if p.scheme in ("http", "https") and p.netloc == domain and link not in seen:
                queue.append(link)

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
    args = ap.parse_args()

    start = args.url if "://" in args.url else "http://" + args.url
    result = crawl(start, args.max_pages)

    out_file = args.output or safe_name(result["tar_name"]) + ".json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    d = result["data"]
    print(f"\n[done] {len(d['pages'])} pages -> {out_file}")
    print("  " + " | ".join(f"{k}:{len(v)}" for k, v in d.items()))


if __name__ == "__main__":
    main()
