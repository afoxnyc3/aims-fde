"""Contract for the question-answering endpoint (TC3).

A second contract beside schema.py, not a change to it. Request/Response
there take one ticket and return one access recommendation; this takes a
question and returns an answer grounded in named records. See decisions.md
(Week 3) for why the Week 1 contract was not stretched to fit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QuestionRequest(BaseModel):
    """One question from a Technology Support Associate."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(
        min_length=1, max_length=2000,
        description="The question in plain language, for example which clubs give a Lifeguard a staff login.",
    )


class ToolStep(BaseModel):
    """One retrieval call, kept so a reader can see how the answer was found."""

    tool: str = Field(description="The retrieval tool called, such as search_chunks.")
    args: dict = Field(description="The arguments the model passed to it.")
    chars: int = Field(description="Characters of evidence the call returned.")


class RetrievalTrace(BaseModel):
    """How the answer was found: enough to audit it without rerunning it."""

    technique: str = Field(description="The retrieval technique that produced the answer.")
    model: str = Field(description="The answer model.")
    steps: list[ToolStep] = Field(description="Every retrieval call, in order.")
    evidence_chars: int = Field(description="Total characters of evidence the model read.")
    latency_s: float = Field(description="Wall-clock seconds for retrieval and answering.")
    stopped: str = Field(description="'answer' if the model finished; 'max_turns' if the turn budget ran out.")


class QuestionAnswer(BaseModel):
    """An answer that names its sources, or an explicit decline. Never an unsourced answer."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(description="The question, copied from the request.")
    declined: bool = Field(
        description=(
            "True when the records do not support an answer: the model said so, the turn budget "
            "ran out, or the answer cited no real record."
        )
    )
    answer: str | None = Field(
        default=None, description="The answer, with record names in square brackets. Null when declined."
    )
    sources: list[str] = Field(
        default_factory=list,
        description=(
            "Every record the answer cites, by page name (SYN-* tickets, STD-* standard pages). "
            "Only names that exist in the corpus. At least one when answered; may be empty when declined."
        ),
    )
    decline_reason: str | None = Field(
        default=None, description="Why there is no answer, in one line. Null when answered."
    )
    dropped_citations: list[str] = Field(
        default_factory=list,
        description="Record names the model cited that do not exist. Removed from sources; a sign of guessing.",
    )
    trace: RetrievalTrace = Field(description="How the answer was found.")

    @model_validator(mode="after")
    def _answer_matches_decline(self) -> QuestionAnswer:
        """An answer must carry sources; a decline carries a reason and no answer."""
        if self.declined:
            if self.answer is not None or not self.decline_reason:
                raise ValueError("a decline has a reason and no answer")
        elif self.answer is None or not self.sources or self.decline_reason is not None:
            raise ValueError("an answer needs at least one source and no decline reason")
        return self
