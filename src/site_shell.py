"""The frame every page shares: fonts, stylesheet, masthead, footer and the data hand-off.

A page template in src/templates/ holds only what is specific to that page (its text and
its script). `render` wraps it in the shared frame and drops the page's data in, so the
four pages cannot drift apart in look or navigation.
"""
from __future__ import annotations

import json

import edgar

TEMPLATES = edgar.ROOT / "src" / "templates"
DOCS = edgar.ROOT / "docs"
SITE_NAME = "Lookthrough"
# Where the site is served from once the repository is public and GitHub Pages is switched on.
# Link previews (the card LinkedIn and others draw when the address is pasted) need full addresses,
# so this is the one place to change if the repository is renamed or a custom domain is used.
SITE_URL = "https://abhay-kumar-2501.github.io/lookthrough/"
CARD = "assets/card.png"  # 1200 x 627, drawn by make_charts.py
CARD_SIZE = (1200, 627)
ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%2315181e'/%3E"
        "%3Crect x='7' y='18' width='4' height='7' fill='%23f6f2e9'/%3E%3Crect x='14' y='12' width='4' height='13' fill='%23f6f2e9'/%3E%3Crect x='21' y='7' width='4' height='18' fill='%23a8321f'/%3E%3C/svg%3E")
AUTHOR = "Abhay Kumar"
PAGES = [
    ("index.html", "Your fund"),
    ("spenders.html", "The workings"),
    ("nvidia.html", "Companion: NVIDIA"),
    ("method.html", "Method and checks"),
]
FONTS = (
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600"
    "&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400"
    "&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&display=swap"
)
DATA_MARK = "/*__DATA__*/null"


def to_json(data) -> str:
    """Strict JSON that is safe inside a <script> block."""
    return json.dumps(data, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")


def render(page: str, title: str, description: str, dateline: str, data=None, body: str | None = None, card_title: str | None = None) -> str:
    """Wrap a page in the shared frame. The body comes from src/templates/<page> unless given directly.

    `card_title` is the headline shown when the page's address is pasted somewhere; by default
    it is the page title followed by the site's name.
    """
    card_title = card_title or f"{title} · {SITE_NAME}"
    if body is None:
        body = (TEMPLATES / page).read_text()
    if data is not None:
        assert DATA_MARK in body, f"{page} has no data placeholder"
        body = body.replace(DATA_MARK, to_json(data))
    here = ' aria-current="page"'
    nav = "".join(f'<a href="{href}"{here if href == page else ""}>{label}</a>' for href, label in PAGES)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="author" content="{AUTHOR}">
<link rel="canonical" href="{SITE_URL}{"" if page == "index.html" else page}">
<link rel="icon" href="{ICON}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{card_title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{SITE_URL}{"" if page == "index.html" else page}">
<meta property="og:image" content="{SITE_URL}{CARD}">
<meta property="og:image:width" content="{CARD_SIZE[0]}">
<meta property="og:image:height" content="{CARD_SIZE[1]}">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<main>
  <header class="mast"><a class="brand" href="index.html">{SITE_NAME}</a><nav aria-label="Pages">{nav}</nav></header>
  <div class="dateline"><span>By {AUTHOR}</span><span>{dateline}</span></div>
<script src="assets/charts.js"></script>
{body}
  <footer>
    <nav aria-label="Pages">{nav}</nav>
    <p>By {AUTHOR}. Built with Claude Code. Every figure comes from a filing with the US securities regulator unless the page says otherwise. Figures read from a sentence link to it; calculated figures show their workings.</p>
    <p>I am a finance student and this is a research project. It is not investment advice, and nothing here is a claim that any company has acted improperly.</p>
  </footer>
</main>
</body>
</html>
"""


def write(page: str, html: str) -> None:
    DOCS.mkdir(exist_ok=True)
    (DOCS / page).write_text(html)
    print(f"docs/{page} written ({len(html) / 1024:.0f} KB)")
