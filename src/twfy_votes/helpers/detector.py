import re
from typing import Callable, Literal, NewType, Protocol, Union

from pydantic import BaseModel, field_validator

LowerStr = NewType("LowerStr", str)
Checker = Callable[[str], bool]


class Stringifiable(Protocol):
    def __str__(self) -> str: ...


def process_text(text: str) -> LowerStr:
    return LowerStr(text.lower().strip())


class PhraseDetector(BaseModel):
    criteria: list[Union[str, re.Pattern, Checker]]
    operator: Literal["and", "or"] = "or"

    @field_validator("criteria")
    def ensure_lower(cls, v: str):
        new_criteria = []
        for criterion in v:
            if isinstance(criterion, str):
                new_criteria.append(criterion.lower())
            else:
                new_criteria.append(criterion)
        return new_criteria

    def score_criterion(
        self,
        criterion: Union[str, re.Pattern, Checker],
        text: str,
        lower_text: str,
        lower_no_space: str,
    ) -> bool:
        if isinstance(criterion, str):
            if " " in criterion:
                strip_space = criterion.replace(" ", "")
                if strip_space in lower_no_space:
                    return True
            if criterion in lower_text:
                return True
        elif isinstance(criterion, re.Pattern):
            if criterion.search(lower_text):
                return True
        elif isinstance(criterion, ComplexPhrase):
            if criterion.score(lower_text):
                return True
        elif callable(criterion):
            if criterion(text):
                return True
        return False

    def score(self, text: str) -> bool:
        lower_text = process_text(text)
        lower_no_space = lower_text.replace(" ", "")
        for criterion in self.criteria:
            value = self.score_criterion(criterion, text, lower_text, lower_no_space)
            if self.operator == "or" and value:
                return True
            elif self.operator == "and" and not value:
                return False
        if self.operator == "or":
            return False
        return True

    def __call__(self, text: Union[str, Stringifiable]) -> bool:
        txt = str(text).replace("\xa0", " ")
        return self.score(txt)

    def __hash__(self):
        return hash((tuple(self.criteria), self.operator))

    def __eq__(self, other):
        if not isinstance(other, PhraseDetector):
            return NotImplemented
        return self.criteria == other.criteria and self.operator == other.operator


class AndPhraseDetector(PhraseDetector):
    operator: Literal["and"] = "and"

    def __hash__(self):
        return hash((tuple(self.criteria), self.operator))


class ComplexPhrase(BaseModel):
    """
    This can be used recursively because it accepts a string and returns a boolean
    As in, it can be used as a criterion in PhraseDetector.
    Basically - if the positive phrase is present and the negative phrase is not present, return True
    """

    positive: PhraseDetector
    negative: PhraseDetector

    def score(self, text: str) -> bool:
        return self.positive.score(text) and not self.negative.score(text)

    def __call__(self, text: Union[str, Stringifiable]) -> bool:
        return self.score(str(text))
