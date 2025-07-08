from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Protocol, TypeGuard, TypeVar

import pandas as pd

ScoreType = TypeVar("ScoreType", float, pd.Series)


@dataclass
class ScoreFloatPair(Generic[ScoreType]):
    """
    Group the counts of strong and weak votes to have less variables to pass around.
    """

    weak: ScoreType
    strong: ScoreType

    def add(self, other: ScoreFloatPair) -> ScoreFloatPair:
        return ScoreFloatPair(
            weak=self.weak + other.weak,
            strong=self.strong + other.strong,
        )

    def divide(self, other: float) -> ScoreFloatPair:
        return ScoreFloatPair(
            weak=self.weak / other,
            strong=self.strong / other,
        )


def is_vectorised_pair(val: object) -> TypeGuard[ScoreFloatPair[pd.Series]]:
    """Determines whether all objects in the list are strings"""
    return (
        isinstance(val, ScoreFloatPair)
        and isinstance(val.weak, pd.Series)
        and isinstance(val.strong, pd.Series)
    )


class ScoringFuncProtocol(Protocol, Generic[ScoreType]):
    """
    Set a protocol for scoring functions to validate
    correct order of arguments and return type.
    """

    @staticmethod
    def score(
        *,
        votes_same: ScoreFloatPair[ScoreType],
        votes_different: ScoreFloatPair[ScoreType],
        votes_absent: ScoreFloatPair[ScoreType],
        votes_abstain: ScoreFloatPair[ScoreType],
        agreements_same: ScoreFloatPair[ScoreType],
        agreements_different: ScoreFloatPair[ScoreType],
    ) -> ScoreType: ...


ScoringFuncType = TypeVar("ScoringFuncType", bound=ScoringFuncProtocol)


class SimplifiedScore(ScoringFuncProtocol, Generic[ScoreType]):
    @staticmethod
    def score(
        *,
        votes_same: ScoreFloatPair[ScoreType],
        votes_different: ScoreFloatPair[ScoreType],
        votes_absent: ScoreFloatPair[ScoreType],
        votes_abstain: ScoreFloatPair[ScoreType],
        agreements_same: ScoreFloatPair[ScoreType],
        agreements_different: ScoreFloatPair[ScoreType],
    ) -> ScoreType:
        """
        This is a simplified version of the public whip scoring system.
        Weak weight votes are 'informative' only, and have no score.

        Absences do not move the needle - but do impose a cap on the most extreme scores.
        More than 1 strong absence prevents a score of 0.05 or 0.95 plus.
        More than 1/3 strong absences prevents a score of 0.15 or 0.85 plus.
        Abstensions are recorded as present - but half the value of a weak vote.

        Strong agreements are counted the same as votes.

        """

        vote_weight = ScoreFloatPair(weak=0.0, strong=10.0)
        agreement_weight = vote_weight
        abstain_total_weight = vote_weight
        abstain_weight = vote_weight.divide(2)  # abstain is half marks
        absence_weight = ScoreFloatPair(
            weak=0.0, strong=0.0
        )  # absences are worth nothing
        absence_total_weight = ScoreFloatPair(weak=0.0, strong=0.0)  # out of nothing

        points = (
            vote_weight.weak * votes_different.weak
            + vote_weight.strong * votes_different.strong
            + absence_weight.weak * votes_absent.weak
            + absence_weight.strong * votes_absent.strong
            + abstain_weight.weak * votes_abstain.weak
            + abstain_weight.strong * votes_abstain.strong
            + agreement_weight.weak * agreements_different.weak
            + agreement_weight.strong * agreements_different.strong
        )

        avaliable_points = (
            vote_weight.weak * (votes_same.weak + votes_different.weak)
            + vote_weight.strong * (votes_same.strong + votes_different.strong)
            + agreement_weight.weak * (agreements_same.weak + agreements_different.weak)
            + agreement_weight.strong
            * (agreements_same.strong + agreements_different.strong)
            + absence_total_weight.weak * votes_absent.weak
            + absence_total_weight.strong * votes_absent.strong
            + abstain_total_weight.weak * votes_abstain.weak
            + abstain_total_weight.strong * votes_abstain.strong
        )

        total = (
            votes_same.strong
            + votes_different.strong
            + votes_absent.strong
            + votes_abstain.strong
        )

        if (
            isinstance(points, pd.Series)
            and isinstance(avaliable_points, pd.Series)
            and isinstance(votes_absent.strong, pd.Series)
            and isinstance(total, pd.Series)
        ):
            score = points / avaliable_points

            # where more than one strong absence prevents a score of 0.05 or 0.95
            score = score.where(
                ~(votes_absent.strong > 1), score.clip(lower=0.06, upper=0.94)
            )

            # if more than one-third absent vote cap the score to prevent an 'almost always'
            score = score.where(
                ~(votes_absent.strong >= total / 3),
                score.clip(lower=0.16, upper=0.84),
            )

            # any inf scores should be -1
            return score.where(avaliable_points != 0, -1)

        elif (
            isinstance(points, float)
            and isinstance(avaliable_points, float)
            and isinstance(votes_absent.strong, float)
            and isinstance(total, float)
        ):
            if avaliable_points == 0:
                return -1.0

            score = points / avaliable_points

            # here we are using the absences as a way of capping the descriptions avaliable
            # we do this rather than give scores because we don't want more absences to drive to the middle of the roaedll
            # but do want to avoid language that suggests a lack of absences in the underlying votes.
            # the cap reflects where twfy switches its language.

            # if more than one absent vote cap the score to prevent a 'consistently'
            if votes_absent.strong > 1:
                if score <= 0.05:
                    score = 0.06
                elif score >= 0.95:
                    score = 0.94

            # if more than one-third absent vote cap the score to prevent an 'almost always'
            if votes_absent.strong > 0 and votes_absent.strong >= total / 3:
                if score <= 0.15:
                    score = 0.16
                elif score >= 0.85:
                    score = 0.84

            return score
        else:
            raise ValueError("Something's wrong with typing!")
