import datetime
from dataclasses import dataclass

import pandas as pd

from twfy_votes.helpers.routes import RouteApp

from ..models.decisions import Agreement, Chamber, Division, UrlColumn

app = RouteApp(app_name="votes")


@dataclass
class DivisionSearch:
    start_date: datetime.date
    end_date: datetime.date
    chamber: Chamber
    decisions: list[Division | Agreement]

    def decisions_df(self) -> pd.DataFrame:
        data = [
            {
                "Date": d.date,
                "Division": UrlColumn(url=d.url(), text=d.safe_decision_name()),
                "Vote Type": d.vote_type(),
                "Powers": d.motion_uses_powers(),
                "Voting Cluster": d.voting_cluster()["desc"],
            }
            for d in self.decisions
        ]

        return pd.DataFrame(data=data)
