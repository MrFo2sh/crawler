#!/usr/bin/env python3
"""
crawler.py - a single-site reconnaissance spider built on Scrapy.

Give it a start URL and it walks the site (staying on the same host, ports
included), collecting the intel a page exposes:

    emails . links . external files (css/pdf/doc/xls) . js files .
    form field names . images . video sources . audio sources . html comments

Everything is de-duplicated and written to one JSON file.

Only dependency: Scrapy.

    pip install scrapy
    python crawler.py https://example.com
    python crawler.py https://example.com -o site.json

Author:  Mohamed Fouad (MrFo2sh)
License: MIT
"""

import argparse
import json
import re
from urllib.parse import urlparse

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.downloadermiddlewares.offsite import OffsiteMiddleware

# an email anywhere in the page body
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# linked documents we record but never crawl into
DOCUMENT_RE = re.compile(r"\.(?:css|pdf|docx?|xlsx?)(?:[?#]|$)", re.IGNORECASE)
# href schemes/anchors that are never crawlable pages
SKIP_LINK_PREFIXES = ("mailto:", "tel:", "javascript:", "#")


def hostname(url):
    """Host without the port  (app.example.com:8080 -> app.example.com)."""
    return urlparse(url).netloc.split(":")[0]


class SameSiteOffsiteMiddleware(OffsiteMiddleware):
    """Offsite filter that compares hostnames only, so a target served on a
    non-default port (e.g. an app on :8080) is still treated as on-site."""

    def should_follow(self, request, spider):
        regex = getattr(self, "host_regex", None)
        if not regex:                      # no allowed_domains -> allow all
            return True
        return bool(regex.search(hostname(request.url)))


class SiteReconSpider(scrapy.Spider):
    """Crawl one site and inventory what it links to and loads."""

    name = "site_recon"

    # bucket -> the selector(s) whose extracted URLs are absolutised into it
    ASSET_SELECTORS = {
        "js_files": ("script::attr(src)",),
        "images": ("img::attr(src)",),
        "videos": ("video::attr(src)", "video source::attr(src)"),
        "audio": ("audio::attr(src)", "audio source::attr(src)"),
    }
    RESULT_KEYS = (
        "emails", "links", "external_files", "js_files", "form_fields",
        "images", "videos", "audio", "comments",
    )

    def __init__(self, start_url, output="results.json", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [start_url]
        self.allowed_domains = [hostname(start_url)]
        self.output = output
        self.seen = set()
        self.results = {key: set() for key in self.RESULT_KEYS}

    # -- per-response extraction -------------------------------------------

    def parse(self, response):
        self.seen.add(response.url)

        content_type = response.headers.get("Content-Type", b"").decode("latin-1", "ignore")
        if "text" not in content_type:
            # a binary / document response: record the URL and stop here
            self.results["external_files"].add(response.url)
            return

        self._grab_intel(response)
        self._grab_assets(response)
        self._grab_forms(response)
        self._grab_comments(response)
        yield from self._grab_links(response)

    def _grab_intel(self, response):
        self.results["emails"].update(EMAIL_RE.findall(response.text))
        for href in response.css("a::attr(href), link::attr(href)").getall():
            if DOCUMENT_RE.search(href):
                self.results["external_files"].add(response.urljoin(href))

    def _grab_assets(self, response):
        for bucket, selectors in self.ASSET_SELECTORS.items():
            for selector in selectors:
                for url in response.css(selector).getall():
                    self.results[bucket].add(response.urljoin(url))

    def _grab_forms(self, response):
        names = response.css(
            "input::attr(name), textarea::attr(name), select::attr(name)"
        ).getall()
        self.results["form_fields"].update(name for name in names if name)

    def _grab_comments(self, response):
        for raw in response.xpath("//comment()").getall():
            text = raw.strip("<!->").strip()
            if text:
                self.results["comments"].add(text)

    def _grab_links(self, response):
        here = hostname(response.url)
        for href in response.css("a::attr(href)").getall():
            if not href or href.startswith(SKIP_LINK_PREFIXES):
                continue
            url = response.urljoin(href)
            self.results["links"].add(url)
            if hostname(url) == here and url not in self.seen:
                self.seen.add(url)
                yield response.follow(url, callback=self.parse)

    # -- output ------------------------------------------------------------

    def closed(self, reason):
        report = {key: sorted(values) for key, values in self.results.items()}
        with open(self.output, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=4, ensure_ascii=False)
        summary = " | ".join(f"{k}:{len(v)}" for k, v in report.items())
        self.logger.info("saved %s  (%s)", self.output, summary)


def crawl(start_url, output):
    process = CrawlerProcess(settings={
        "LOG_LEVEL": "INFO",
        "DOWNLOADER_MIDDLEWARES": {
            # swap the built-in offsite filter for our port-aware subclass
            "scrapy.downloadermiddlewares.offsite.OffsiteMiddleware": None,
            "__main__.SameSiteOffsiteMiddleware": 50,
        },
    })
    process.crawl(SiteReconSpider, start_url=start_url, output=output)
    process.start()


def main():
    parser = argparse.ArgumentParser(prog="crawler", description="Single-site recon spider (Scrapy).")
    parser.add_argument("start_url", help="URL to start crawling, e.g. https://example.com")
    parser.add_argument("-o", "--output", default="results.json",
                        help="output JSON file (default results.json)")
    args = parser.parse_args()

    start = args.start_url if "://" in args.start_url else "http://" + args.start_url
    crawl(start, args.output)


if __name__ == "__main__":
    main()
