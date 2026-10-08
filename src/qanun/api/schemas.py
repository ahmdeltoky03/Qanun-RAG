from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(..., max_length=4000, examples=["ما هي شروط صحة العقد؟"])

    @field_validator("question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        return v


class SourceDetail(BaseModel):
    article_number: int
    citation: str
    score: float
    is_repealed: bool
    chapter: str = ""
    section: str = ""
    text_ar: str = ""
    text_en: str = ""


class AskResponse(BaseModel):
    answer: str
    sources: list[str] = Field(description="Article labels such as 'المادة 147' / 'Article 147' - never chunk ids")
    source_details: list[SourceDetail] = []
    flags: list[str] = []
    out_of_scope: bool = False
    blocked: bool = False
    trace_id: str = ""
    latency_ms: float = 0.0


class HealthResponse(BaseModel):
    status: str
    documents_indexed: int
    release: str
    embedding_model: str
    llm_model: str
    tracing: bool
