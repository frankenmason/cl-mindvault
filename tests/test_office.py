"""Office document extraction tests.

Locks the 0.2.7 / 0.3.1 behavior: .docx / .xlsx / .pptx files are
extractable, detect() classifies them as 'document', and binary files
are routed through _extract_text_from_file instead of raw read_text.
"""

from __future__ import annotations

from pathlib import Path

from mindvault.detect import BINARY_DOCUMENT_EXTS, EXT_MAP, detect
from mindvault.ingest import _extract_text_from_file


class TestExtMap:
    def test_office_classified_as_document(self):
        assert EXT_MAP[".docx"] == "document"
        assert EXT_MAP[".xlsx"] == "document"
        assert EXT_MAP[".pptx"] == "document"

    def test_binary_document_exts_set(self):
        assert ".docx" in BINARY_DOCUMENT_EXTS
        assert ".xlsx" in BINARY_DOCUMENT_EXTS
        assert ".pptx" in BINARY_DOCUMENT_EXTS
        assert ".pdf" in BINARY_DOCUMENT_EXTS

    def test_markdown_not_in_binary(self):
        assert ".md" not in BINARY_DOCUMENT_EXTS
        assert ".txt" not in BINARY_DOCUMENT_EXTS


class TestOfficeExtraction:
    def test_docx_extracts_korean_text(self, office_docs_dir: Path):
        text = _extract_text_from_file(office_docs_dir / "proposal.docx")
        assert text is not None
        assert "프로젝트 A 제안서" in text
        assert "MindVault 문서 추출 테스트" in text

    def test_xlsx_extracts_sheet_name_and_cells(self, office_docs_dir: Path):
        text = _extract_text_from_file(office_docs_dir / "sales.xlsx")
        assert text is not None
        assert "# Sheet: 매출" in text
        assert "월" in text
        assert "매출" in text
        assert "1000000" in text

    def test_pptx_extracts_slide_titles(self, office_docs_dir: Path):
        text = _extract_text_from_file(office_docs_dir / "roadmap.pptx")
        assert text is not None
        assert "# Slide 1" in text
        assert "2026 로드맵" in text
        assert "MindVault 확장 계획" in text

    def test_nonexistent_file_returns_none(self, tmp_path: Path):
        result = _extract_text_from_file(tmp_path / "missing.docx")
        assert result is None


class TestDetectOnBinaryDocs:
    """Detect() must classify docx/xlsx/pptx as 'document' and NOT crash
    while reading them for word counts (binary formats are skipped)."""

    def test_detect_classifies_office_as_document(self, office_docs_dir: Path, tmp_path: Path):
        # Add one plain markdown file alongside the office fixtures so we can
        # verify word counting still works for text formats in the same run.
        (office_docs_dir / "readme.md").write_text("# Hello world\n\nSome plain text.\n")

        result = detect(office_docs_dir)
        docs = result["files"]["document"]
        # All four files (3 office + 1 md) should be classified
        basenames = sorted(Path(p).name for p in docs)
        assert "proposal.docx" in basenames
        assert "sales.xlsx" in basenames
        assert "roadmap.pptx" in basenames
        assert "readme.md" in basenames

    def test_detect_word_count_skips_binary(self, office_docs_dir: Path):
        (office_docs_dir / "note.md").write_text("word1 word2 word3\n")
        result = detect(office_docs_dir)
        # Only the .md file (3 words) contributes to total_words since
        # binary formats are intentionally skipped to avoid zip-noise
        assert result["total_words"] == 3
