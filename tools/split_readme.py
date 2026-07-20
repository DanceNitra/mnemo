"""Move the reference sections out of the README into docs/, leaving pointers.

The README had grown to 124 KB / 1587 lines — ten times mem0's and Supermemory's — with a 600-line API
reference and a 300-line integration catalogue sitting between the pitch and the proof. Nothing is
deleted: each block is MOVED verbatim into docs/ and replaced by a short pointer, so the landing page
answers "what is this and why should I trust it" and the reference stays one click away.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)

# (start heading, end heading exclusive, target file, pointer text)
MOVES = [
    ("## Use", "## Framework integrations", "API.md",
     "## Use\n\nThe full API reference — every method, argument and return shape, with runnable examples —\n"
     "lives in **[docs/API.md](docs/API.md)**. The four operations you actually need are further down this\n"
     "page; everything else is there when you need it.\n"),
    ("## Framework integrations", "## Use it as an MCP server", "INTEGRATIONS.md",
     "## Framework integrations\n\nAdapters for LangGraph, CrewAI, LangChain, LlamaIndex, AutoGen and the rest,\n"
     "with copy-paste snippets: **[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md)**.\n"),
    ("## The `second_brain` thinking layer", "## Status", "SECOND_BRAIN.md",
     "## The `second_brain` thinking layer\n\nAn optional layer on top of the store — dialectic, contradiction\n"
     "surfacing, question generation: **[docs/SECOND_BRAIN.md](docs/SECOND_BRAIN.md)**.\n"),
]


def main():
    text = README.read_text(encoding="utf-8")
    before = len(text)
    for start, end, target, pointer in MOVES:
        i = text.find("\n" + start)
        j = text.find("\n" + end)
        if i == -1 or j == -1 or j < i:
            print(f"SKIP {target}: could not locate '{start}' .. '{end}'")
            continue
        block = text[i + 1:j + 1]
        (DOCS / target).write_text(
            f"<!-- moved out of README.md to keep the landing page readable; content unchanged -->\n\n"
            + block, encoding="utf-8")
        text = text[:i + 1] + pointer + text[j + 1:]
        print(f"moved {len(block)//1024:>3} KB -> docs/{target}")
    README.write_text(text, encoding="utf-8")
    print(f"\nREADME {before//1024} KB -> {len(text)//1024} KB ({text.count(chr(10))} lines)")


if __name__ == "__main__":
    main()
