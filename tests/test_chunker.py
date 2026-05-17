"""Tests for the markdown chunker."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from chunker import canonicalize, chunk_markdown, estimate_tokens


def test_canonicalize_strips_frontmatter():
    md = "---\ntitle: Test\n---\n# Hello\nWorld"
    result = canonicalize(md)
    assert "---" not in result
    assert "# Hello" in result


def test_canonicalize_normalizes_whitespace():
    md = "Hello   \n\n\n\n  World"
    result = canonicalize(md)
    assert "\n\n\n" not in result


def test_chunk_by_headings():
    md = "# Section 1\nContent A\n\n# Section 2\nContent B\n\n# Section 3\nContent C"
    chunks = chunk_markdown(md, max_tokens=10)
    assert len(chunks) >= 2
    assert all(len(c) > 0 for c in chunks)


def test_chunk_respects_max_tokens():
    md = "Word " * 5000  # ~5000 tokens
    chunks = chunk_markdown(md, max_tokens=3000)
    for c in chunks:
        assert estimate_tokens(c) <= 3200  # allow 6% overrun for boundary


def test_chunk_small_doc_single_chunk():
    md = "# Small\nJust a little note."
    chunks = chunk_markdown(md, max_tokens=3000)
    assert len(chunks) == 1


def test_estimate_tokens():
    assert estimate_tokens("hello world") >= 2
    assert estimate_tokens("") == 0


if __name__ == "__main__":
    test_canonicalize_strips_frontmatter()
    test_canonicalize_normalizes_whitespace()
    test_chunk_by_headings()
    test_chunk_respects_max_tokens()
    test_chunk_small_doc_single_chunk()
    test_estimate_tokens()
    print("All chunker tests passed!")
