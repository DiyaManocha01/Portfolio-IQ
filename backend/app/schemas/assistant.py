from pydantic import BaseModel, Field


class AssistantQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AssistantAnswer(BaseModel):
    answer: str
    sources_used: list[str]
    guardrail_tripped: bool
    guardrail_matched_phrase: str | None
    model: str
    disclaimer: str
