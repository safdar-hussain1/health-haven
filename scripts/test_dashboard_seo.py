#!/usr/bin/env python3
"""Check that the search and link-preview metadata survives into docs/index.html.

docs/index.template.html carries the <head> block (title, description,
canonical, Open Graph and Twitter tags, JSON-LD) and scripts/build_dashboard.py
bakes it into docs/index.html. Standard library only, so it runs anywhere the
build does:

    python3 scripts/test_dashboard_seo.py
"""
import json
import pathlib
import re
import struct
import unittest
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
PAGE = DOCS / "index.html"
TEMPLATE = DOCS / "index.template.html"

URL = "https://safdar-hussain1.github.io/health-haven/"
REPO = "https://github.com/safdar-hussain1/health-haven"
TOKEN = "0SIEfExLTSQj1qvnHWF5A5fY58KVl2lpIEnePP9CtI0"
AUTHOR = "Safdar Hussain"


class Head(HTMLParser):
    """Collects <head> metadata, the JSON-LD blocks and the <h1> count."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang, self.title = None, None
        self.meta, self.links, self.ld, self.h1 = {}, [], [], 0
        self._in_head = self._in_title = self._in_ld = False
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "head":
            self._in_head = True
        elif tag == "title" and self._in_head and self.title is None:
            self._in_title, self._buf = True, ""
        elif tag == "meta" and (a.get("name") or a.get("property")):
            key = (a.get("name") or a.get("property")).lower()
            self.meta.setdefault(key, []).append((a.get("content") or "").strip())
        elif tag == "link":
            self.links.append(a)
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_ld, self._buf = True, ""
        elif tag == "h1":
            self.h1 += 1

    def handle_endtag(self, tag):
        if tag == "head":
            self._in_head = False
        elif tag == "title" and self._in_title:
            self._in_title, self.title = False, " ".join(self._buf.split())
        elif tag == "script" and self._in_ld:
            self._in_ld = False
            self.ld.append(self._buf)

    def handle_data(self, data):
        if self._in_title or self._in_ld:
            self._buf += data


class DashboardSeoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")
        cls.head = Head()
        cls.head.feed(cls.html)

    def one(self, key):
        values = self.head.meta.get(key, [])
        self.assertEqual(len(values), 1, f"expected exactly one {key!r} tag")
        return values[0]

    def test_head_comes_from_the_template(self):
        template = TEMPLATE.read_text(encoding="utf-8")
        cut = lambda text: text[:text.index("</head>")]
        self.assertEqual(cut(self.html), cut(template),
                         "docs/index.html is stale: run python3 scripts/build_dashboard.py")

    def test_language_title_and_description(self):
        self.assertEqual(self.head.lang, "en")
        self.assertTrue(self.head.title)
        self.assertLessEqual(len(self.head.title), 60)
        self.assertTrue(120 <= len(self.one("description")) <= 160)
        self.assertEqual(self.one("author"), AUTHOR)
        self.assertEqual(self.one("google-site-verification"), TOKEN)
        self.assertIn("viewport", self.head.meta)

    def test_canonical_and_favicon(self):
        rels = lambda link: (link.get("rel") or "").lower().split()
        self.assertEqual([l.get("href") for l in self.head.links if rels(l) == ["canonical"]], [URL])
        icons = [l.get("href") or "" for l in self.head.links if "icon" in rels(l)]
        self.assertTrue(icons, "no <link rel=icon>")
        self.assertTrue(icons[0].startswith("data:image/svg+xml") or (DOCS / icons[0]).is_file())

    def test_open_graph_and_twitter_cards(self):
        title, description = self.head.title, self.one("description")
        self.assertEqual(self.one("og:type"), "website")
        self.assertEqual(self.one("og:site_name"), AUTHOR)
        self.assertEqual(self.one("og:url"), URL)
        self.assertEqual(self.one("og:title"), title)
        self.assertEqual(self.one("twitter:title"), title)
        self.assertEqual(self.one("og:description"), description)
        self.assertEqual(self.one("twitter:description"), description)
        self.assertEqual(self.one("og:image"), URL + "og-image.png")
        self.assertEqual(self.one("twitter:image"), URL + "og-image.png")
        self.assertEqual(self.one("og:image:width"), "1200")
        self.assertEqual(self.one("og:image:height"), "630")
        self.assertTrue(self.one("og:image:alt"))
        self.assertEqual(self.one("twitter:image:alt"), self.one("og:image:alt"))
        self.assertEqual(self.one("twitter:card"), "summary_large_image")

    def test_json_ld_graph_names_the_app_the_code_and_the_author(self):
        self.assertEqual(len(self.head.ld), 1, "expected one JSON-LD block")
        graph = {node["@type"]: node for node in json.loads(self.head.ld[0])["@graph"]}
        app, code = graph["WebApplication"], graph["SoftwareSourceCode"]
        self.assertEqual(app["url"], URL)
        self.assertEqual(app["image"], URL + "og-image.png")
        self.assertEqual(app["description"], self.one("description"))
        self.assertEqual(app["applicationCategory"], "BusinessApplication")
        self.assertEqual(code["codeRepository"], REPO)
        self.assertIn("Java", code["programmingLanguage"])
        for node in (app, code):
            self.assertEqual(node["author"]["@type"], "Person")
            self.assertEqual(node["author"]["name"], AUTHOR)
            self.assertIn("https://github.com/safdar-hussain1", node["author"]["sameAs"])

    def test_exactly_one_h1(self):
        self.assertEqual(self.head.h1, 1)

    def test_og_image_is_a_1200x630_png_under_500kb(self):
        data = (DOCS / "og-image.png").read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", data[16:24]), (1200, 630))
        self.assertLess(len(data), 500 * 1024)

    def test_sitemap_lists_the_page_with_a_fixed_lastmod(self):
        sitemap = (DOCS / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn(f"<loc>{URL}</loc>", sitemap)
        self.assertRegex(sitemap, r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>")


if __name__ == "__main__":
    unittest.main()
