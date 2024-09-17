import pandas as pd

from votes.policy_generation.scoring import ScoreFloatPair
from votes.policy_generation.scoring import SimplifiedScore as SimplifiedScoreBase

SimplifiedScore = SimplifiedScoreBase[float]
SimplifiedScoreSeries = SimplifiedScoreBase[pd.Series]


def test_abstain():
    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=1.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    assert result == 0.5, "Expected score to be 0.5 when all votes are abstain"


def test_midway_score():
    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=5.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=5.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    assert (
        result == 0.5
    ), "Expected score to be 0.5 when half of the votes are the same and half are different"


def test_similar_score():
    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=15.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=5.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    assert (
        result == 0.25
    ), "Expected score to be 0.25 when a quarter of the votes are different and three quarters are the same"


def test_similar_score_agreement():
    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=15.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=5.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=15.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=5.0),
    )

    assert (
        result == 0.25
    ), "Expected score to be 0.25 when a quarter of the agreements are different and three quarters are the same"


def test_dissimilar_score_agreements():
    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=5.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=15.0),
    )

    assert (
        result == 0.75
    ), "Expected score to be 0.75 when a quarter of the votes are the same and three quarters are different"


def test_dissimilar_score():
    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=5.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=15.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    assert (
        result == 0.75
    ), "Expected score to be 0.75 when a quarter of the votes are the same and three quarters are different"


def test_simplified_score_all_votes_same():
    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=5.0, strong=5.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=5.0, strong=5.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )
    assert (
        result == 0.0
    ), f"Expected score to be 0.0 when all votes are the same, instead got {result}"


def test_simplified_score_all_votes_different():
    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_different=ScoreFloatPair(weak=5.0, strong=5.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=5.0, strong=5.0),
    )
    assert result == 1.0, "Expected score to be 1.0 when all votes are different"


def test_simplified_score_all_votes_absent():
    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=5.0, strong=5.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )
    assert (
        result == -1
    ), "Expected score to be -1 when all votes are absent - no score available"


def test_simplified_score_all_votes_abstain():
    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=5.0, strong=5.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )
    assert result == 0.5, "Expected score to be 0.5 when all votes are abstain"


def test_weak_votes_no_effect():
    # the score based on a set of strong votes should not changed by adding or removing any weak votes

    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=5.0, strong=5.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=5.0, strong=5.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    result_with_weak_votes = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=5.0, strong=5.0),
        votes_different=ScoreFloatPair(weak=5.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=5.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=5.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=5.0, strong=5.0),
        agreements_different=ScoreFloatPair(weak=5.0, strong=0.0),
    )

    assert (
        result == result_with_weak_votes
    ), "Expected score to be the same with or without weak votes"


def test_absences_no_effect():
    # the score based on a set of strong votes should not be changed by adding or removing any absences

    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=5.0, strong=5.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=5.0, strong=5.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    result_with_absences = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=5.0, strong=5.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=5.0, strong=1.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=5.0, strong=5.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    assert (
        result == result_with_absences
    ), "Expected score to be the same with or without absences"


def test_absence_cap_strong():
    result_with_absences = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=5.0, strong=10.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=2.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    assert (
        result_with_absences == 0.06
    ), f"Expected score to be the cap - instead was {result_with_absences}"


def test_absence_cap_strong_against():
    result_with_absences = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_different=ScoreFloatPair(weak=5.0, strong=10.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=2.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    assert (
        result_with_absences == 0.94
    ), f"Expected score to be the cap - instead was {result_with_absences}"


def test_absence_cap_one_third():
    result_with_absences = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=5.0, strong=10.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=5.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    assert (
        result_with_absences == 0.16
    ), f"Expected score to be the cap - instead was {result_with_absences}"


def test_absence_cap_one_third_against():
    result_with_absences = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_different=ScoreFloatPair(weak=5.0, strong=10.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=5.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    assert (
        result_with_absences == 0.84
    ), f"Expected score to be the cap - instead was {result_with_absences}"


def test_weak_agreements_change_nothing():
    # adding weak agreements should not change the score

    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=5.0, strong=5.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=5.0, strong=5.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    result_with_weak_agreements = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=5.0, strong=5.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=5.0, strong=5.0),
        agreements_different=ScoreFloatPair(weak=5.0, strong=0.0),
    )

    assert (
        result == result_with_weak_agreements
    ), "Expected score to be the same with or without weak agreements"


def test_strong_agreements_are_like_votes():
    # strong agreements should be counted the same as votes
    # compare two scores - the first has a set of strong agreeing votes,
    # the second moves these into agreeing agreements

    result = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0, strong=5.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=5.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=0.0),
    )

    result_with_agreements = SimplifiedScore.score(
        votes_same=ScoreFloatPair(weak=0.0, strong=5.0),
        votes_different=ScoreFloatPair(weak=0.0, strong=5.0),
        votes_absent=ScoreFloatPair(weak=0.0, strong=0.0),
        votes_abstain=ScoreFloatPair(weak=0.0, strong=0.0),
        agreements_same=ScoreFloatPair(weak=0.0, strong=5.0),
        agreements_different=ScoreFloatPair(weak=0.0, strong=5.0),
    )

    assert (
        result == result_with_agreements
    ), "Expected score to be the same with or without strong agreements"


def test_series_logic():
    result = SimplifiedScoreSeries.score(
        votes_same=ScoreFloatPair(weak=pd.Series([0.0]), strong=pd.Series([0.0])),
        votes_different=ScoreFloatPair(weak=pd.Series([0.0]), strong=pd.Series([0.0])),
        votes_absent=ScoreFloatPair(weak=pd.Series([0.0]), strong=pd.Series([0.0])),
        votes_abstain=ScoreFloatPair(weak=pd.Series([0.0]), strong=pd.Series([1.0])),
        agreements_same=ScoreFloatPair(weak=pd.Series([0.0]), strong=pd.Series([0.0])),
        agreements_different=ScoreFloatPair(
            weak=pd.Series([0.0]), strong=pd.Series([0.0])
        ),
    )
    assert result.iloc[0] == 0.5, "Expected score to be 0.5 when all votes are abstain"
