"""Deterministic text chunker — content-hash IDs guarantee idempotency."""

from __future__ import annotations

import hashlib

from xagent.core.wiki.models import CanonicalDoc, Chunk


class WikiChunker:
    """Split documents into ≤ max_tokens chunks with deterministic IDs."""

    def __init__(self, max_tokens: int = 3000, overlap_tokens: int = 200):
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, doc: CanonicalDoc) -> list[Chunk]:
        """Split *doc* into chunks.  Same content → same chunk IDs."""
        paragraphs = doc.content.split("\n\n")
        chunks: list[Chunk] = []
        current_text = ""
        position = 0

        for para in paragraphs:
            if not para.strip():
                continue
            candidate = (current_text + "\n\n" + para).strip() if current_text else para
            if self._estimate_tokens(candidate) > self.max_tokens and current_text:
                chunk_id = self._content_hash(doc.doc_id, position, current_text)
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc.doc_id,
                    content=current_text.strip(),
                    token_count=self._estimate_tokens(current_text),
                    position=position,
                ))
                position += 1
                # Overlap: carry tail of previous chunk
                if self.overlap_tokens > 0:
                    tail = self._tail_tokens(current_text, self.overlap_tokens)
                    current_text = (tail + "\n\n" + para).strip()
                else:
                    current_text = para
            else:
                current_text = candidate

        if current_text.strip():
            chunk_id = self._content_hash(doc.doc_id, position, current_text)
            chunks.append(Chunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                content=current_text.strip(),
                token_count=self._estimate_tokens(current_text),
                position=position,
            ))

        return chunks

    @staticmethod
    def _content_hash(doc_id: str, position: int, content: str) -> str:
        """Deterministic ID: identical content always produces the same ID."""
        raw = f"{doc_id}:{position}:{content}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: CJK ≈ 1.5 tok/char, Latin ≈ 0.75 tok/word."""
        cn_chars = sum(1 for c in text if "一" <= c <= "鿿")
        en_words = len(text.split()) - cn_chars
        return max(1, int(cn_chars * 1.5 + max(0, en_words) * 0.75))

    @staticmethod
    def _tail_tokens(text: str, n: int) -> str:
        """Return approximately the last *n* tokens of *text*."""
        words = text.split()
        # Rough: take last n words (good enough for overlap)
        return " ".join(words[-n:]) if len(words) > n else text
