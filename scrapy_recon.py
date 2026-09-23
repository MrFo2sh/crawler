#!/usr/bin/env python3
"""
scrapy_recon.py - a Scrapy-based website reconnaissance crawler.

Walks a single site (same host, ports allowed) and inventories everything it
finds - pages, links, forms, assets, media, emails, phone numbers and HTML
comments - into one tidy JSON file.

For JavaScript-rendered sites (React / Vue / Angular single-page apps, whose
markup is built in the browser and never appears in the raw HTML) pass
--render: requests are then routed through a real headless browser via
scrapy-playwright, so the spider parses the rendered DOM.

    # static crawl (only needs scrapy)
    python scrapy_recon.py https://example.com

    # render JavaScript first (needs scrapy-playwright + a browser)
    python scrapy_recon.py https://spa.example.com --render

Author:  Mohamed Fouad (MrFo2sh)
License: MIT
"""

import argparse
import json
import re
import sys
from urllib.parse import urlparse

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.linkextractors import LinkExtractor

# scrapy-playwright is optional and only needed for --render.
try:
    from scrapy_playwright.page import PageMethod
except ImportError:  # pragma: no cover - optional dependency
    PageMethod = None

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-\s().]{7,}\d")
# linked documents we record but never crawl into
DOC_RE = re.compile(r"\.(css|pdf|docx?|xlsx?)(?:[?#]|$)", re.I)

# buckets the spider fills; each is a set, deduplicated, sorted on close
BUCKETS = ("pages", "links", "emails", "phones", "css", "js_files",
           "external_files", "form_fields", "images", "videos", "audio",
           "comments")


class ReconCrawler(scrapy.Spider):
    """Single-site recon spider. Stays on the start URL's host (port included)."""

    name = "recon"

    def __init__(self, url, max_pages=50, output=None, render=False,
                 render_wait=2500, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_url = url
        self.max_pages = int(max_pages)
        self.render = bool(render)
        self.render_wait = int(render_wait)
        self.target = urlparse(url).netloc            # host or host:port
        self.output = output or _safe_name(self.target) + ".json"

        self.seen = set()
        self.forms = []
        self.buckets = {k: set() for k in BUCKETS}
        # LinkExtractor ignores image/css/js/archive extensions by default,
        # so linked assets are never mistaken for crawlable pages.
        self._links = LinkExtractor()

    # -- request building ---------------------------------------------------

    async def start(self):
        # Scrapy >= 2.13 entry point
        yield self._request(self.start_url)

    def start_requests(self):
        # fallback for Scrapy < 2.13
        yield self._request(self.start_url)

    def _request(self, url):
        meta = {}
        if self.render:
            meta["playwright"] = True
            meta["playwright_page_methods"] = [
                PageMethod("wait_for_timeout", self.render_wait)
            ]
        return scrapy.Request(url, callback=self.parse, errback=self._drop, meta=meta)

    def _drop(self, failure):
        self.logger.debug("drop %r", failure.value)

    # -- helpers ------------------------------------------------------------

    def _on_site(self, url):
        return urlparse(url).netloc == self.target

    def _capped(self):
        return len(self.buckets["pages"]) >= self.max_pages

    def _harvest_forms(self, response):
        for form in response.css("form"):
            fields = []
            for field in form.css("input, textarea, select"):
                name = field.attrib.get("name", "")
                if name:
                    self.buckets["form_fields"].add(name)
                fields.append({"name": name, "type": field.attrib.get("type", "text")})
            self.forms.append({
                "action": response.urljoin(form.attrib.get("action", "")),
                "method": (form.attrib.get("method") or "get").lower(),
                "inputs": fields,
            })

    def _harvest_media(self, response):
        # attribute each <source> to its real <video>/<audio> parent
        for kind in ("video", "audio"):
            for media in response.css(kind):
                urls = media.css("::attr(src)").getall()
                urls += media.css("source::attr(src)").getall()
                self.buckets[kind + "s" if kind == "video" else kind].update(
                    response.urljoin(u) for u in urls
                )

    # -- main callback ------------------------------------------------------

    def parse(self, response):
        self.seen.add(response.url)

        ctype = response.headers.get("Content-Type", b"").decode("latin-1", "ignore")
        if not ctype.startswith("text"):
            self.buckets["external_files"].add(response.url)
            return

        self.buckets["pages"].add(response.url)
        b = self.buckets

        b["emails"].update(EMAIL_RE.findall(response.text))
        b["phones"].update(m.strip() for m in PHONE_RE.findall(response.text))
        b["js_files"].update(response.urljoin(u) for u in response.css("script::attr(src)").getall())
        b["images"].update(response.urljoin(u) for u in response.css("img::attr(src)").getall())
        b["comments"].update(
            c.strip("<!->").strip() for c in response.xpath("//comment()").getall() if c.strip("<!->").strip()
        )

        # stylesheets vs. linked documents
        for href in response.css("link::attr(href)").getall():
            rel = " ".join(response.css(f'link[href="{href}"]::attr(rel)').getall()).lower()
            if "stylesheet" in rel or href.split("?")[0].lower().endswith(".css"):
                b["css"].add(response.urljoin(href))
            elif DOC_RE.search(href):
                b["external_files"].add(response.urljoin(href))
        for href in response.css("a::attr(href)").getall():
            if DOC_RE.search(href):
                b["external_files"].add(response.urljoin(href))

        self._harvest_forms(response)
        self._harvest_media(response)

        # record and follow on-site page links (LinkExtractor already skips assets)
        for link in self._links.extract_links(response):
            b["links"].add(link.url)
            if not self._capped() and self._on_site(link.url) and link.url not in self.seen:
                self.seen.add(link.url)
                yield self._request(link.url)

    # -- teardown -----------------------------------------------------------

    def closed(self, reason):
        data = {k: sorted(v) for k, v in self.buckets.items()}
        data["forms"] = self.forms
        report = {"tar_name": self.target, "data": data}
        with open(self.output, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
        counts = " | ".join(f"{k}:{len(v)}" for k, v in data.items() if isinstance(v, list))
        self.logger.info("wrote %s  (%s)", self.output, counts)


def _safe_name(name):
    """Turn a netloc into a safe filename (e.g. the ':' in host:port)."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def build_settings(args):
    settings = {
        "LOG_LEVEL": "INFO",
        "ROBOTSTXT_OBEY": args.obey_robots,
        "USER_AGENT": args.user_agent,
        "DOWNLOAD_DELAY": args.delay,
        "CLOSESPIDER_PAGECOUNT": args.max_pages,
        # allowed_domains is intentionally unset so host:port targets aren't
        # dropped by the offsite middleware; on-site filtering is done in code.
    }
    if args.render:
        if PageMethod is None:
            sys.exit(
                "error: --render needs scrapy-playwright. Install it with:\n"
                "    pip install scrapy-playwright && playwright install chromium"
            )
        settings.update({
            "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            "DOWNLOAD_HANDLERS": {
                "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            },
            "PLAYWRIGHT_LAUNCH_OPTIONS": {"headless": True},
        })
    return settings


def main():
    ap = argparse.ArgumentParser(prog="scrapy_recon", description="Scrapy site recon crawler.")
    ap.add_argument("url", help="start URL, e.g. https://example.com")
    ap.add_argument("-p", "--max-pages", type=int, default=50, help="max pages to crawl (default 50)")
    ap.add_argument("-o", "--output", help="output JSON file (default <host>.json)")
    ap.add_argument("-r", "--render", action="store_true",
                    help="render JavaScript via scrapy-playwright (for SPAs)")
    ap.add_argument("--render-wait", type=int, default=2500, metavar="MS",
                    help="ms to wait for the SPA to paint (default 2500; --render only)")
    ap.add_argument("--delay", type=float, default=0.0, metavar="SEC",
                    help="delay between requests, for politeness (default 0)")
    ap.add_argument("--obey-robots", action="store_true", help="honour robots.txt")
    ap.add_argument("--user-agent", default="Mozilla/5.0 (compatible; recon-crawler/1.0)",
                    help="User-Agent header to send")
    args = ap.parse_args()

    if "://" not in args.url:
        args.url = "http://" + args.url

    process = CrawlerProcess(build_settings(args))
    process.crawl(ReconCrawler, url=args.url, max_pages=args.max_pages,
                  output=args.output, render=args.render, render_wait=args.render_wait)
    process.start()


if __name__ == "__main__":
    main()
