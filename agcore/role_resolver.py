"""
Role-based class + method resolution for lab-agnostic rubric checks.

The Procedures peer-review rubric names specific classes ("ProcedureCall",
"ProcedureDeclaration", "Environment", "Program", "Parser") and methods
("exec", "eval", "declareVariable", "setVariable", "getVariable",
"parseProgram", "parseProcedureDeclaration", "parseFactor"). Most students
follow those names, but a few inevitably rename things -- ProcedureDecl,
Call, Env, parseProc, declareVar -- and a human grading the peer review
would still recognise the renamed class as fulfilling the same ROLE. This
module reproduces that mental step so the autograder does not zero out
otherwise-correct submissions for a stylistic rename.

How resolution works
====================
Each lab supplies a dict of RoleSpecs (class_roles) and a dict of
method-alias tuples (method_aliases). For every role the resolver scores
every parsed ClassRecord on a weighted mix of signals and picks the
winner:

    (a) exact name match of spec.preferred_name           +10
    (b) alias name match                                   +6
    (c) token-containment (all tokens in one alternative) +4
    (d) structural: expected superclass                   +3
    (e) structural: has at least one required method      +2
    (f) file lives in spec.preferred_dir                  +1

A candidate must clear MIN_ACCEPT_SCORE to be returned; otherwise we
return None (missing class). Method resolution is simpler: a flat list of
acceptable names, first hit wins.

This module is intentionally generic. The Procedures-lab specific
RoleSpec dict lives in autograders/ag-procedures/config.py; a new lab
provides its own dict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# Minimum weighted score a candidate must reach to be accepted as matching
# a role. A class that only matches on preferred_dir alone (score 1) will
# NOT be returned -- we would rather admit "no such class" than hand back a
# false positive.
MIN_ACCEPT_SCORE = 4


@dataclass
class RoleSpec:
    """What the rubric thinks a class should look like.

    @param preferred_name the canonical name used in the rubric text
    @param aliases alternative names students commonly use
    @param name_tokens list of token-sets; a class name wins the token test
                       if its lowercased name contains ALL tokens of ANY set.
                       Example for "ProcedureDeclaration":
                         [("procedure", "decl"), ("proc", "decl")]
                       matches "ProcedureDecl", "ProcDeclaration", etc.
    @param superclass the expected superclass name, or None to skip this
                      signal
    @param required_methods at least one of these must be present for the
                            structural arm to award its points
    @param preferred_dir directory name under the Compiler root where this
                         class typically lives (e.g. "ast", "environment"),
                         used as a tie-break signal
    """
    preferred_name: str
    aliases: Sequence[str] = ()
    name_tokens: Sequence[Sequence[str]] = ()
    superclass: Optional[str] = None
    required_methods: Sequence[str] = ()
    preferred_dir: Optional[str] = None


def resolve_class_role(classes: Sequence, spec: RoleSpec):
    """Return the ClassRecord that best matches spec, or None.

    @param classes iterable of ClassRecord (from javadoc_parser.parse_tree)
    @param spec the RoleSpec describing what we are looking for
    @return the highest-scoring ClassRecord, or None if the best candidate
            scored below MIN_ACCEPT_SCORE
    @postcondition tie between two candidates resolves to whichever lives
                   in spec.preferred_dir; then to whichever appeared first
                   in traversal order (the sort in parse_tree is stable)
    """
    best = None
    best_score = MIN_ACCEPT_SCORE - 1
    best_pref = False
    for cls in classes:
        score = _score_class(cls, spec)
        if score <= best_score:
            if score < best_score:
                continue
            # tie: prefer the one in the expected directory
            pref = _in_preferred_dir(cls, spec)
            if pref and not best_pref:
                best, best_pref = cls, True
            continue
        best = cls
        best_score = score
        best_pref = _in_preferred_dir(cls, spec)
    return best


def resolve_method(cls, method_aliases: Sequence[str]):
    """Return the first MethodRecord on cls whose name matches any alias.

    Case-sensitive on purpose -- Java is case-sensitive and `declareVariable`
    really is different from `DeclareVariable`. Students using idiosyncratic
    casing should be flagged, not silently matched.

    @param cls a ClassRecord, or None (returns None immediately)
    @param method_aliases ordered sequence of acceptable method names; the
                          first hit wins so callers should put the rubric's
                          preferred name first.
    @return the matching MethodRecord or None
    """
    if cls is None:
        return None
    for alias in method_aliases:
        for m in cls.methods:
            if m.method_name == alias:
                return m
    return None


def _score_class(cls, spec: RoleSpec) -> int:
    """Weighted score of one class against a role spec. Higher is better."""
    score = 0
    name = cls.name
    name_lower = name.lower()

    if name == spec.preferred_name:
        score += 10
    elif name in spec.aliases:
        score += 6

    # Token containment: at least one alternative's tokens must ALL appear.
    for token_set in spec.name_tokens:
        if all(tok.lower() in name_lower for tok in token_set):
            score += 4
            break

    # Structural signals.
    if spec.superclass and cls.superclass == spec.superclass:
        score += 3
    if spec.required_methods:
        present = {m.method_name for m in cls.methods}
        if any(rm in present for rm in spec.required_methods):
            score += 2

    if _in_preferred_dir(cls, spec):
        score += 1
    return score


def _in_preferred_dir(cls, spec: RoleSpec) -> bool:
    """True iff cls.file lives under spec.preferred_dir (e.g. 'ast/Foo.java')."""
    if not spec.preferred_dir:
        return False
    # file is stored as a relative path like "ast/ProcedureCall.java".
    head = cls.file.split("/", 1)[0] if "/" in cls.file else ""
    return head == spec.preferred_dir
