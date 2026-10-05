"""Render the three submission documents to PDF and save local visual QA artifacts."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import markdown
import pypdfium2 as pdfium
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = (
    "Progress_Update.md",
    "POC_Technical_Report.md",
    "Team_Allocation.md",
)
CSS = """
* { box-sizing: border-box; }
body {
  margin: 0; color: #172633; background: white;
  font: 10.3pt/1.4 'Segoe UI', Calibri, Arial, sans-serif;
}
h1 { font-size: 21pt; line-height: 1.18; margin: 5mm 0 4mm; color: #173e52; }
h2 { font-size: 12.8pt; line-height: 1.25; margin: 5mm 0 2.5mm; color: #173e52; }
h1, h2, h3 { break-after: avoid; }
p { margin: 0 0 3mm; orphans: 3; widows: 3; }
a { color: #245970; text-decoration: underline; overflow-wrap: anywhere; }
strong { font-weight: 650; }
ul { padding-left: 5mm; margin: 2mm 0 4mm; }
li { margin: 1mm 0; }
code { font: 8.7pt/1.35 Consolas, monospace; overflow-wrap: anywhere; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f1f5f7;
      padding: 3mm; margin: 3mm 0; border-left: 0.8mm solid #7796a4;
      break-inside: avoid; }
pre code { font-size: 8.4pt; }
table { width: 100%; border-collapse: collapse; font-size: 8.8pt;
        line-height: 1.3; margin: 3mm 0 4mm; }
thead { display: table-header-group; }
th { background: #e6eff3; color: #173e52; font-weight: 650; text-align: left; }
td, th { border: 0.25mm solid #c9d5dc; padding: 2mm; vertical-align: top;
         overflow-wrap: anywhere; }
tr { break-inside: avoid; }
table code { font-size: 8.2pt; }
.masthead { color: #5c6c76; font-size: 8pt; letter-spacing: 0.25pt;
         border-bottom: 0.4mm solid #b9cbd3; padding-bottom: 2mm; }
body.allocation table th:first-child { width: 22%; }
body.allocation h2:last-of-type { break-before: page; }
"""


def printable_html(source: Path) -> str:
    contents = source.read_text(encoding="utf-8")
    body = markdown.markdown(contents, extensions=["tables", "fenced_code", "sane_lists"])

    def repository_link(match: re.Match) -> str:
        target = html.unescape(match.group(1))
        if urlsplit(target).scheme or target.startswith("#"):
            return match.group(0)
        destination = (source.parent / target).resolve().relative_to(ROOT).as_posix()
        return f'href="https://github.com/Muscar1a/gsm-ride-hailing/blob/main/{destination}"'

    body = re.sub(r'href="([^"]+)"', repository_link, body)
    title = contents.splitlines()[0].removeprefix("# ")
    kind = "allocation" if source.name == "Team_Allocation.md" else "report"
    return (
        '<!doctype html><html lang="vi"><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>"
        f'<body class="{kind}"><div class="masthead">GSM CAUSAL MARKETPLACE</div>'
        f"{body}</body></html>"
    )


def inspect_pdf(pdf_path: Path, qa_path: Path, source: Path) -> dict:
    pages = []
    texts = []
    with pdfium.PdfDocument(pdf_path) as document:
        for number in range(len(document)):
            page = document[number]
            text_page = page.get_textpage()
            text = text_page.get_text_range()
            if len(text.strip()) < 50:
                raise ValueError(f"Empty or near-empty page: {pdf_path.name}, {number + 1}")
            text_page.close()
            image_path = qa_path / f"page-{number + 1:02d}.png"
            bitmap = page.render(scale=1.4)
            bitmap.to_pil().save(image_path)
            bitmap.close()
            pages.append({"page": number + 1, "size_pt": page.get_size(), "image": str(image_path)})
            texts.append(text)
            page.close()
    full_text = "\n\n".join(texts)
    if "\ufffd" in full_text:
        raise ValueError(f"Replacement glyphs in {pdf_path.name}")
    title = source.read_text(encoding="utf-8").splitlines()[0].removeprefix("# ")
    if title not in " ".join(full_text.split()):
        raise ValueError(f"Title did not survive PDF extraction: {pdf_path.name}")
    (qa_path / "extracted.txt").write_text(full_text, encoding="utf-8")
    return {
        "source": str(source.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "pdf": str(pdf_path.relative_to(ROOT)),
        "pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", type=Path, help="Installed Chromium/Edge executable")
    args = parser.parse_args()
    if args.browser and not args.browser.is_file():
        parser.error(f"Browser executable not found: {args.browser}")
    source_folder = ROOT / "docs/submission_20261004"
    qa_folder = ROOT / ".cache/submission_qa"
    results = []
    footer = """
    <div style="width:100%; padding:0 18mm; font:8px 'Segoe UI',Arial,sans-serif;
                color:#5c6c76; display:flex; justify-content:flex-end;">
      <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
    </div>
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(args.browser) if args.browser else None, headless=True
        )
        try:
            for name in DOCUMENTS:
                source = source_folder / name
                qa_path = qa_folder / source.stem
                qa_path.mkdir(parents=True, exist_ok=True)
                html_path = qa_path / "print.html"
                html_path.write_text(printable_html(source), encoding="utf-8")
                page = browser.new_page()
                # Documents use local fonts and no remote assets; rendering needs no network.
                page.route("http://**/*", lambda route: route.abort())
                page.route("https://**/*", lambda route: route.abort())
                page.goto(html_path.as_uri(), wait_until="load", timeout=30000)
                page.evaluate("document.fonts.ready")
                page.emulate_media(media="print")
                pdf_path = source.with_suffix(".pdf")
                page.pdf(
                    path=str(pdf_path),
                    format="A4",
                    landscape=False,
                    print_background=True,
                    display_header_footer=True,
                    header_template="<div></div>",
                    footer_template=footer,
                    margin={"top": "17mm", "right": "18mm", "bottom": "19mm", "left": "18mm"},
                )
                page.close()
                result = inspect_pdf(pdf_path, qa_path, source)
                results.append(result)
                print(f"{pdf_path.relative_to(ROOT)}: {len(result['pages'])} pages")
        finally:
            browser.close()
    qa_folder.mkdir(parents=True, exist_ok=True)
    (qa_folder / "manifest.json").write_text(
        json.dumps({"documents": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
