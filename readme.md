# crawler

A single-site **reconnaissance spider** built on [Scrapy](https://scrapy.org).

Point it at a URL and it walks the site (staying on the same host — ports
included), then dumps everything it finds into one JSON file: emails, links,
external documents, JavaScript files, form field names, images, video/audio
sources and HTML comments.

## Requirements

- Python 3.8+
- [Scrapy](https://scrapy.org)

```bash
pip install scrapy
# or:
pip install -r requirements.txt
```

**On Kali / Debian** (Python is externally managed — a plain `pip install`
raises `externally-managed-environment`), use the packaged Scrapy instead:

```bash
sudo apt install python3-scrapy      # system-wide, no venv needed
```

Or isolate it in a virtual environment:

```bash
python3 -m venv ~/.venvs/crawler
source ~/.venvs/crawler/bin/activate
pip install scrapy
```

## Usage

```bash
python crawler.py https://example.com
```

Options:

| Flag | Description | Default |
| :--- | :--- | :--- |
| `start_url` | URL to start crawling (positional). `http://` is added if the scheme is omitted. | — |
| `-o`, `--output` | Output JSON file. | `results.json` |

Examples:

```bash
python crawler.py https://example.com
python crawler.py example.com -o site.json
```

## Output

The JSON groups findings by type — each key holds a de-duplicated, sorted array:

```json
{
    "emails":         ["info@example.com"],
    "links":          ["https://example.com/about", "https://twitter.com/..."],
    "external_files": ["https://example.com/prospectus.pdf"],
    "js_files":       ["https://example.com/app.js"],
    "form_fields":    ["username", "password"],
    "images":         ["https://example.com/logo.png"],
    "videos":         ["https://example.com/intro.mp4"],
    "audio":          ["https://example.com/theme.mp3"],
    "comments":       ["TODO: remove debug endpoint"]
}
```

| Key | What it collects |
| :--- | :--- |
| `emails` | Email addresses found anywhere in the page text |
| `links` | Every `<a href>` (on-site and off-site); on-site links are also crawled |
| `external_files` | Linked documents (`.css`, `.pdf`, `.doc(x)`, `.xls(x)`) and any non-text response reached |
| `js_files` | Script URLs (`<script src>`) |
| `form_fields` | Names of every `<input>` / `<textarea>` / `<select>` |
| `images` | Image URLs (`<img src>`) |
| `videos` | `<video>` and child `<source>` URLs |
| `audio` | `<audio>` and child `<source>` URLs |
| `comments` | HTML comments (`<!-- ... -->`), markers stripped |

## How it works

- Built on Scrapy, so you get concurrency, retries, redirects and a real
  scheduler for free.
- A small `SameSiteOffsiteMiddleware` keeps the crawl on the start host and,
  because it matches on hostname only, works for `host:port` targets too.
- Each response is parsed by focused helpers (`_grab_intel`, `_grab_assets`,
  `_grab_forms`, `_grab_comments`, `_grab_links`); on-site `<a>` links are
  followed recursively until the site is exhausted.
- Results accumulate in sets (auto-deduplicated) and are written out as JSON
  when the spider closes.

## Notes

- Stays on the start URL's **host**; off-site links are recorded under `links`
  but not crawled.
- Non-text responses (PDFs, images fetched directly, etc.) are recorded under
  `external_files` rather than parsed.
- Scrapy de-duplicates requests, so each page is fetched once.

## Educational use / authorization

For learning and for use against sites you own or are explicitly authorized to
test. Crawling generates real traffic — have permission first, and respect the
target's `robots.txt` and terms of service.

## License

MIT
