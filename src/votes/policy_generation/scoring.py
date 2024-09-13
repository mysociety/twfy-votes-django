from __future__ import annotations

from typing import NamedTuple, Protocol


class ScoreFloatPair(NamedTuple):
    """
    Group the counts of strong and weak votes to have less variables to pass around.
    """

    weak: float
    strong: float

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


class ScoringFuncProtocol(Protocol):
    """
    Set a protocol for scoring functions to validate
    correct order of arguments and return type.
    """

    @staticmethod
    def score(
        *,
        votes_same: ScoreFloatPair,
        votes_different: ScoreFloatPair,
        votes_absent: ScoreFloatPair,
        votes_abstain: ScoreFloatPair,
        agreements_same: ScoreFloatPair,
        agreements_different: ScoreFloatPair,
    ) -> float: ...


class PublicWhipScore(ScoringFuncProtocol):
    @staticmethod
    def score(
        *,
        votes_same: ScoreFloatPair,
        votes_different: ScoreFloatPair,
        votes_absent: ScoreFloatPair,
        votes_abstain: ScoreFloatPair,
        agreements_same: ScoreFloatPair,
        agreements_different: ScoreFloatPair,
    ) -> float:
        """
        Calculate the classic Public Whip score for a difference between two MPs.

        The score is a number between 0 and 1, where 0 is a perfect match and 1 is a perfect
        mismatch. Returns -1 if there are no votes to compare.

        This assumes two kinds of votes: weak and strong.

        weak votes are worth a base score of 10/10 points if aligned, 0/10 points if not aligned, and 1/2 points if absent.
        Strong votes are worth a base score of 50/50 points if aligned, 0/50 points if not aligned, and 25/50 points if absent.

        The weird bit of complexity here is absences on weak votes reduce the total of the comparison.
        This means that MPs are only lightly penalised for missing votes if they attended some votes, or if there are strong votes.
        If all votes are weak and absent, the score will be 0.5.

        So if there were five weak votes, two in line with the policy, and three absent - the difference would be 0.12.
        But if weak votes were treated the same way as strong votes (5/10) - the difference would be 0.3.

        So the practical result of making a policy a mix of strong and weak votes is first,
        obviously that weak votes make up a smaller part of the total score.
        But the second is that strong votes penalise absences more than weak votes.

        Strong votes were originally intended to reflect three line whips, but in practice have broadened out to mean 'more important'.

        Do nothing with agreements for the moment.

        """
        vote_weight = ScoreFloatPair(weak=10.0, strong=50.0)
        absence_total_weight = ScoreFloatPair(weak=2.0, strong=50.0)

        absence_weight = ScoreFloatPair(weak=1.0, strong=25.0)

        # treat abstentions as absences
        votes_absent_or_abstain = votes_absent.add(votes_abstain)

        points = (
            vote_weight.weak * votes_different.weak
            + vote_weight.strong * votes_different.strong
            + absence_weight.weak * votes_absent_or_abstain.weak
            + (
                (absence_weight.strong) * votes_absent_or_abstain.strong
            )  # Absences on strong votes are worth half the strong value
        )

        avaliable_points = (
            vote_weight.weak * votes_same.weak
            + vote_weight.weak * votes_different.weak
            + vote_weight.strong * votes_same.strong
            + vote_weight.strong * votes_different.strong
            + absence_total_weight.strong * votes_absent_or_abstain.strong
            + absence_total_weight.weak * votes_absent_or_abstain.weak
        )  # Absences on weak votes reduce the total of the comparison

        if avaliable_points == 0:
            return -1

        return points / avaliable_points


class SimplifiedScore(ScoringFuncProtocol):
    @staticmethod
    def score(
        *,
        votes_same: ScoreFloatPair,
        votes_different: ScoreFloatPair,
        votes_absent: ScoreFloatPair,
        votes_abstain: ScoreFloatPair,
        agreements_same: ScoreFloatPair,
        agreements_different: ScoreFloatPair,
    ) -> float:
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

        if avaliable_points == 0:
            return -1

        score = points / avaliable_points

        total = (
            votes_same.strong
            + votes_different.strong
            + votes_absent.strong
            + votes_abstain.strong
        )

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
        if votes_absent.strong >= total / 3:
            if score <= 0.15:
                score = 0.16
            elif score >= 0.85:
                score = 0.84

        return score
