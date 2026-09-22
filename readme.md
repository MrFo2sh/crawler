# crawler

A tiny, **dependency-free** website crawler in a single Python file.

Point it at a URL and it walks the whole site (staying on the same domain),
then dumps everything it finds — pages, links, CSS, JS, external files, form
fields, images, video/audio, emails, phone numbers, HTML comments and full
form structures — into one clean JSON file.

Standard library only. No `pip install`, nothing to set up.

> Same recon surface as HTB's Scrapy-based `ReconSpider`, but with **no
> dependencies**. Scrapy, like this tool, only sees the server's raw HTML — so
> for JavaScript-rendered SPAs use the optional [`--render`](#javascript-rendered-sites--render)
> mode, which actually goes further than a plain Scrapy crawl.

## Requirements

- Python 3.7+
- *(optional)* [Playwright](https://playwright.dev/python/) — only for `--render`

## Usage

```bash
python crawler.py http://example.com
```

Options:

| Flag | Description | Default |
| :--- | :--- | :--- |
| `url` | Start URL (positional). `http://` is added if you omit the scheme. | — |
| `-p`, `--max-pages` | Maximum number of pages to crawl. | `50` |
| `-o`, `--output` | Output JSON file. | `<tar_name>.json` |
| `-r`, `--render` | Render JavaScript with a headless browser (needs Playwright). | off |
| `--render-wait` | Milliseconds to wait after load for the SPA to paint (`--render` only). | `2500` |

Examples:

```bash
python crawler.py example.com                 # crawl, write example.com.json
python crawler.py http://example.com -p 100   # crawl up to 100 pages
python crawler.py example.com -o site.json    # custom output file
python crawler.py https://spa.example.com -r  # render JS before parsing
```

### Type `crawler http://...` instead of `python crawler.py`

**Linux / macOS**

```bash
chmod +x crawler.py
alias crawler='python3 /full/path/to/crawler.py'
crawler http://example.com
```

**Windows (PowerShell)**

```powershell
function crawler { python C:\full\path\to\crawler.py @args }
crawler http://example.com
```

## JavaScript-rendered sites (`--render`)

Modern sites built with React / Vue / Angular ship an almost-empty HTML shell
(`<div id="root"></div>`) and build the real page — forms, images, links — in
the browser with JavaScript. A plain HTTP fetch (this tool's default, and what
Scrapy does too) only sees that empty shell, so those runs come back with
`forms:0 images:0 links:0`.

`--render` drives a real headless Chromium via Playwright: it loads the page,
lets the JavaScript run, then parses the **rendered DOM**. Install it once:

```bash
pip install playwright && playwright install chromium
```

On Kali / other externally-managed Python (PEP 668), use a venv:

```bash
python3 -m venv ~/.venvs/crawler
source ~/.venvs/crawler/bin/activate
pip install playwright && playwright install chromium
python3 crawler.py https://spa.example.com --render
```

Rendering costs a browser and a few seconds per page, so it stays **opt-in** —
plain sites don't need it. If a SPA still comes back empty, give it longer to
paint with `--render-wait 5000`.

## Output

The JSON is grouped by type — each category is its own key with an array of
results:

```json
{
  "tar_name": "example.com",
  "data": {
    "pages":          ["http://example.com/", "http://example.com/about"],
    "links":          ["http://example.com/contact", "https://twitter.com/..."],
    "emails":         ["info@example.com"],
    "phones":         ["+1 555 123 4567"],
    "css":            ["http://example.com/style.css"],
    "js_files":       ["http://example.com/app.js"],
    "external_files": ["http://example.com/report.pdf"],
    "form_fields":    ["user", "pass"],
    "images":         ["http://example.com/logo.png"],
    "videos":         ["http://example.com/intro.mp4"],
    "audio":          ["http://example.com/theme.mp3"],
    "comments":       ["<!-- TODO: remove debug endpoint -->"],
    "forms":          [
      {
        "action": "http://example.com/login",
        "method": "post",
        "inputs": [
          {"name": "user", "type": "text"},
          {"name": "pass", "type": "password"}
        ]
      }
    ]
  }
}
```

| Key | What it collects |
| :--- | :--- |
| `pages` | HTML pages actually crawled |
| `links` | Every `<a href>` found (on-site and off-site) |
| `emails` | Email addresses found in the HTML |
| `phones` | Phone-number-looking strings found in the HTML |
| `css` | Stylesheet URLs (`<link rel="stylesheet">`, `.css`) |
| `js_files` | Script URLs (`<script src>`) |
| `external_files` | Linked documents (`.pdf`, `.doc(x)`, `.xls(x)`) and any non-text response reached |
| `form_fields` | Names of every `<input>` / `<textarea>` / `<select>` |
| `images` | Image URLs (`<img src>`) |
| `videos` | Video URLs (`<video>` / child `<source>`) |
| `audio` | Audio URLs (`<audio>` / child `<source>`) |
| `comments` | HTML comments (`<!-- ... -->`) |
| `forms` | Full forms with their `action`, `method`, and typed input fields |

## How it works

`crawler.py` uses only the Python standard library:

- `urllib` fetches pages (with a timeout and a User-Agent).
- `html.parser` extracts tags, attributes, media, forms and comments.
- `re` finds emails, phone numbers and document links.
- A simple queue keeps the crawl on the target's domain and stops at
  `--max-pages`.

With `--render`, the fetch step is swapped for a headless Chromium (Playwright)
that returns the rendered DOM; the same parser then runs over it.

Results are de-duplicated and sorted before being written out.

## Notes

- Only crawls URLs on the **same domain** as the start URL.
- Only parses `text/html` responses; other content types are recorded under
  `external_files` but not crawled into.
- Failed requests are skipped so one bad URL never stops the run.
- Illegal filename characters in the target (e.g. the `:` in `host:port`) are
  replaced with `_` in the default output filename; `tar_name` inside the JSON
  keeps the real value.

## Educational use / authorization

This tool is for learning and for use against sites you own or are explicitly
authorized to test. Crawling generates real traffic — always have permission
first, and respect the target's `robots.txt` and terms of service.

## License

MIT
