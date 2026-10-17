"""Protect canonical Help links and the packaged runtime mirrors."""

from html.parser import HTMLParser
from pathlib import Path
import runpy
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]


class HelpPage(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.lang = None
        self.ids = set()
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.lang = attrs.get("lang")
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag in ("a", "link") and "href" in attrs:
            self.links.append(attrs["href"])


def test_generated_help_languages_links_and_runtime_sync(tmp_path):
    generator = runpy.run_path(str(ROOT / "scripts/generate_help.py"))
    generator["generate"](tmp_path)
    names = {"cli.html", "cli.zh-TW.html", "webui.html", "webui.zh-TW.html",
             "supported-models.html", "supported-models.zh-TW.html", "help.css"}
    assert {path.name for path in tmp_path.iterdir()} == names
    pages = {name: HelpPage((tmp_path / name).read_text(encoding="utf-8"))
             for name in names if name.endswith(".html")}
    for name, page in pages.items():
        assert page.lang == ("zh-TW" if ".zh-TW." in name else "en")
        assert "help-content" in page.ids
        for href in page.links:
            link = urlsplit(href)
            if link.scheme or link.netloc:
                assert link.scheme == "https", href
                continue
            target = unquote(link.path) or name
            assert target in names, (name, href)
            if link.fragment:
                assert unquote(link.fragment) in pages[target].ids, (name, href)
    for owner, guide in (("scopes_tool_cli/help", "cli"),
                         ("scopes_tool_webui/static/help", "webui")):
        for name in (f"{guide}.html", f"{guide}.zh-TW.html", "supported-models.html",
                     "supported-models.zh-TW.html", "help.css"):
            assert (ROOT / "src" / owner / name).read_bytes() == (tmp_path / name).read_bytes()
