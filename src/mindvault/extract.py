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

    # 2. API consent check (once for the batch)
    if not provider["is_local"]:
        # Estimate total cost
        total_text = ""
        for f in files:
            if f.exists():
                try:
                    total_text += f.read_text(encoding="utf-8", errors="ignore")
                except (OSError, IOError):
                    pass
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

        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, IOError):
            continue

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
