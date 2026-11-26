import hashlib
from dataclasses import dataclass
from pathlib import Path

from .schema import Evidence


@dataclass
class Document:
    name: str
    sha256: str
    lines: list[str]
    pages: list[int | None]

    def numbered(self):
        return "\n".join(f"{i}: {line}" for i, line in enumerate(self.lines, 1))

    def verify(self, evidence: Evidence):
        if not 1 <= evidence.line_start <= evidence.line_end <= len(self.lines):
            raise ValueError("Evidence line range outside document")
        excerpt = "\n".join(self.lines[evidence.line_start - 1 : evidence.line_end])
        if evidence.quote not in excerpt:
            raise ValueError("Evidence quote does not occur at claimed location")


def read_document(path: Path) -> Document:
    if path.stat().st_size > 20_000_000:
        raise ValueError("Document exceeds 20 MB limit")
    raw = path.read_bytes()
    pages = []
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF is unsupported")
        if len(reader.pages) > 200:
            raise ValueError("PDF exceeds 200 pages")
        lines = []
        for page_number, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                raise ValueError(f"Page {page_number}: no text; OCR required, analysis stopped")
            part = text.splitlines()
            lines.extend(part)
            pages.extend([page_number] * len(part))
    elif path.suffix.lower() in {".md", ".txt"}:
        lines = raw.decode("utf-8-sig").splitlines()
        pages = [None] * len(lines)
    else:
        raise ValueError("Supported input: PDF with text layer, Markdown, UTF-8 TXT")
    if not lines or not any(line.strip() for line in lines):
        raise ValueError("Empty document")
    if sum(map(len, lines)) > 100_000:
        raise ValueError("Input exceeds 100,000 characters; no silent truncation")
    return Document(path.name, hashlib.sha256(raw).hexdigest(), lines, pages)
