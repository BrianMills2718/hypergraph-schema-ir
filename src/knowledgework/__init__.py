"""knowledgework: one declared model in, backend schemas and an honest verdict out."""

from __future__ import annotations

from .constraints import ConstraintVerdict
from .constraints import Verdict
from .constraints import evaluate_constraints
from .constraints import render_verdict_report
from .errors import DuplicateNameError
from .errors import DuplicateVertexTypeError
from .errors import KnowledgeworkError
from .errors import ParseError
from .errors import UnknownVertexTypeError
from .model import Constraint
from .model import Hyperedge
from .model import Model
from .model import Operation
from .model import ResolvedModel
from .model import VertexSet
from .parser import parse_file
from .parser import parse_source
from .resolve import resolve_model

__version__ = "0.1.0.dev0"

__all__ = [
    "Constraint",
    "ConstraintVerdict",
    "DuplicateNameError",
    "DuplicateVertexTypeError",
    "Hyperedge",
    "KnowledgeworkError",
    "Model",
    "Operation",
    "ParseError",
    "ResolvedModel",
    "UnknownVertexTypeError",
    "Verdict",
    "VertexSet",
    "__version__",
    "evaluate_constraints",
    "parse_file",
    "parse_source",
    "render_verdict_report",
    "resolve_model",
]
