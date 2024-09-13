import datetime

from votes.populate.commons_votes import DivisionSearchList


def test_valid_results():
    known_date = datetime.date.fromisoformat("2024-09-10")
    divisions = DivisionSearchList.from_date(start_date=known_date, end_date=known_date)

    assert len(divisions.root) == 2, "Expected 2 divisions on this date"

    vote_count = 0
    for d in divisions.root:
        vote_count += (
            len(d.Ayes)
            + len(d.Noes)
            + len(d.AyeTellers)
            + len(d.NoTellers)
            + len(d.NoVoteRecorded)
        )

    assert vote_count == 1300, "Expected 1300 votes on this date (2 x 650)"
