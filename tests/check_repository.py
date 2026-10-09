"""Reproduce syntax and local Markdown-link checks without external tools."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    count = 0
    for folder in ("mazeproof", "tests"):
        for path in (ROOT / folder).rglob("*.py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            count += 1
    documents = [ROOT / "README.md"]
    for folder in ("docs", "tests/fixtures", "examples"):
        documents.extend((ROOT / folder).rglob("*.md"))
    links = 0
    for document in documents:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            target = target.strip("<>").split("#", 1)[0]
            resolved = (document.parent / target).resolve()
            if ROOT not in resolved.parents or not resolved.is_file():
                raise ValueError("Broken or non-repository link in {}: {}".format(document.relative_to(ROOT), target))
            links += 1
    print("Python syntax ({} files) and local Markdown links ({}): OK".format(count, links))


if __name__ == "__main__":
    main()
