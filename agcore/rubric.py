"""
Rubric data model. A rubric is a list of items with point values; each item
carries a checker callable (provided by the lab-specific config) that
inspects the parsed-up submission and reports points earned plus a free-form
note. The checker also flags severity, which the report module uses to pick
red shades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional


# Severity ladder for colour shading on the rubric and elsewhere.
SEVERITY_NONE = 0     # Full credit, no concern.
SEVERITY_MINOR = 1    # Lost a point or two, generally cosmetic.
SEVERITY_MEDIUM = 2   # Lost a chunk; reviewer should look.
SEVERITY_MAJOR = 3    # Functional failure; clearly broken.


@dataclass
class CheckResult:
    """The outcome of grading one rubric item."""

    earned: float
    notes: str = ""
    severity: int = SEVERITY_NONE


@dataclass
class RubricItem:
    """One row on the peer-review checkoff sheet."""

    code: str             # Short stable id, e.g. "ast-classes"
    description: str      # The exact text from the peer review sheet.
    points: float         # Points possible.
    # The checker takes the orchestrator's GradedSubmission and returns CheckResult.
    checker: Callable[["Any"], CheckResult]
    # Optional category for grouping in the PDF (e.g. "Documentation").
    category: str = "General"

    def grade(self, submission: "Any") -> "GradedItem":
        """Run the checker and wrap the outcome in a GradedItem."""
        result = self.checker(submission)
        earned = max(0.0, min(self.points, result.earned))
        return GradedItem(item=self, earned=earned, notes=result.notes,
                          severity=result.severity)


@dataclass
class GradedItem:
    """A rubric item paired with the score the student received on it."""

    item: RubricItem
    earned: float
    notes: str
    severity: int

    @property
    def passed(self) -> bool:
        """True iff the student earned full credit on this item."""
        return self.earned >= self.item.points
