"""The projector builds every model context from ``IN`` beliefs only.

This is what makes retraction real. There is no transcript: when a belief goes ``OUT`` it is not
flagged in the context, it is absent from it. A retracted or expired fact, or a conflicted key,
can't leak into the model's next step, because the model never sees it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .belief import Belief, Status

if TYPE_CHECKING:
    from .kernel import BeliefBase
    from .tools import Tool


@dataclass(frozen=True)
class Projection:
    """A rendered context plus exactly which belief revisions it exposed.

    ``visible`` is what makes the conservative dependency policy sound: a claim generated from
    this projection can only have used these beliefs.
    """

    text: str
    visible: tuple[Belief, ...]

    @property
    def refs(self) -> tuple[str, ...]:
        return tuple(b.ref for b in self.visible)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(b.key for b in self.visible)

    def belief(self, key: str) -> Belief | None:
        for b in self.visible:
            if b.key == key:
                return b
        return None


class Projector:
    """Renders a belief base into a prompt.

    Args:
        max_beliefs: Upper bound on beliefs shown; the most confident, then most recent, win.
        min_confidence: Hide beliefs below this effective confidence. Defaults to the belief
            base's ``TrustPolicy.min_confidence``.
        max_document_chars: Truncation limit per document; the projector says when it truncates.
        show_sources: Include each belief's source in the context.
    """

    def __init__(
        self,
        *,
        max_beliefs: int = 500,
        min_confidence: float | None = None,
        max_document_chars: int = 50_000,
        show_sources: bool = True,
    ) -> None:
        self.max_beliefs = max_beliefs
        self.min_confidence = min_confidence
        self.max_document_chars = max_document_chars
        self.show_sources = show_sources

    def select(self, kb: BeliefBase, scope: Iterable[str] | None = None) -> list[Belief]:
        """The beliefs a model may see: ``IN``, unconflicted, confident enough, optionally scoped."""
        kb.refresh()
        threshold = self.min_confidence if self.min_confidence is not None else kb.trust.min_confidence
        blocked = kb.conflicted_keys()
        allowed = set(scope) if scope is not None else None
        chosen: dict[str, Belief] = {}
        for key in kb.keys(Status.IN):
            if key in blocked or (allowed is not None and key not in allowed):
                continue
            belief = kb[key]
            if kb.confidence(belief.ref) < threshold:
                continue
            chosen[key] = belief
        beliefs = list(chosen.values())
        if len(beliefs) > self.max_beliefs:
            beliefs.sort(key=lambda b: (kb.confidence(b.ref), b.created_at), reverse=True)
            beliefs = sorted(beliefs[: self.max_beliefs], key=lambda b: b.created_at)
        return beliefs

    def project(
        self,
        kb: BeliefBase,
        *,
        task: str,
        tools: Sequence[Tool] = (),
        feedback: Sequence[str] = (),
        scope: Iterable[str] | None = None,
        instructions: str = "",
        include_documents: bool = True,
    ) -> Projection:
        visible = self.select(kb, scope)
        sections = [f"# Task\n{task.strip()}"]
        if instructions:
            sections.append(f"# Instructions\n{instructions.strip()}")

        if visible:
            lines = [
                "Current beliefs. Values are authoritative; cite them by key in follows_from and as {key} in formulas."
            ]
            for b in visible:
                line = f"- {b.key} = {_render_value(b.value)}"
                details = []
                if b.claim:
                    details.append(b.claim)
                if self.show_sources:
                    details.append(f"source: {b.source}")
                details.append(f"confidence: {kb.confidence(b.ref):.2f}")
                lines.append(line + "  | " + " | ".join(details))
            sections.append("# Beliefs\n" + "\n".join(lines))
        else:
            sections.append("# Beliefs\n(none yet)")

        conflicts = [c for c in kb.conflicts() if scope is None or set(c.keys) & set(scope)]
        if conflicts:
            lines = ["These keys are disputed and unusable until resolved:"]
            lines += [f"- {c.subject}: {c.description.split(' (')[0]}" for c in conflicts]
            sections.append("# Conflicts\n" + "\n".join(lines))

        if tools:
            sections.append("# Tools\n" + "\n".join(f"- {t.describe()}" for t in tools))

        if include_documents and kb.documents:
            parts = []
            for name, text in kb.documents.items():
                body = text
                if len(body) > self.max_document_chars:
                    body = (
                        body[: self.max_document_chars] + f"\n[... truncated at {self.max_document_chars} characters]"
                    )
                parts.append(f"## {name}\n{body}")
            sections.append("# Documents\n" + "\n\n".join(parts))

        if feedback:
            sections.append(
                "# Runtime feedback\nYour previous response had problems:\n" + "\n".join(f"- {f}" for f in feedback)
            )
        return Projection(text="\n\n".join(sections) + "\n", visible=tuple(visible))


def _render_value(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return repr(value)
