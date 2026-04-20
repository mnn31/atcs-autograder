"""
Keyword-proximity scoring for student javadocs.

For each method or class the lab-specific config supplies a set of expected
keywords ("the doc should mention the procedure being registered in the
environment..."). We flatten the javadoc to lowercase text and count
stem-based matches. We deliberately use simple lowercase substring matching
rather than spaCy/NLTK -- the goal is flexibility, not ML-accurate semantic
matching.

Thresholds live next to the keyword sets in each lab's config module so the
grader stays reusable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

from .javadoc_parser import Javadoc, MethodRecord, ClassRecord


STEM_SUFFIXES = ("ing", "ed", "es", "s", "ly", "ion", "tion", "ation")


def _stem(word: str) -> str:
    """Very-lightweight stemmer: trim common English suffixes."""
    w = word.lower()
    for suf in STEM_SUFFIXES:
        if len(w) > len(suf) + 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _normalise(text: str) -> List[str]:
    """Tokenise and stem a string for keyword matching."""
    return [_stem(tok) for tok in re.findall(r"[A-Za-z]+", text.lower())]


@dataclass
class ProximityFinding:
    """The outcome of proximity-checking one doc against one keyword set."""

    target: str              # "ClassName.methodName" or "ClassName (class)"
    file: str
    line: int
    expected: List[str]
    matched: List[str]       # Keywords (stems) that appeared
    missing: List[str]       # Keywords (stems) that did NOT appear
    threshold: int           # Minimum hits required to pass
    passed: bool
    missing_tags: List[str] = field(default_factory=list)
    note: str = ""           # Short human-readable verdict

    @property
    def severity(self) -> int:
        """Heuristic severity score 0..3 used for colour shading.

        0 = clean, 1 = minor miss, 2 = missing tags or many keywords,
        3 = completely undocumented.
        """
        if self.passed and not self.missing_tags:
            return 0
        if self.note == "missing javadoc":
            return 3
        score = 0
        if not self.passed:
            deficit = self.threshold - len(self.matched)
            score += min(2, max(1, deficit))
        if self.missing_tags:
            score += 1
        return min(3, score)


def check_method(
    method: MethodRecord,
    expected: Sequence[str],
    threshold: int,
    require_return: bool = True,
) -> ProximityFinding:
    """Score one method's javadoc against an expected keyword set.

    Args:
        method: the method record to audit.
        expected: keywords the doc ought to mention.
        threshold: minimum number of keywords (post-stem) required.
        require_return: if True and the method's return type isn't void, an
            @return tag is required.

    Returns a ProximityFinding ready to drop into the report.
    """
    expected_stems = [_stem(w) for w in expected]
    target = f"{method.class_name}.{method.method_name}"
    if method.javadoc is None:
        return ProximityFinding(
            target=target, file=method.file, line=method.line,
            expected=list(expected), matched=[], missing=list(expected_stems),
            threshold=threshold, passed=False,
            missing_tags=_expected_tags(method, require_return),
            note="missing javadoc",
        )
    return _score_doc(method.javadoc, target, method.file, method.line,
                      expected_stems, list(expected), threshold,
                      _expected_tags(method, require_return),
                      method_params=method.params, method_ret=method.return_type,
                      require_return=require_return)


def check_class(
    cls: ClassRecord,
    expected: Sequence[str],
    threshold: int,
    required_tags: Iterable[str] = ("@author", "@version"),
) -> ProximityFinding:
    """Score one class's header javadoc."""
    expected_stems = [_stem(w) for w in expected]
    target = f"{cls.name} (class)"
    if cls.javadoc is None:
        return ProximityFinding(
            target=target, file=cls.file, line=cls.line,
            expected=list(expected), matched=[], missing=list(expected_stems),
            threshold=threshold, passed=False,
            missing_tags=list(required_tags), note="missing class javadoc",
        )
    missing_tags = [t for t in required_tags
                    if not cls.javadoc.tags_named(t)]
    return _score_doc(cls.javadoc, target, cls.file, cls.line,
                      expected_stems, list(expected), threshold,
                      missing_tags, method_params=None,
                      method_ret="", require_return=False)


def _expected_tags(method: MethodRecord, require_return: bool) -> List[str]:
    """Tags that SHOULD appear in this method's javadoc given its signature.

    Constructors (detected by method_name == class_name) never require
    @return -- they don't have one.
    """
    tags: List[str] = []
    if method.params:
        tags.extend(["@param"] * len(method.params))
    is_ctor = method.method_name == method.class_name
    if (require_return and not is_ctor
            and method.return_type not in ("void", "")):
        tags.append("@return")
    return tags


def _score_doc(
    javadoc: Javadoc,
    target: str,
    file: str,
    line: int,
    expected_stems: List[str],
    expected_original: List[str],
    threshold: int,
    required_tags: List[str],
    method_params: list[str] | None,
    method_ret: str,
    require_return: bool,
) -> ProximityFinding:
    text_tokens = set(_normalise(javadoc.plain_text()))
    matched = [kw for kw in expected_stems if kw in text_tokens]
    missing = [kw for kw in expected_stems if kw not in text_tokens]

    # Tag accounting: each @param in javadoc cancels one required @param slot;
    # likewise @return. Extra @params beyond the method signature are tolerated.
    remaining_required: List[str] = []
    available_tags = list(javadoc.tags)
    for req in required_tags:
        found_idx = next(
            (i for i, t in enumerate(available_tags) if t.tag == req), None
        )
        if found_idx is None:
            remaining_required.append(req)
        else:
            available_tags.pop(found_idx)

    # Even if the tag count matches, a @param with a bogus arg name is still
    # "present"; we do not (yet) cross-check arg names. This keeps us lenient.
    passed = len(matched) >= threshold and not remaining_required
    note = ""
    if not passed:
        if len(matched) < threshold:
            note = f"only {len(matched)}/{threshold} keywords matched"
        elif remaining_required:
            note = f"missing tags: {', '.join(remaining_required)}"
    return ProximityFinding(
        target=target, file=file, line=line,
        expected=expected_original, matched=matched, missing=missing,
        threshold=threshold, passed=passed,
        missing_tags=remaining_required, note=note,
    )
