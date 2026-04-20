"""
Parses a student's Java sources into structured class/method records with
their javadoc comments attached. Uses the `javalang` parser for the Java AST
and a light regex pass over the source text to pull out the preceding /** ... */
javadoc block for each declaration.

We intentionally avoid relying on javalang's own doc attribute, which is
brittle on malformed student code. Instead we snapshot the raw source lines
before each declaration and hunt backwards for the nearest /** */ block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import javalang


JAVADOC_BLOCK_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)


@dataclass
class JavadocTag:
    """One @-tag inside a javadoc block, e.g. @param name description."""

    tag: str          # "@param", "@return", etc. (leading @ included)
    arg: str = ""     # optional arg (e.g. the param name)
    text: str = ""    # description text


@dataclass
class Javadoc:
    """Parsed javadoc block: prose description + tagged sections."""

    description: str = ""
    tags: List[JavadocTag] = field(default_factory=list)

    def tags_named(self, tag: str) -> List[JavadocTag]:
        """All tags matching the given @tag, case-sensitive."""
        return [t for t in self.tags if t.tag == tag]

    def plain_text(self) -> str:
        """Flatten the full javadoc (description + tag text) for keyword scoring."""
        parts = [self.description]
        parts.extend(f"{t.arg} {t.text}" for t in self.tags)
        return " ".join(p for p in parts if p).lower()


@dataclass
class MethodRecord:
    """One method in a student's source file."""

    class_name: str
    method_name: str
    params: List[str]            # parameter names, in order
    return_type: str             # "void" if no return
    javadoc: Optional[Javadoc]   # None if the method has no javadoc
    line: int                    # line number of the declaration
    file: str                    # path to the source file (relative)


@dataclass
class ClassRecord:
    """One top-level or inner class/interface in a student's source file."""

    name: str
    superclass: Optional[str]
    interfaces: List[str]
    javadoc: Optional[Javadoc]
    line: int
    file: str
    methods: List[MethodRecord] = field(default_factory=list)


def parse_tree(compiler_root: Path) -> List[ClassRecord]:
    """Walk every .java file under compiler_root and return the class records.

    Parse failures are caught per-file: a file with a syntax error contributes
    no classes but doesn't sink the whole traversal.
    """
    records: List[ClassRecord] = []
    for java_file in sorted(compiler_root.rglob("*.java")):
        try:
            records.extend(_parse_file(java_file, compiler_root))
        except (javalang.parser.JavaSyntaxError, javalang.tokenizer.LexerError,
                Exception):
            # Skip unparseable files. The checkstyle/test-runner passes still
            # catch the failure elsewhere.
            continue
    return records


def _parse_file(path: Path, compiler_root: Path) -> List[ClassRecord]:
    """Parse one Java file into zero or more ClassRecords."""
    source = path.read_text(encoding="utf-8", errors="replace")
    lines = source.splitlines()
    tree = javalang.parse.parse(source)
    rel = str(path.relative_to(compiler_root))

    class_records: List[ClassRecord] = []
    class_types = (javalang.tree.ClassDeclaration,
                   javalang.tree.InterfaceDeclaration)
    # `tree.filter()` takes a single class -- iterate each type separately.
    nodes = []
    for cls_type in class_types:
        nodes.extend(tree.filter(cls_type))
    for _, node in nodes:
        line = node.position.line if node.position else 1
        cls_doc = _javadoc_before(lines, line - 1)
        superclass = None
        if isinstance(node, javalang.tree.ClassDeclaration) and node.extends:
            superclass = node.extends.name
        interfaces: List[str] = []
        if isinstance(node, javalang.tree.ClassDeclaration) and node.implements:
            interfaces = [iface.name for iface in node.implements]
        cls_record = ClassRecord(
            name=node.name, superclass=superclass, interfaces=interfaces,
            javadoc=cls_doc, line=line, file=rel, methods=[]
        )
        for method_node in list(node.methods) + list(
                getattr(node, "constructors", [])):
            m_line = method_node.position.line if method_node.position else line
            doc = _javadoc_before(lines, m_line - 1)
            if isinstance(method_node, javalang.tree.ConstructorDeclaration):
                ret = node.name
                mname = node.name
            else:
                ret = _type_name(method_node.return_type)
                mname = method_node.name
            params = [p.name for p in method_node.parameters]
            cls_record.methods.append(MethodRecord(
                class_name=node.name, method_name=mname, params=params,
                return_type=ret, javadoc=doc, line=m_line, file=rel,
            ))
        class_records.append(cls_record)
    return class_records


def _type_name(return_type) -> str:
    """Render a javalang return-type node as a plain string."""
    if return_type is None:
        return "void"
    if hasattr(return_type, "name"):
        return return_type.name
    return str(return_type)


def _javadoc_before(lines: List[str], decl_line_idx: int) -> Optional[Javadoc]:
    """Scan upwards from decl_line_idx for the nearest /** ... */ block.

    We stop at the nearest non-blank, non-annotation, non-comment line that
    isn't part of a javadoc -- if we hit code before we see a javadoc, the
    declaration has no doc.
    """
    i = decl_line_idx - 1
    # Skip annotations (@Override etc.) and blank lines.
    while i >= 0 and (not lines[i].strip() or lines[i].lstrip().startswith("@")):
        i -= 1
    if i < 0:
        return None
    # Must end with */ to be a javadoc closer.
    if not lines[i].rstrip().endswith("*/"):
        return None
    # Walk back to the opener.
    end = i
    while i >= 0 and "/**" not in lines[i]:
        i -= 1
    if i < 0:
        return None
    block = "\n".join(lines[i: end + 1])
    return _parse_javadoc(block)


def _parse_javadoc(block: str) -> Javadoc:
    """Turn a /** ... */ block into a Javadoc record."""
    inner_match = JAVADOC_BLOCK_RE.search(block)
    inner = inner_match.group(1) if inner_match else block
    # Normalise: drop leading "*" on each line and trim.
    cleaned_lines = []
    for raw in inner.splitlines():
        s = raw.strip()
        if s.startswith("*"):
            s = s[1:].lstrip()
        cleaned_lines.append(s)
    description_parts: List[str] = []
    tags: List[JavadocTag] = []
    current: Optional[JavadocTag] = None
    for line in cleaned_lines:
        if line.startswith("@"):
            if current is not None:
                tags.append(current)
            parts = line.split(None, 2)
            tag = parts[0]
            if tag in ("@param", "@throws", "@exception"):
                arg = parts[1] if len(parts) > 1 else ""
                text = parts[2] if len(parts) > 2 else ""
            else:
                arg = ""
                text = line[len(tag):].strip()
            current = JavadocTag(tag=tag, arg=arg, text=text)
        else:
            if current is None:
                description_parts.append(line)
            else:
                current.text = (current.text + " " + line).strip()
    if current is not None:
        tags.append(current)
    description = " ".join(p for p in description_parts if p).strip()
    return Javadoc(description=description, tags=tags)
