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

Examples:

```bash
python crawler.py example.com                 # crawl, write example.com.json
python crawler.py http://example.com -p 100   # crawl up to 100 pages
python crawler.py example.com -o site.json    # custom output file
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

- `urllib` fetches pages (with a timeout and a User-Agent).
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
