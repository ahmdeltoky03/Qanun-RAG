"""Chunk by *article*, not by character count.

A legal answer needs the whole article; a fixed-size window that cuts article 147
in half returns half a rule. Articles are short (median ~200 chars), so each one is
a single chunk per language. Only unusually long articles are split, on paragraph
(Arabic) or sentence (English) boundaries, with a small overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from prodml.arabic import normalize_for_search


@dataclass(frozen=True)
class Chunk:
    id: int
    article_number: int
    lang: str  # "ar" | "en"
    text: str  # what we show to the LLM / user
    embed_text: str  # what we embed (hierarchy-prefixed, normalised)
    payload: dict = field(default_factory=dict)


def _split(text: str, lang: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    units = text.split("\n") if lang == "ar" and "\n" in text else re.split(r"(?<=[.;؛])\s+", text)
    parts: list[str] = []
    cur = ""
    for u in units:
        if cur and len(cur) + len(u) + 1 > max_chars:
            parts.append(cur)
            cur = (cur[-overlap:] + " " + u) if overlap else u
        else:
            cur = f"{cur} {u}".strip()
    if cur:
        parts.append(cur)
    return parts


def build_chunks(records: list[dict], chunk_size: int = 300, overlap: int = 60) -> list[Chunk]:
    chunks: list[Chunk] = []
    for rec in records:
        n = rec["article_number"]
        for lang, text_key, ctx_keys in (
            ("ar", "text_ar", ("chapter_ar", "section_ar", "topic_ar")),
            ("en", "text_en", ("chapter", "section", "topic")),
        ):
            text = rec.get(text_key, "").strip()
            if not text:
                continue
            ctx = " > ".join(rec[k] for k in ctx_keys if rec.get(k))
            label = f"المادة {n}" if lang == "ar" else f"Article {n}"
            for j, piece in enumerate(_split(text, lang, chunk_size, overlap)):
                embed_text = normalize_for_search(f"{label}. {ctx}. {piece}" if ctx else f"{label}. {piece}")
                chunks.append(
                    Chunk(
                        id=len(chunks),
                        article_number=n,
                        lang=lang,
                        text=piece,
                        embed_text=embed_text,
                        payload={
                            "article_number": n,
                            "lang": lang,
                            "part": rec.get("part", ""),
                            "book": rec.get("book", ""),
                            "chapter": rec.get("chapter", ""),
                            "section": rec.get("section", ""),
                            "is_repealed": rec["is_repealed"],
                            "source_page": rec["source_page"],
                            "citation": rec["citation"],
                            "piece": j,
                            "text": piece,
                        },
                    )
                )
    return chunks
