"""Corollary: an agent runtime where the unit of state is a belief, not a message.

Every conclusion carries its proof. Correct one fact, and everything that followed from it
updates itself.

The most used names are importable from the package root::

    from corollary import Agent, BeliefBase, rule, tool
"""

import logging

from ._version import __version__
from .agent import Agent, Dependencies, NarrowResult, Report, StepRecord
from .belief import Belief, Source, SourceKind, Status
from .changes import Change, ChangeKind, Pending, Propagation
from .conflict import Conflict, ConflictKind, Constraint, Resolution
from .contract import SYSTEM_PROMPT, Action, Answer, Cite, Claim, ToolCall, parse_response
from .errors import (
    CircularDefeatError,
    CitationError,
    ContractViolation,
    CorollaryError,
    FormulaError,
    InvalidKeyError,
    ModelError,
    ModelRefusalError,
    NotBelievedError,
    RuleError,
    UnknownBeliefError,
    UnresolvedConflictError,
    VerificationError,
)
from .justification import Justification, JustificationKind
from .kernel import BeliefBase, Derived, Event, Rederivation
from .ledger import Outcome, SourceRecord, TrustLedger
from .models import AnthropicModel, CallableModel, Model, OpenAIModel, ScriptedModel
from .projector import Projection, Projector
from .proof import Proof, ProofDiff, ProofStep
from .resolvers import AskHuman, PreferHigherConfidence, PreferNewest, PreferSource
from .rules import Rule, rule
from .tools import Tool, tool
from .trust import TrustPolicy
from .verify import CheckResult, Severity, VerificationReport, Verifier

__all__ = [
    "SYSTEM_PROMPT",
    "Action",
    "Agent",
    "Answer",
    "AnthropicModel",
    "AskHuman",
    "Belief",
    "BeliefBase",
    "CallableModel",
    "Change",
    "ChangeKind",
    "CheckResult",
    "CircularDefeatError",
    "CitationError",
    "Cite",
    "Claim",
    "Conflict",
    "ConflictKind",
    "Constraint",
    "ContractViolation",
    "CorollaryError",
    "Dependencies",
    "Derived",
    "Event",
    "FormulaError",
    "InvalidKeyError",
    "Justification",
    "JustificationKind",
    "Model",
    "ModelError",
    "ModelRefusalError",
    "NarrowResult",
    "NotBelievedError",
    "OpenAIModel",
    "Outcome",
    "Pending",
    "PreferHigherConfidence",
    "PreferNewest",
    "PreferSource",
    "Projection",
    "Projector",
    "Proof",
    "ProofDiff",
    "ProofStep",
    "Propagation",
    "Rederivation",
    "Report",
    "Resolution",
    "Rule",
    "RuleError",
    "ScriptedModel",
    "Severity",
    "Source",
    "SourceKind",
    "SourceRecord",
    "Status",
    "StepRecord",
    "Tool",
    "ToolCall",
    "TrustLedger",
    "TrustPolicy",
    "UnknownBeliefError",
    "UnresolvedConflictError",
    "VerificationError",
    "VerificationReport",
    "Verifier",
    "__version__",
    "parse_response",
    "rule",
    "tool",
]

# A library never configures logging; applications opt in with logging.getLogger("corollary").
logging.getLogger(__name__).addHandler(logging.NullHandler())
