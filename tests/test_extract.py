"""Unit tests for mindvault.extract helpers.

These lock the 0.3.1 Obsidian parser behavior so future refactors (planned for
0.4.0) can't silently regress.
"""

from __future__ import annotations

import pytest

from mindvault.extract import (
    _extract_inline_tags,
    _parse_frontmatter,
)


# ----------------------------------------------------------------------------
# _parse_frontmatter
# ----------------------------------------------------------------------------

class TestParseFrontmatter:
    def test_no_frontmatter(self):
        text = "# Just a Header\n\nBody."
        meta, rest, offset = _parse_frontmatter(text)
        assert meta == {}
        assert rest == text
        assert offset == 0

    def test_inline_list(self):
        text = (
            "---\n"
            "title: Auth Rewrite Plan\n"
            "tags: [project, auth, 2026-q2]\n"
            "status: in-progress\n"
            "---\n"
            "\n"
            "# Auth Rewrite Plan\n"
        )
        meta, rest, offset = _parse_frontmatter(text)
        assert meta["title"] == "Auth Rewrite Plan"
        assert meta["tags"] == ["project", "auth", "2026-q2"]
        assert meta["status"] == "in-progress"
        assert rest.startswith("# Auth Rewrite Plan")
        # 4 lines for frontmatter block + 1 blank line consumed by lstrip = 5
        assert offset >= 5

    def test_yaml_list(self):
        text = (
            "---\n"
            "tags:\n"
            "  - foo\n"
            "  - bar\n"
            "  - baz\n"
            "---\n"
            "Body"
        )
        meta, rest, _ = _parse_frontmatter(text)
        assert meta["tags"] == ["foo", "bar", "baz"]

    def test_quoted_values_stripped(self):
        text = "---\ntitle: \"Quoted Title\"\n---\nbody"
        meta, _, _ = _parse_frontmatter(text)
        assert meta["title"] == "Quoted Title"

    def test_empty_value(self):
        text = "---\naliases:\n---\nbody"
        meta, _, _ = _parse_frontmatter(text)
        # empty key gets [] (list continuation slot)
        assert meta["aliases"] == []

    def test_line_offset_preserved(self):
        """Line offset lets callers keep original file line numbers after strip."""
        text = "---\na: 1\nb: 2\n---\n# Header at line 5\n"
        _, rest, offset = _parse_frontmatter(text)
        # File line 5 is "# Header" → becomes line 1 of `rest` (offset=4)
        first_remaining_line = rest.splitlines()[0]
        assert first_remaining_line == "# Header at line 5"
        assert offset == 4


# ----------------------------------------------------------------------------
# _extract_inline_tags
# ----------------------------------------------------------------------------

class TestExtractInlineTags:
    @pytest.mark.parametrize("line, expected", [
        ("#project standalone", {"project"}),
        ("Leading space then #tag", {"tag"}),
        ("Multiple #one and #two #three", {"one", "two", "three"}),
        ("Nested #parent/child tag", {"parent/child"}),
        ("Dash allowed: #프로젝트-v2", {"프로젝트-v2"}),
    ])
    def test_basic_matches(self, line, expected):
        assert _extract_inline_tags(line) == expected

    def test_korean_and_cjk(self):
        line = "Korean #한글 and Japanese #日本語 together"
        assert _extract_inline_tags(line) == {"한글", "日本語"}

    @pytest.mark.parametrize("line", [
        "`#define FOO` inside backticks",
        "Mixed real with `#include <stdio.h>` and only `#macro`",
        "`#123` still stripped",
    ])
    def test_inline_code_stripped(self, line):
        # After stripping `...`, nothing real remains to extract
        result = _extract_inline_tags(line)
        # Filter out anything that would pass through — these lines only
        # contain tags inside code, so result should be empty
        assert result == set()

    def test_inline_code_mixed_with_real_tag(self):
        line = "Mixed `#define` in code but real #architecture outside"
        assert _extract_inline_tags(line) == {"architecture"}

    @pytest.mark.parametrize("line", [
        "Hex #fff color",
        "Hex #ffffff color",
        "Hex #abc123 color",
    ])
    def test_hex_colors_skipped(self, line):
        assert _extract_inline_tags(line) == set()

    def test_numeric_only_skipped(self):
        # #123 starts with a digit → not a tag (regex rejects digit first char)
        assert _extract_inline_tags("Issue #123 was fixed") == set()

    def test_bracket_preceded_ignored(self):
        # array[#idx] — # is preceded by `[`, not whitespace → not matched
        assert _extract_inline_tags("array[#idx] and cfg[#include]") == set()

    def test_empty_line(self):
        assert _extract_inline_tags("") == set()
