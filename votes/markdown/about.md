# TheyWorkForYou Votes – Help & Overview

## What is TheyWorkForYou Votes?

TheyWorkForYou Votes is the home of our upgraded parliamentary voting analysis. It brings together data from the UK’s legislatures, adds new context, and makes it easier for everyone—from interested citizens to researchers—to understand and analyse decisions made.

If you spot a problem or have a suggestion, please let us know via our [issue reporting form](https://survey.alchemer.com/s3/8114572/TheyWorkForYou-Votes-issue-reporting) or the [contact page](https://www.theyworkforyou.com/contact/).

You can read more about votes in general, and our voting summary information [in TheyWorkForYou](https://www.theyworkforyou.com/voting-information/).

---

## Decisions, Divisions & Agreements

This site lists decisions made in the UK’s Parliaments, and provides analysis of the results.
On this site a decision can be a Division or an Agreement.

A division is when representatives vote “Aye/No” (or equivalents) and the names are recorded, as happens in the Commons, Lords, Scottish Parliament, and Senedd Cymru.

Alternatively, a decision may be an Agreement. In this case, the chair asks whether anyone objects, and if no one does, the motion passes without a recorded vote. We create an entry for this agreement to better associate it with the text of the motion. 

We do **not yet list divisions for the Northern Ireland Assembly**. Our current parser for the Assembly does not extract divisions.

---

## Divisions

For each division you’ll find:

* The motion text (where available)
* Tallies of Ayes, Noes and absentees.
* Party‑by‑party breakdowns.
* An automated description of the parliamentary dynamic

## Agreements

Agreements are decisions made without a vote. The chair will test if there is any opposition, and if not, the motion is passed. 

We list agreements for the House of Commons, and the Scottish Parliament.     

Agreements do not necessarily mean that all MPs supported the result, just that there was no opposition, and so the decision was made collectively. 

In practice, this can mean “everyone loved this”, “we all agree you’d win so it is a waste of time voting”, or “this is a small piece of house business”.

Our goal in listing agreements is to be able to better explain decisions made without a vote, by creating a page to attach motions that are passed this way. 

We can add these into voting summaries, but do so infrequently – when we feel we can make a clear interpretation of the decision. 

---

## Motions

Understanding *what* was being voted on is just as important as seeing the numbers. In debates, the matter is often talked about as “the Question”, with the full wording hidden earlier in the transcript—or missing entirely.

We have written new parsers to pull out the motion text and attach it to each decision. Because transcripts vary, mistakes can happen: please use the **“Report a problem”** link on any decision page if something looks wrong.

We’re also categorising these motions into common types and adding plain‑English explanations. This work is ongoing—feedback is welcome.

Sometimes knowning the motion is still unhelpful because it refers to an Lords amendment number. We need to automate a few more steps to be able to pull the content of this out of the PDFs Parliament publishes. 

---

## Parliamentary Dynamics Clustering

To give a quick sense of the politics behind each division, we run a clustering algorithm on a breakdown of each vote.
We calculate the six percentages(Government/Opposition × For/Against/Absent) and can use this as a way to cluster that is independent of the relative numbers of the government and opposition. This helps give a sense of who is proposing the vote, and the strength of the conflict. 

The clusters currently in use are:

* **Strong conflict – Government proposes**
* **Strong conflict – Opposition proposes**
* **Divided opposition – Government Aye, Opposition split**
* **Medium conflict – Opposition Aye, Government No**
* **Nominal opposition – Government Aye, Opposition weak No**
* **Multi‑party against – Government No, Opposition split**
* **Low‑participation vote**
* **Cross‑party Aye**

If a vote sits awkwardly in its cluster we flag it as an outlier, and editors can override the label where necessary.

---

## Legislation Tags

Where a decision relates to a Bill, we link all the relevant votes together and back to the bill‑tracking page. Titles vary, so occasionally a bill will be split across two tags or a vote will be missed.

All currently legislative tags can be seen on the tags page.

---

## Voting Breakdowns & Party Alignment

For every decision we list how each representative voted and summarise party voting behaviour.

Because whip instructions are not always public, we calculate a **party‑alignment score** instead. Alignment is the distance between an MP’s vote for the motion(0 % or 100 %) and the share of their party voting for the motion (e.g. if 3/5s vote for the motion: 60%). If all members of a party vote the same way, there is 100% alignment. 

Absent votes don’t count towards the score. Lower scores indicate greater rebellion. Annual aggregates appear on each representative’s profile.

This is slightly different from ‘rebelliousness’ scores because even those who consistently vote with the majority of the party will not score 100% (as they will pick up small percentage from the average differences because of rebels).

The advantage of this statistic is being responsive the size of rebellions – e.g. in a free vote a sizable group of representatives voting against the majority of the party will be more aligned with the average party position in this vote, than a single MP going the other way in another vote. 

Our long term goal is to calculate rebellion information based on actual whip information. 

---

## Annotations

Partly as a result of [sites like TheyWorkForYou](https://www.mysociety.org/2023/07/12/guest-post-does-watching-mps-make-them-behave-better/)[,](https://www.mysociety.org/2023/07/12/guest-post-does-watching-mps-make-them-behave-better/) more MPs are now publicly explaining how they voted. We’re beginning to log these statements so they appear alongside the official record. Decisions, agreements and individual votes can all carry annotations with extra background or links.

In future we hope to let representatives add their own explanations directly.

---

## Whip Reports

Party whips tell MPs how to vote. [Making these instructions public](https://www.mysociety.org/2022/01/21/the-voting-instructions-parties-give-their-mps-should-be-public/) would help everyone understand parliamentary decisions better.

For some votes, we are adding Whip Reports about how parties instructed their members to vote when this information has become public.

As with annotations, we want to explore getting the information directly from representatives, to improve public understanding of how our Parliaments work.

---

## Policies and Voting‑Record Comparisons

TheyWorkForYou’s voting summary are caucluated on this site as **policies**: themed collections of votes marked as *supporting* or *opposing* a given outcome.

From these we calculate:

* **MP policy score** – how far an MP’s votes align with the policy direction.
* **Party comparison** – how an MP’s score compares with colleagues in the same party over the same votes.

At present policies cover only the House of Commons, but the new tooling behind TheyWorkForYou Votes will make it easier to extend them to other legislatures, or to push summaries further back in time as a learning resources. We have no set timetable on doing this however. 

Read [more about votes, and how we handle them in TheyWorkForYou](https://www.theyworkforyou.com/voting-information).
