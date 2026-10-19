"""Generate offline Help from the six canonical Markdown documents."""

from __future__ import annotations

import argparse
import html
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit

import markdown
from markdown.extensions.toc import TocExtension, slugify_unicode


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("docs/cli/USER_GUIDE.md", "cli.html", "en"),
    ("docs/cli/USER_GUIDE.zh-TW.md", "cli.zh-TW.html", "zh-TW"),
    ("docs/webui/USER_GUIDE.md", "webui.html", "en"),
    ("docs/webui/USER_GUIDE.zh-TW.md", "webui.zh-TW.html", "zh-TW"),
    ("docs/core/supported-models.md", "supported-models.html", "en"),
    ("docs/core/supported-models.zh-TW.md", "supported-models.zh-TW.html", "zh-TW"),
)


def rewrite_links(content: str, source: Path) -> str:
    targets = {(REPO_ROOT / name).resolve(): output for name, output, _ in SOURCES}

    def replace(match: re.Match[str]) -> str:
        href, label = match.groups()
        link = urlsplit(html.unescape(href))
        if link.scheme or link.netloc or not link.path:
            return match.group(0)
        target = (source.parent / unquote(link.path)).resolve()
        if target in targets:
            href = targets[target]
            if link.fragment:
                href += "#" + link.fragment
            return f'<a href="{html.escape(href, quote=True)}">{label}</a>'
        # Do not expose repository-only paths to installed Help readers.
        raise ValueError(f"Offline Help link is not bundled: {source.relative_to(REPO_ROOT)} -> {link.path}")

    return re.sub(r'<a href="([^"]+)">(.*?)</a>', replace, content, flags=re.DOTALL)


def generate(output_dir: Path) -> None:
    template = (REPO_ROOT / "docs/help/template.html").read_text(encoding="utf-8")
    for token in ("{{lang}}", "{{title}}", "{{content}}"):
        if template.count(token) != 1:
            raise ValueError(f"Help template must contain {token} exactly once")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, output, lang in SOURCES:
        source = REPO_ROOT / name
        text = source.read_text(encoding="utf-8")
        title = re.search(r"^# (.+)$", text, re.MULTILINE)
        if title is None:
            raise ValueError(f"Help source has no H1 title: {name}")
        content = markdown.markdown(text, extensions=[
            "fenced_code", "tables", "sane_lists", TocExtension(slugify=slugify_unicode),
        ])
        content = rewrite_links(content, source)
        page = template.replace("{{lang}}", lang)
        page = page.replace("{{title}}", html.escape(title.group(1), quote=True))
        page = page.replace("{{content}}", content)
        (output_dir / output).write_text(page, encoding="utf-8", newline="\n")
    shutil.copyfile(REPO_ROOT / "docs/help/help.css", output_dir / "help.css")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / ".tmp_tests/generated_help")
    args = parser.parse_args()
    generate(args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
