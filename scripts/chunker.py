"""Markdown canonicalization and chunking for Memory Tree Pipeline.

Turns arbitrary markdown into normalized chunks of ≤max_tokens tokens.
Splits on heading boundaries first, then paragraph boundaries, then hard splits.
"""
import re
from typing import List


def estimate_tokens(text: str) -> int:
    """Estimate token count. ~4 chars per token for English markdown."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def canonicalize(markdown: str) -> str:
    """Normalize markdown: strip frontmatter, normalize whitespace, clean artifacts."""
    text = markdown.strip()

    # Strip YAML frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3:].strip()

    # Normalize multiple blank lines to double
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Strip trailing whitespace per line
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    return text.strip()


def chunk_markdown(markdown: str, max_tokens: int = 3000) -> List[str]:
    """Split markdown into chunks, respecting heading and paragraph boundaries.

    Strategy:
    1. Split on H1/H2 headings first
    2. If a section exceeds max_tokens, split on H3/H4
    3. If still too large, split on paragraph boundaries (double newline)
    4. If still too large, hard split on sentence boundaries
    """
    text = canonicalize(markdown)
    if not text:
        return []

    if estimate_tokens(text) <= max_tokens:
        return [text]

    # Split on H1/H2 headings
    sections = re.split(r'\n(?=#{1,2}\s)', text)
    sections = [s.strip() for s in sections if s.strip()]

    result = []
    for section in sections:
        if estimate_tokens(section) <= max_tokens:
            result.append(section)
        else:
            # Split on H3/H4 headings
            subsections = re.split(r'\n(?=#{3,4}\s)', section)
            for sub in subsections:
                sub = sub.strip()
                if not sub:
                    continue
                if estimate_tokens(sub) <= max_tokens:
                    result.append(sub)
                else:
                    # Split on paragraphs
                    paras = sub.split("\n\n")
                    current = ""
                    for para in paras:
                        para = para.strip()
                        if not para:
                            continue
                        candidate = (current + "\n\n" + para).strip() if current else para
                        if estimate_tokens(candidate) <= max_tokens:
                            current = candidate
                        else:
                            if current:
                                result.append(current)
                            # If single paragraph exceeds limit, hard split
                            if estimate_tokens(para) > max_tokens:
                                words = para.split()
                                current = ""
                                for word in words:
                                    candidate = (current + " " + word).strip() if current else word
                                    if estimate_tokens(candidate) > max_tokens:
                                        if current:
                                            result.append(current)
                                        current = word
                                    else:
                                        current = candidate
                            else:
                                current = para
                    if current:
                        result.append(current)

    return [r for r in result if r.strip()]
