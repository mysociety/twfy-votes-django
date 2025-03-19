# About TheyWorkForYou Votes

## Introduction

TheyWorkForYou Votes is a parliamentary voting analysis.

Our goal is to create and support better analysis of decisions taken in the UK's Parliaments - both directly to citizens, or indirectly by providing new tools and data to specialists. 

Please report any issues through [the reporting form](https://survey.alchemer.com/s3/8114572/TheyWorkForYou-Votes-issue-reporting) or [our contact page](https://www.theyworkforyou.com/contact/).

Read [more about votes, and how we handle them in TheyWorkForYou](https://www.theyworkforyou.com/voting-information/).


## Decisions

This site lists decisions made in the UK's Parliaments, and provides analysis of the results.

By decisions, we mean by 'divisions' (when representatives have voted), and 'agreements' (when a decision is made without a vote).

## Divisions

We list divisions for the Westminster Parliament, the Scottish Parliament, and the Senedd/Welsh Parliament.

We do not currently list divisions for the Northern Ireland Assembly. This is because the underlying TheyWorkForYou parser does not currently support divisions, and there are additional analysis needs around correctly showing the results of votes with cross-community requirements. 

## Agreements

Agreements are decisions made without a vote. The chair will test if there is any opposition, and if not, the motion is passed. 

We list agreements for the House of Commons, and the Scottish Parliament.     

Agreements do not necessarily mean that all MPs supported the result, just that there was no opposition, and so the decision was made collectively. 

In practice, this can mean "everyone loved this", "we all agree you'd win so it's a waste of time voting", and "this is a small piece of house business". 

Our goal in listing agreements is to be able to better explain decisions made without a vote, by creating a page to attach motions that are passed this way. 

We can add these into voting summaries, but do so infrequently - when we feel we can make a clear interpretation of the decision. 

## Motions

To improve public understanding of Parliament, we want to make it easier to understand and link back to what a vote or decision was about.

The official record (Hansard) can be unhelpful for this, with the subject for debate being referred to as 'the question', and the motion itself may be significantly earlier, or sometimes absent altogether. 

We have written new parsers to extract motions from Parliamentary transcripts, and assign them to decisions/agreements.

This can be fiddly, as the wording of motions can be complex, and the way they are presented in the transcript can vary. Please report any errors using the link on the decision in question. 

For each motion, we are then trying to categorise the kind of motion - and give additional detail about what that kind of motion means. This is a work in progress, and please report any problems. 

## Parliamentary dynamics clustering

For divisions in all Parliaments we cover, we have added an automated description of the Parliamentary dynamics of the vote. 

The goal of this is to make it easier when reviewing lots of votes to understand as a glance the shape of the politics of a vote - and then to expand that to a fuller description for public use. 

The way this technically works is for each division we have divided the results into six percentages of government/opposition and for/against/absent.

From this, we ran a clustering approach to identify common groups of divisions based on basic government/opposition dynamics. 

The clusters this current covers are:

* Strong conflict: Gov proposes
* Strong conflict: Opposition proposes
* Divided opposition: Government Aye, Opposition divided
* Medium conflict: Opposition Aye, Government No
* Nominal opposition: Government Aye Opposition Weak No
* Multi-party against: Government No, Opposition divided
* Low participation vote
* Cross-party aye

Additionally - for items that are outliers in their cluster - we highlight that this may be the best current description, but is stretching how we are describing it.

We can override these descriptions when the automated description is not helpful - please report any issues using the link on the decision in question.

## Voting breakdowns and party alignment

This is the bread and butter of a voting analysis site. We list how people vote, and create breakdowns of how parties collectively voted. 

As a substitute for knowing the party voting instructions, we calculate a party alignment score - where we calculate the percentage of party that voted for the motion, and then calculate the distance of individual representatives (who will be 0% or 100% for the motion) to this score. Absent votes do not count towards this score. 

Lower scores will be more rebellious. Aggregate summaries for a specific representative by year are available on their person page. 

When a party is divided, even MPs who voted with the majority view will pick up a small lack of alignment - which is why in the long term stats unrebellious MPs have scores below 100%..

## Annotations and whip reports

An impact of TheyWorkForYou has been [more public explanations by representatives](https://www.mysociety.org/2023/07/12/guest-post-does-watching-mps-make-them-behave-better/) of how they've voted. 

We want to start logging these into our database, to make the more accessible to people viewing their representatives' voting records.

Divisions, Agreements, and votes by individual representatives can be annotated with additional information or a link. 

We're currently testing this out, but in the long run we want to make it possible for representatives to add their own annotations to their voting records. 

## Whip reports

A key part of how Parliament works is that MPs are instructed on how to vote by their party.

To better explain how Parliament works, [we want this information to be public](https://www.mysociety.org/2022/01/21/the-voting-instructions-parties-give-their-mps-should-be-public/) in all instances, but a starting point is better collection and display of this information where it is has become public.

For some votes, we are adding Whip Reports about how parties instructed their members to vote when this information has become public. 

As with annotations, we want to explore getting the information directly from representatives, to improve public understanding of how our Parliaments work. 

## Policies/Voting Records Comparisons

One of TheyWorkForYou's key features are the voting record summaries. TheyWorkForYou Votes is our tool for managing and calculating these summaries. 

We create "policies", that group a set of votes together and say if a vote agrees or is against the general direction of the policy. 

From this, we calculate for each MP their own alignment score, and the alignment score of comparable MPs (MPs of the same party, over the same votes). This helps highlight policies where an MP differs from the majority of their party. 

We currently only have policies for the House of Commons, but part of the purpose of TheyWorkForYou is creating tools that help us update policies more efficiently, and reduce the resources needed to expand to other Parliaments.

Read [more about votes, and how we handle them in TheyWorkForYou](https://www.theyworkforyou.com/voting-information/).
