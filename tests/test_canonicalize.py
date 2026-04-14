"""Adversarial tests for canonicalize.py (S64 P6)."""
import pytest
from mindvault.canonicalize import (
    canonicalize_label, md_escape_label, yaml_quote_label, safe_slugify
)


class TestCanonicalizeLabel:
    def test_control_chars_stripped(self):
        assert canonicalize_label("a\x00b\x1fc") == "abc"  # non-WS control stripped, no space inserted
    
    def test_zero_width_stripped(self):
        assert canonicalize_label("a\u200bb\u200cc\ufeffd") == "abcd"
    
    def test_bidi_override_stripped(self):
        assert canonicalize_label("hello\u202eevil") == "helloevil"
    
    def test_newlines_stripped(self):
        assert canonicalize_label("a\nb\r\nc\td") == "a b c d"
    
    def test_nfc_normalize(self):
        # Combining character NFD → NFC precomposed
        assert canonicalize_label("café") == canonicalize_label("cafe\u0301")
    
    def test_length_cap(self):
        out = canonicalize_label("x" * 300)
        assert len(out) <= 200
        assert out.endswith("\u2026")
    
    def test_none_empty(self):
        assert canonicalize_label(None) == ""
        assert canonicalize_label("") == ""


class TestMdEscape:
    def test_metachar_escape(self):
        out = md_escape_label("[link](url)")
        assert "\\[" in out and "\\]" in out and "\\(" in out
    
    def test_html_escape(self):
        out = md_escape_label("<script>alert(1)</script>")
        assert "&lt;" in out and "&gt;" in out
        assert "<script>" not in out
    
    def test_wikilink_break(self):
        # Prevent label from prematurely closing [[...]]
        out = md_escape_label("foo]]\n[click](bad)")
        assert "]]" not in out


class TestYamlQuote:
    def test_colon_safe(self):
        out = yaml_quote_label("title: pwn")
        assert out.startswith('"') and out.endswith('"')
    
    def test_backslash_escape(self):
        out = yaml_quote_label(r'path\to\file')
        assert r'\\' in out


class TestSafeSlugify:
    def test_path_traversal_blocked(self):
        slug = safe_slugify("../../etc/passwd")
        assert ".." not in slug
        assert "/" not in slug
        assert not slug.startswith(".")
    
    def test_windows_reserved(self):
        slug = safe_slugify("CON")
        assert slug != "con"
    
    def test_empty_fallback(self):
        slug = safe_slugify("!!!")
        assert slug.startswith("unnamed-")
    
    def test_allowed_chars_only(self):
        import re
        slug = safe_slugify("Hello World! 한국어 <script>")
        assert re.match(r"^[a-z0-9\-]+$", slug)


class TestIntegration:
    def test_ingest_canonicalize_flow(self):
        """LLM injected label → canonicalize → md_escape flow preserves invariant."""
        # LLM injects malicious label with bidi + markdown + HTML
        hostile = "normal\u202e\n]][\u200bscript src=x"
        canonical = canonicalize_label(hostile)
        # No control / bidi / newline
        assert "\u202e" not in canonical
        assert "\n" not in canonical
        assert "\u200b" not in canonical
        # md_escape now safe for markdown
        md = md_escape_label(canonical)
        assert "\\]" in md or "]]" not in md
