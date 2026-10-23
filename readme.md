# crawler

A tiny, **dependency-free** website crawler in a single Python file.

Point it at a URL and it walks the whole site (staying on the same domain),
then dumps everything it finds — pages, links, CSS, JS, images, forms, emails,
phone numbers and HTML comments — into one clean JSON file.

Standard library only. No `pip install`, nothing to set up.

## Requirements

- Python 3.7+

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
| `-H`, `--header` | Extra request header, **curl style** (`"Name: value"`). Repeatable. See below. | — |
| `-A`, `--user-agent` | User-Agent string (same as `-H "User-Agent: ..."`). | `Mozilla/5.0 (compatible; crawler/1.0)` |
| `-b`, `--cookie` | Cookie header value (same as `-H "Cookie: ..."`). String form only, no cookie-jar files. | — |
| `-k`, `--insecure` | Skip TLS certificate verification (like `curl -k`). | off |

Examples:

```bash
python crawler.py example.com                 # crawl, write example.com.json
python crawler.py http://example.com -p 100   # crawl up to 100 pages
python crawler.py example.com -o site.json    # custom output file
python crawler.py example.com -H "X-Forwarded-For: 127.0.0.1" -H "Authorization: Bearer eyJ..."
python crawler.py example.com -b "PHPSESSID=abc123; lang=en"   # crawl as a logged-in user
python crawler.py example.com -A "Mozilla/5.0 (X11; Linux x86_64) Firefox/128.0"
python crawler.py example.com -H @headers.txt  # one "Name: value" per line
```

### Headers (`-H`) — same rules as curl

`-H` takes exactly what `curl -H` takes, and can be repeated as often as you
like. The headers are sent with **every** request the crawler makes.

| Form | Effect | Example |
| :--- | :--- | :--- |
| `"Name: value"` | Set the header (replaces any existing one with that name, case-insensitive). | `-H "X-Forwarded-For: 127.0.0.1"` |
| `"Name;"` | Send the header with an **empty** value. | `-H "X-Custom;"` |
| `"Name:"` | **Remove** the header, including the default `User-Agent`. | `-H "User-Agent:"` |
| `"@file"` | Read headers from a file, one per line (each line follows the rules above). | `-H @burp-headers.txt` |

Later flags win: `-A foo -H "User-Agent: bar"` sends `bar`. Header names are
sent in `Title-Case` (`x-api-key` goes out as `X-Api-Key`), which is what
`urllib` does; HTTP header names are case-insensitive so servers don't care.

`Accept-Encoding` is always forced to `identity` (the crawler does not
decompress responses), so any `Accept-Encoding` you pass is overridden.

### Paste a Chrome "Copy as cURL" line

You can grab a request in Chrome DevTools (**Network → right-click → Copy →
Copy as cURL**) and run it through the crawler by just swapping `curl` for
`crawler`:

```bash
crawler 'http://app.local:5000/' \
  -H 'Accept: text/html,application/xhtml+xml' \
  -b 'pid=0c3b...; sid=ca9d...' \
  -H 'User-Agent: Mozilla/5.0 ...' \
  --compressed --insecure
```

`-H`, `-b`, `-A` and `-k`/`--insecure` are honoured. Other curl-only flags
(`--compressed`, `-L`/`--location`, `--data-raw`, `--http2`, …) are accepted
and ignored with a one-line note on stderr, so the paste runs instead of
erroring out.

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

## Output

The JSON is grouped by type — each category is its own key with an array of
results:

```json
{
  "tar_name": "example.com",
  "data": {
    "pages":    ["http://example.com/", "http://example.com/about"],
    "links":    ["http://example.com/contact", "https://twitter.com/..."],
    "css":      ["http://example.com/style.css"],
    "js":       ["http://example.com/app.js"],
    "images":   ["http://example.com/logo.png"],
    "forms":    [
      {
        "action": "http://example.com/login",
        "method": "post",
        "inputs": [
          {"name": "user", "type": "text"},
          {"name": "pass", "type": "password"}
        ]
      }
    ],
    "emails":   ["info@example.com"],
    "phones":   ["+1 555 123 4567"],
    "comments": ["<!-- TODO: remove debug endpoint -->"]
  }
}
```

| Key | What it collects |
| :--- | :--- |
| `pages` | HTML pages actually crawled |
| `links` | Every `<a href>` found (on-site and off-site) |
| `css` | Stylesheet URLs (`<link rel="stylesheet">`, `.css`) |
| `js` | Script URLs (`<script src>`) |
| `images` | Image URLs (`<img src>`) |
| `forms` | Forms with their `action`, `method`, and input fields |
| `emails` | Email addresses found in the HTML |
| `phones` | Phone-number-looking strings found in the HTML |
| `comments` | HTML comments (`<!-- ... -->`) |

## How it works

`crawler.py` uses only the Python standard library:

- `urllib` fetches pages (with a timeout and the headers built from
  `-H` / `-A` / `-b`, defaulting to just a User-Agent).
- `html.parser` extracts tags, attributes, forms and comments.
- `re` finds emails and phone numbers.
- A simple queue keeps the crawl on the target's domain and stops at
  `--max-pages`.

Results are de-duplicated and sorted before being written out.

## Notes

- Only crawls URLs on the **same domain** as the start URL.
- Only parses `text/html` responses; other content types are recorded as
  links/assets but not crawled into.
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
