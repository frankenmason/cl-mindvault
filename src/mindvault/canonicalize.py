"""Centralized label canonicalization + context-specific escaping.

Design (S64 Phase P6, Mason option A, 3-way consensus):
- canonicalize_label() runs ONCE at ingest (extract.py/build.py)
- Graph invariant: all node/edge labels stored as safe canonical form
- Context-specific escapers apply at render time:
    md_escape_label  — markdown body/link/heading
    yaml_quote_label — frontmatter values
    safe_slugify     — filesystem paths + anchors
"""
from __future__ import annotations
import re
import unicodedata


# Whitespace-ish control chars → space (preserves word boundary)
_WS_CONTROL = re.compile(r"[\x09\x0a\x0b\x0c\x0d]")
# Other hostile chars must be removed (not replaced)
_CONTROL_CHARS = re.compile(
    r"[\x00-\x08\x0e-\x1f\x7f"   # ASCII control EXCEPT whitespace (handled above)
    r"\u200b-\u200f"               # zero-width + bidi marks
    r"\u202a-\u202e"               # bidi override
    r"\u2066-\u2069"               # bidi isolates
    r"\ufeff"                      # BOM / ZWNBSP
    r"]"
)

# Markdown metacharacters requiring backslash escape in general text
_MD_METACHARS = re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~])")

# YAML-unsafe chars requiring quoted string in frontmatter
_YAML_UNSAFE = re.compile(r"[:#!&*\|><%@`]|^[-?]")

# Slugify: lowercase, collapse non-alnum to hyphens, strip leading dots
_SLUG_ALLOWED = re.compile(r"[^a-z0-9\-]+")
_WINDOWS_RESERVED = {"con","prn","aux","nul","com1","com2","com3","com4","com5",
                     "com6","com7","com8","com9","lpt1","lpt2","lpt3","lpt4",
                     "lpt5","lpt6","lpt7","lpt8","lpt9"}


def canonicalize_label(text, max_len: int = 200) -> str:
    """Remove hostile unicode + control + normalize + cap length.

    MUST run exactly once at ingest. Downstream sinks assume output is canonical.
    """
    if text is None:
        return ""
    s = str(text)
    # Unicode NFC normalize (homograph mitigation)
    s = unicodedata.normalize("NFC", s)
    # Whitespace control → space (preserve word boundaries)
    s = _WS_CONTROL.sub(" ", s)
    # Remove hostile control/bidi/zero-width
    s = _CONTROL_CHARS.sub("", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Length cap
    if len(s) > max_len:
        s = s[:max_len - 1] + "\u2026"  # ellipsis
    return s


def md_escape_label(text) -> str:
    """Escape markdown metacharacters for safe embedding in body/heading/link text.

    Input SHOULD already be canonicalized (defensive re-canonicalize is cheap).
    """
    s = canonicalize_label(text)
    s = _MD_METACHARS.sub(r"\\\1", s)
    # Prevent HTML injection in lenient renderers
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    return s


def yaml_quote_label(text) -> str:
    """Quote for YAML frontmatter value. Always wraps in double quotes.
    
    Escapes backslash and double quotes per YAML 1.2 double-quoted scalar rules.
    """
    s = canonicalize_label(text)
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def safe_slugify(text, max_len: int = 80) -> str:
    """Filesystem-safe slug. Rejects traversal, empty, reserved names.

    Always returns ASCII [a-z0-9-]+. Falls back to 'unnamed-<hash>' if empty.
    """
    s = canonicalize_label(text).lower()
    # Drop non-alnum → hyphen, collapse repeats
    s = _SLUG_ALLOWED.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-.")
    # Reject Windows reserved names
    if s in _WINDOWS_RESERVED:
        s = f"safe-{s}"
    # Length cap
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    # Empty / all-stripped fallback
    if not s:
        import hashlib
        h = hashlib.md5(str(text).encode("utf-8", errors="ignore")).hexdigest()[:8]
        s = f"unnamed-{h}"
    return s
