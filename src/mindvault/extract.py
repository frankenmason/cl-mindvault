"""AST extraction (tree-sitter) + semantic extraction interface."""

from __future__ import annotations

import re
from pathlib import Path
from tree_sitter import Language, Parser


def _get_language(ext: str):
    """Return tree-sitter Language for a file extension, or None."""
    try:
        if ext == ".py":
            import tree_sitter_python
            return Language(tree_sitter_python.language())
        elif ext in (".ts",):
            import tree_sitter_typescript
            return Language(tree_sitter_typescript.language_typescript())
        elif ext in (".tsx",):
            import tree_sitter_typescript
            return Language(tree_sitter_typescript.language_tsx())
        elif ext in (".js", ".jsx", ".mjs"):
            import tree_sitter_javascript
            return Language(tree_sitter_javascript.language())
        elif ext == ".go":
            import tree_sitter_go
            return Language(tree_sitter_go.language())
        elif ext == ".rs":
            import tree_sitter_rust
            return Language(tree_sitter_rust.language())
        elif ext == ".java":
            import tree_sitter_java
            return Language(tree_sitter_java.language())
        elif ext == ".swift":
            import tree_sitter_swift
            return Language(tree_sitter_swift.language())
        elif ext in (".kt", ".kts"):
            import tree_sitter_kotlin
            return Language(tree_sitter_kotlin.language())
        elif ext in (".c", ".h"):
            import tree_sitter_c
            return Language(tree_sitter_c.language())
        elif ext in (".cpp", ".cc", ".cxx", ".hpp"):
            import tree_sitter_cpp
            return Language(tree_sitter_cpp.language())
        elif ext == ".rb":
            import tree_sitter_ruby
            return Language(tree_sitter_ruby.language())
        elif ext == ".cs":
            import tree_sitter_c_sharp
            return Language(tree_sitter_c_sharp.language())
    except (ImportError, Exception):
        return None
    return None


def _sanitize_id(name: str) -> str:
    """Convert name to a valid node ID component: lowercase, special chars to underscore."""
    return re.sub(r"[^a-z0-9_]", "_", name.lower())


def _node_id(filestem: str, entity_name: str) -> str:
    return f"{_sanitize_id(filestem)}_{_sanitize_id(entity_name)}"


def _extract_text(node) -> str:
    """Get text content of a node."""
    return node.text.decode("utf-8", errors="ignore") if node.text else ""


def _find_children_by_type(node, type_name: str) -> list:
    """Find direct children of a given type."""
    return [c for c in node.children if c.type == type_name]


def _find_identifier(node) -> str | None:
    """Find the first identifier child's text."""
    for c in node.children:
        if c.type in ("identifier", "name", "type_identifier"):
            return _extract_text(c)
    return None


# Language-specific node type maps for functions and classes
_FUNC_TYPES = {
    "function_definition",      # Python
    "function_declaration",     # JS/TS/Go/C/C++/Java
    "method_definition",        # JS/TS class methods
    "method_declaration",       # Java/C#/Swift/Kotlin
    "arrow_function",           # JS/TS (only named via variable)
    "function_item",            # Rust
    "impl_item",                # Rust impl block
    "function",                 # Ruby
    "method",                   # Ruby
}

_CLASS_TYPES = {
    "class_definition",         # Python
    "class_declaration",        # JS/TS/Java/C#/Kotlin
    "struct_item",              # Rust
    "class_specifier",          # C++
    "struct_specifier",         # C/C++
    "interface_declaration",    # TS/Java
    "protocol_declaration",     # Swift
    "class",                    # Ruby
    "module",                   # Ruby
}

_IMPORT_TYPES = {
    "import_statement",         # Python/Java/TS
    "import_from_statement",    # Python
    "import_declaration",       # Go/Kotlin
    "use_declaration",          # Rust
    "require",                  # Ruby
    "using_directive",          # C#
}


def _extract_imports(node) -> list[str]:
    """Extract import targets from an import node."""
    targets = []
    for child in node.children:
        if child.type in ("dotted_name", "identifier", "scoped_identifier",
                          "qualified_name", "string", "name"):
            text = _extract_text(child)
            if text and text not in ("import", "from", "use", "require", "using"):
                targets.append(text)
    # For import_from_statement, get the module name (first dotted_name)
    if node.type == "import_from_statement":
        for child in node.children:
            if child.type == "dotted_name":
                targets = [_extract_text(child)]
                break
    return targets


def _extract_calls(node) -> list[str]:
    """Recursively find all function call names in a subtree."""
    calls = []
    if node.type == "call":
        func = node.child_by_field_name("function")
        if func is None and node.children:
            func = node.children[0]
        if func:
            text = _extract_text(func)
            # Strip object prefix: self.method -> method, obj.method -> method
            if "." in text:
                text = text.rsplit(".", 1)[-1]
            if text:
                calls.append(text)
    elif node.type == "call_expression":
        func = node.child_by_field_name("function")
        if func is None and node.children:
            func = node.children[0]
        if func:
            text = _extract_text(func)
            if "." in text:
                text = text.rsplit(".", 1)[-1]
            if text:
                calls.append(text)
    for child in node.children:
        calls.extend(_extract_calls(child))
    return calls


def _get_superclasses(node) -> list[str]:
    """Extract superclass names from a class definition node."""
    supers = []
    # Python: argument_list contains superclasses
    for child in node.children:
        if child.type == "argument_list":
            for arg in child.children:
                if arg.type in ("identifier", "dotted_name", "type_identifier"):
                    supers.append(_extract_text(arg))
        elif child.type == "superclass":
            text = _extract_text(child)
            if text:
                supers.append(text)
        elif child.type == "super_interfaces" or child.type == "extends_type_clause":
            for sc in child.children:
                if sc.type in ("identifier", "type_identifier", "dotted_name"):
                    supers.append(_extract_text(sc))
    return supers


def _process_file(file_path: Path, lang) -> tuple[list[dict], list[dict]]:
    """Process a single file and return (nodes, edges)."""
    nodes = []
    edges = []

    try:
        code = file_path.read_bytes()
    except (OSError, IOError):
        return nodes, edges

    parser = Parser(lang)
    tree = parser.parse(code)
    root = tree.root_node

    if root.has_error:
        # Still try to extract what we can
        pass

    filestem = _sanitize_id(file_path.stem)
    source_file = str(file_path)

    # Module node
    module_id = _node_id(filestem, "module")
    nodes.append({
        "id": module_id,
        "label": file_path.stem,
        "file_type": "code",
        "source_file": source_file,
        "source_location": None,
    })

    # Track defined names for call resolution
    defined_names: dict[str, str] = {}  # entity_name -> node_id

    # First pass: extract functions and classes at all levels
    def visit_definitions(node, parent_class_id=None):
        for child in node.children:
            if child.type in _FUNC_TYPES:
                name = _find_identifier(child)
                if not name:
                    # Try field name
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = _extract_text(name_node)
                if not name:
                    continue

                nid = _node_id(filestem, name)
                loc = f"L{child.start_point[0] + 1}"
                nodes.append({
                    "id": nid,
                    "label": name,
                    "file_type": "code",
                    "source_file": source_file,
                    "source_location": loc,
                })
                defined_names[name] = nid

                # contains edge
                container = parent_class_id if parent_class_id else module_id
                edges.append({
                    "source": container,
                    "target": nid,
                    "relation": "contains",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source_file,
                    "weight": 1.0,
                })

                # Extract calls within this function
                calls = _extract_calls(child)
                for call_name in calls:
                    call_target_id = _node_id(filestem, call_name)
                    edges.append({
                        "source": nid,
                        "target": call_target_id,
                        "relation": "calls",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": source_file,
                        "weight": 1.0,
                    })

            elif child.type in _CLASS_TYPES:
                name = _find_identifier(child)
                if not name:
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        name = _extract_text(name_node)
                if not name:
                    continue

                nid = _node_id(filestem, name)
                loc = f"L{child.start_point[0] + 1}"
                nodes.append({
                    "id": nid,
                    "label": name,
                    "file_type": "code",
                    "source_file": source_file,
                    "source_location": loc,
                })
                defined_names[name] = nid

                # contains edge (module contains class)
                edges.append({
                    "source": module_id,
                    "target": nid,
                    "relation": "contains",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source_file,
                    "weight": 1.0,
                })

                # extends edges
                supers = _get_superclasses(child)
                for sup in supers:
                    sup_id = _node_id(filestem, sup)
                    edges.append({
                        "source": nid,
                        "target": sup_id,
                        "relation": "extends",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": source_file,
                        "weight": 1.0,
                    })

                # Recurse into class body for methods
                for body_child in child.children:
                    if body_child.type in ("block", "class_body", "declaration_list",
                                           "field_declaration_list"):
                        visit_definitions(body_child, parent_class_id=nid)

    visit_definitions(root)

    # Extract imports
    def visit_imports(node):
        for child in node.children:
            if child.type in _IMPORT_TYPES:
                targets = _extract_imports(child)
                for target in targets:
                    # Create import target ID based on the imported module/name
                    target_stem = _sanitize_id(target.split(".")[-1])
                    target_id = f"{target_stem}_module"
                    edges.append({
                        "source": module_id,
                        "target": target_id,
                        "relation": "imports",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": source_file,
                        "weight": 1.0,
                    })

    visit_imports(root)

    return nodes, edges


def extract_ast(code_files: list[Path]) -> dict:
    """AST extraction via tree-sitter.

    Args:
        code_files: List of source code file paths.

    Returns:
        Dict with keys: nodes (list), edges (list), input_tokens (int), output_tokens (int).
    """
    all_nodes = []
    all_edges = []

    for file_path in code_files:
        ext = file_path.suffix.lower()
        lang = _get_language(ext)
        if lang is None:
            continue  # Skip unsupported extensions silently

        try:
            nodes, edges = _process_file(file_path, lang)
            all_nodes.extend(nodes)
            all_edges.extend(edges)
        except Exception:
            # Skip files that fail to parse
            continue

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def extract_document_structure(doc_files: list[Path]) -> dict:
    """Extract structure from document files (no LLM, 0 tokens).

    Supports: .md (headers, links, code blocks, wikilinks),
              .txt/.rst (section detection, RST underline headers),
              .pdf (pdftotext, silent skip if unavailable).

    Returns: {nodes: [], edges: [], input_tokens: 0, output_tokens: 0}
    """
    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    seen_ids: set[str] = set()

    def _add_node(node: dict) -> None:
        if node["id"] not in seen_ids:
            seen_ids.add(node["id"])
            all_nodes.append(node)

    def _add_edge(edge: dict) -> None:
        all_edges.append(edge)

    def _heading_slug(text: str) -> str:
        return re.sub(r"[^a-z0-9_]", "_", text.strip().lower()).strip("_")

    for file_path in doc_files:
        if not file_path.exists():
            continue
        ext = file_path.suffix.lower()
        source_file = str(file_path)
        filestem = _sanitize_id(file_path.stem)

        try:
            if ext == ".md":
                _parse_markdown(file_path, filestem, source_file, _add_node, _add_edge, _heading_slug)
            elif ext in (".txt", ".rst"):
                _parse_text(file_path, filestem, source_file, _add_node, _add_edge, _heading_slug, is_rst=(ext == ".rst"))
            elif ext == ".pdf":
                _parse_pdf(file_path, filestem, source_file, _add_node, _add_edge, _heading_slug)
        except Exception:
            continue

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "input_tokens": 0,
        "output_tokens": 0,
    }


_FRONTMATTER_KEY_RE = re.compile(r"^([\w_-]+)\s*:\s*(.*)$")
_FRONTMATTER_LIST_RE = re.compile(r"^\[(.*)\]$")
# Tag: any non-digit, non-underscore word char as first char (Unicode letters OK),
# followed by word chars / slashes / hyphens. Must be preceded by start-of-line or whitespace.
_INLINE_TAG_RE = re.compile(r"(?:^|\s)#([^\W\d_][\w/-]*)", re.UNICODE)
# Matches `inline code spans` to strip before scanning for tags (so #define inside
# backticks is not mistaken for a tag).
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


def _parse_frontmatter(text: str) -> tuple[dict, str, int]:
    """Parse minimal YAML frontmatter from the top of a markdown file.

    Supports:
        key: value
        key: [item1, item2]
        key:
          - item1
          - item2

    Returns (metadata_dict, remaining_text, line_offset).
    `line_offset` is the number of lines (including the closing `---`) that
    belonged to the frontmatter block, so callers can preserve real source
    line numbers after stripping. Returns ({}, original_text, 0) when no
    frontmatter is found.
    """
    if not text.startswith("---"):
        return {}, text, 0
    # Require a newline after the opening --- marker
    first_nl = text.find("\n")
    if first_nl == -1 or text[3:first_nl].strip():
        return {}, text, 0
    body = text[first_nl + 1:]
    close_match = re.search(r"^---\s*$", body, flags=re.MULTILINE)
    if not close_match:
        return {}, text, 0
    yaml_block = body[:close_match.start()]
    remaining = body[close_match.end():].lstrip("\r\n")
    # Count the lines that the frontmatter (including both `---` markers) occupied
    consumed = text[: first_nl + 1 + close_match.end()]
    line_offset = consumed.count("\n")
    # Account for the newline immediately after closing `---` that lstrip removed
    trimmed = body[close_match.end():]
    line_offset += len(trimmed) - len(trimmed.lstrip("\r\n"))

    metadata: dict = {}
    current_key: str | None = None
    for raw_line in yaml_block.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        # YAML list continuation: "  - item"
        if line.lstrip().startswith("- ") and current_key is not None:
            item = line.lstrip()[2:].strip().strip('"').strip("'")
            if not isinstance(metadata.get(current_key), list):
                metadata[current_key] = []
            if item:
                metadata[current_key].append(item)
            continue
        kv = _FRONTMATTER_KEY_RE.match(line)
        if not kv:
            continue
        key, raw_value = kv.group(1), kv.group(2).strip()
        if not raw_value:
            metadata[key] = []
            current_key = key
            continue
        inline_list = _FRONTMATTER_LIST_RE.match(raw_value)
        if inline_list:
            items = [
                part.strip().strip('"').strip("'")
                for part in inline_list.group(1).split(",")
                if part.strip()
            ]
            metadata[key] = items
        else:
            metadata[key] = raw_value.strip('"').strip("'")
        current_key = key
    return metadata, remaining, line_offset


def _extract_inline_tags(line: str) -> set[str]:
    """Extract Obsidian-style #tags from a single line of prose.

    - Supports Unicode letters (including Hangul: `#한글`, CJK, emoji-free scripts)
    - Inline code spans (`` `...` ``) are stripped first so `` `#define` `` is
      not mistaken for a tag.
    - Skips hex color codes (`#fff`, `#ffffff`) and numeric-only tags.
    - Matches at line start or after whitespace to avoid catching
      `array[#index]` or `href="#anchor"`.
    """
    # Strip inline-code spans before scanning
    scan_target = _INLINE_CODE_RE.sub(" ", line)
    tags: set[str] = set()
    for m in _INLINE_TAG_RE.finditer(scan_target):
        tag = m.group(1)
        # Hex color: 3, 4, 6, or 8 hex chars (ASCII-only so regex stays simple)
        if re.fullmatch(r"[0-9a-fA-F]{3,8}", tag):
            continue
        tags.add(tag)
    return tags


def _parse_markdown(
    file_path: Path, filestem: str, source_file: str,
    add_node, add_edge, heading_slug,
) -> None:
    """Parse markdown file for headers, links, code blocks, wikilinks.

    Obsidian-aware: strips YAML frontmatter, captures frontmatter metadata and
    inline #tags on the nearest header node.
    """
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, IOError):
        return

    # Strip YAML frontmatter (Obsidian / Jekyll / Hugo). line_offset keeps
    # source_location line numbers aligned with the original file.
    frontmatter, text, line_offset = _parse_frontmatter(text)

    lines = text.split("\n")
    # Stack of (depth, node_id) for parent-child tracking
    header_stack: list[tuple[int, str]] = []
    in_code_block = False
    code_lang = None
    current_header_id = None
    # Metadata captured for the file-level synthetic node
    pending_frontmatter: dict | None = frontmatter if frontmatter else None
    inline_tags: set[str] = set()
    # First header encountered — used for the file-level node's contains edge.
    # Capture it at creation time, NOT inferred from header_stack[0] at EOF
    # (which would be the last branch's top-level ancestor, not the first header).
    first_header_id: str | None = None

    def _line_label(idx: int) -> str:
        return f"line {line_offset + idx + 1}"

    for i, line in enumerate(lines):
        # Code block toggle
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                lang_match = re.match(r"```(\w+)", line.strip())
                code_lang = lang_match.group(1) if lang_match else None
                # Create has_code_example edge from current header
                if current_header_id and code_lang:
                    lang_node_id = f"{filestem}_{_sanitize_id(code_lang)}_lang"
                    add_node({
                        "id": lang_node_id,
                        "label": code_lang,
                        "file_type": "document",
                        "source_file": source_file,
                        "source_location": _line_label(i),
                    })
                    add_edge({
                        "source": current_header_id,
                        "target": lang_node_id,
                        "relation": "has_code_example",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": source_file,
                    })
            else:
                in_code_block = False
                code_lang = None
            continue

        if in_code_block:
            continue

        # Header detection
        header_match = re.match(r"^(#{1,6})\s+(.+)", line)
        if header_match:
            depth = len(header_match.group(1))
            title = header_match.group(2).strip()
            slug = heading_slug(title)
            if not slug:
                continue
            node_id = f"{filestem}_{slug}"
            current_header_id = node_id
            if first_header_id is None:
                first_header_id = node_id

            add_node({
                "id": node_id,
                "label": title,
                "file_type": "document",
                "source_file": source_file,
                "source_location": _line_label(i),
            })

            # Find parent: pop stack until we find a shallower depth
            while header_stack and header_stack[-1][0] >= depth:
                header_stack.pop()
            if header_stack:
                parent_id = header_stack[-1][1]
                add_edge({
                    "source": parent_id,
                    "target": node_id,
                    "relation": "contains",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source_file,
                })
            header_stack.append((depth, node_id))
            continue

        # Collect inline #tags (Obsidian-style)
        inline_tags |= _extract_inline_tags(line)

        # Markdown links [text](url)
        for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", line):
            url = m.group(2)
            # Only internal references (relative paths, no http)
            if not url.startswith("http") and not url.startswith("#"):
                target_stem = _sanitize_id(Path(url.split("#")[0]).stem)
                if target_stem and current_header_id:
                    target_id = f"{target_stem}_module"
                    add_edge({
                        "source": current_header_id,
                        "target": target_id,
                        "relation": "references",
                        "confidence": "EXTRACTED",
                        "confidence_score": 1.0,
                        "source_file": source_file,
                    })

        # Wikilinks [[target]]
        for m in re.finditer(r"\[\[([^\]]+)\]\]", line):
            target_text = m.group(1)
            target_id = f"{_sanitize_id(target_text)}_module"
            if current_header_id:
                add_edge({
                    "source": current_header_id,
                    "target": target_id,
                    "relation": "references",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": source_file,
                })

    # Post-process: if we captured frontmatter or inline #tags, emit a
    # file-level synthetic node that aggregates metadata for the whole note.
    # This node coexists with header nodes (contains edge from file → first header).
    combined_tags: set[str] = set(inline_tags)
    if pending_frontmatter:
        fm_tags = pending_frontmatter.get("tags")
        if isinstance(fm_tags, list):
            combined_tags.update(str(t) for t in fm_tags)
        elif isinstance(fm_tags, str):
            combined_tags.add(fm_tags)

    if pending_frontmatter or combined_tags:
        file_node_id = f"{filestem}_file"
        synth_node: dict = {
            "id": file_node_id,
            "label": pending_frontmatter.get("title", filestem) if pending_frontmatter else filestem,
            "file_type": "document",
            "source_file": source_file,
            "source_location": "file",
        }
        if pending_frontmatter:
            synth_node["metadata"] = pending_frontmatter
        if combined_tags:
            synth_node["tags"] = sorted(combined_tags)
        add_node(synth_node)
        # Link file node to the FIRST header ever seen (captured at creation),
        # not header_stack[0] which at EOF reflects the last branch's ancestor.
        if first_header_id is not None:
            add_edge({
                "source": file_node_id,
                "target": first_header_id,
                "relation": "contains",
                "confidence": "EXTRACTED",
                "confidence_score": 1.0,
                "source_file": source_file,
            })


def _parse_text(
    file_path: Path, filestem: str, source_file: str,
    add_node, add_edge, heading_slug, is_rst: bool = False,
) -> None:
    """Parse text/rst file for sections."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, IOError):
        return

    lines = text.split("\n")
    prev_line = None

    for i, line in enumerate(lines):
        is_header = False
        title = None

        if is_rst and prev_line and prev_line.strip():
            # RST underline headers: line of === or --- under text
            stripped = line.strip()
            if stripped and len(stripped) >= 3 and all(c == stripped[0] for c in stripped) and stripped[0] in "=-~^\"'`:._*+#":
                title = prev_line.strip()
                is_header = True

        # Uppercase line as section title (for plain .txt)
        if not is_header and not is_rst:
            stripped = line.strip()
            if stripped and stripped == stripped.upper() and len(stripped) > 3 and stripped[0].isalpha():
                # Check if surrounded by blank lines
                prev_blank = (i == 0) or (not lines[i - 1].strip())
                next_blank = (i == len(lines) - 1) or (not lines[i + 1].strip() if i + 1 < len(lines) else True)
                if prev_blank or next_blank:
                    title = stripped
                    is_header = True

        if is_header and title:
            slug = heading_slug(title)
            if slug:
                node_id = f"{filestem}_{slug}"
                add_node({
                    "id": node_id,
                    "label": title,
                    "file_type": "document",
                    "source_file": source_file,
                    "source_location": f"line {i + 1}",
                })

        prev_line = line


def _parse_pdf(
    file_path: Path, filestem: str, source_file: str,
    add_node, add_edge, heading_slug,
) -> None:
    """Parse PDF via pdftotext subprocess. Silent skip if unavailable."""
    import subprocess
    import shutil

    if not shutil.which("pdftotext"):
        return  # Silent skip

    try:
        result = subprocess.run(
            ["pdftotext", str(file_path), "-"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return
        text = result.stdout
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return

    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        # Heuristic: lines that start with uppercase/number and are short = section headers
        if len(stripped) < 80 and stripped[0].isupper() and not stripped.endswith("."):
            slug = heading_slug(stripped)
            if slug and len(slug) > 2:
                node_id = f"{filestem}_{slug}"
                add_node({
                    "id": node_id,
                    "label": stripped,
                    "file_type": "document",
                    "source_file": source_file,
                    "source_location": f"line {i + 1}",
                })


def extract_semantic(files: list[Path], cache_dir: Path) -> dict:
    """Semantic extraction (requires LLM). Uses SHA256 cache.

    Args:
        files: List of file paths to extract semantics from.
        cache_dir: Directory for SHA256-keyed cache files.

    Returns:
        Dict with keys: nodes (list), edges (list), input_tokens (int), output_tokens (int).
    """
    from mindvault.llm import detect_llm, call_llm, estimate_cost, confirm_api_usage
    from mindvault.cache import is_dirty, update_cache
    import json
    import sys

    empty = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}

    # 1. Detect LLM
    provider = detect_llm()
    if provider["provider"] is None:
        return empty

    # Shared text extractor — handles .docx/.xlsx/.pptx/.pdf via ingest helpers
    from mindvault.detect import BINARY_DOCUMENT_EXTS
    from mindvault.ingest import _extract_text_from_file

    def _read_doc(p: Path) -> str:
        ext = p.suffix.lower()
        if ext in BINARY_DOCUMENT_EXTS:
            return _extract_text_from_file(p) or ""
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except (OSError, IOError):
            return ""

    # 2. API consent check (once for the batch)
    if not provider["is_local"]:
        # Estimate total cost
        total_text = ""
        for f in files:
            if f.exists():
                total_text += _read_doc(f)
        cost = estimate_cost(total_text, provider)
        if not confirm_api_usage(provider, cost):
            return empty

    all_nodes = []
    all_edges = []
    input_tokens = 0
    output_tokens = 0

    extraction_prompt = """Extract key concepts and relationships from this text.
Return JSON only:
{
  "nodes": [{"id": "slug_name", "label": "Human Name", "file_type": "document", "source_file": "path"}],
  "edges": [{"source": "id1", "target": "id2", "relation": "references|implements|related_to", "confidence": "EXTRACTED|INFERRED", "confidence_score": 0.8}]
}

Rules:
- Extract named concepts, entities, technologies, decisions
- EXTRACTED: explicitly stated relationship
- INFERRED: reasonable inference
- Keep nodes under 30 per document
- Keep edges under 50 per document"""

    for file_path in files:
        if not file_path.exists():
            continue

        # Check cache (only process dirty files)
        if not is_dirty(file_path, cache_dir):
            continue

        text = _read_doc(file_path)

        if not text.strip():
            continue

        # Truncate to max_tokens_per_file
        from mindvault.config import get as cfg_get
        max_tokens = cfg_get("max_tokens_per_file", 4000)
        max_chars = max_tokens * 4
        if len(text) > max_chars:
            text = text[:max_chars]

        input_tokens += len(text) // 4

        # Call LLM
        response = call_llm(extraction_prompt, text, provider)
        if not response:
            continue

        output_tokens += len(response) // 4

        # Parse JSON from response
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        try:
            data = json.loads(cleaned)
            nodes = data.get("nodes", [])
            edges = data.get("edges", [])

            # Ensure required fields
            for node in nodes:
                if "source_file" not in node or not node["source_file"]:
                    node["source_file"] = str(file_path)
                if "file_type" not in node:
                    node["file_type"] = "document"

            for edge in edges:
                if "confidence" not in edge:
                    edge["confidence"] = "INFERRED"
                if "confidence_score" not in edge:
                    edge["confidence_score"] = 0.7
                if "source_file" not in edge:
                    edge["source_file"] = str(file_path)
                if "weight" not in edge:
                    edge["weight"] = 1.0

            all_nodes.extend(nodes)
            all_edges.extend(edges)

            # Update cache after successful extraction
            update_cache(file_path, cache_dir)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # JSON parse failure → skip file, don't crash
            print(f"Warning: Failed to parse LLM response for {file_path}: {e}", file=sys.stderr)
            continue

    return {
        "nodes": all_nodes,
        "edges": all_edges,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
