# twfy-votes-django

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/mysociety/twfy-votes-django)

Voting information platform.

This takes the divisions data from TheyWorkForYou and votes.parliament.uk and adds layers of analysis. 

In turn, it powers the voting record summaries in TheyWorkForYou. 

# The general data approach

The public facing components of this are a normal django/postgres approach.

However, most of the data crunching happens in duckdb as part of the populate process. 

This uses a set of SQL queries to create aggregate analysis or transformations. This can pull from parquet files, or from postgres tables.

The goal of this is that little heavy lifting should happen at run time - and that the kind of analysis we're doing is most efficient to do in bulk at the start. 

# Populating the database

`script/setup` -- setup database.

`script/populate --all` - will run through all the steps to create the database from scratch.

Individual steps can be run with `scripts/populate --group votes` - see `script/populate --show-options` for a complete list of available groups and models, displayed in a nice table format. 

This populate command can also take an `--update-since` isodate. Where this make sense, it is respected (biggest benefit is not reloading all votes). `--update-last [x]` does the last x days.

The policy calculation treats this being set as a flag that makes it only compare the hashes since it was last calculated, and recalculate the difference - rather than the default starting from scratch. 

The best range to do an update for commons api happening today is:

`script/populate --update-last 0 --start-group api_votes --end-group person_stats`

or `script/populate --shortcut refresh_commons_api`

And to update motions and agreements (if analysis repo was delayed):

`script/populate --update-last 4 --start-group download_motions --end-group decisions`


or `script/populate --shortcut refresh_motions_agreements`

## Available shortcuts

Several shortcuts are predefined to run common groups of tasks:

- `refresh_commons_api` - Update from the Commons API (last 1 day)
- `refresh_motions_agreements` - Update motions and agreements (last 3 days)
- `refresh_daily` - Run all models for the last day
- `refresh_recent` - Run all models for the last 10 days
- `refresh_policies` - Update just the policies (last 7 days)

You can see all available shortcuts and their descriptions with `script/populate --show-options`.

To add new steps, follow the example of one of files in `votes/populate` - adding a Group to the ImportOrder enum if necessary. 

Groups and models are different concepts when multiple models logically can be created at the same time (order doesn't matter) - but before or after other steps. 

# The automatic update process

There is a task checker that runs every minute - can be manually run with `script/manage run_queue --check-for-updates`.

This checks for any update queue items that have been created, and runs the corresponding update (the instructions dict it expects uses the same inputs as the populate command).

These are currently produced in four ways.

* Manually through the django admin.
* A check of the Commons Votes API.
* Webhook meant for twfy's parsing to trigger (refreshes the last day).
* Webhook meant for the motion detector to trigger (refreshes motions) - ideally consolidate this into parlparse at some point. 

# Adjusting policies

There is a CLI to handle updating the policy yamls (although you can do this manually).

`python -m twfy_votes.policy ui` will give an overview of the options.

When done, this will just process the changed policies. 

```
script/populate --start-group POLICIES --end-group POLICYCALC --update-since 2024-09-17
```

# Tests

`script/test` will run pytest. Pytest is using the *local live database* - which it expects to be loaded with the real data (given that is easily avaliable).

If adjusting at the policy generation approach you might also want to look `script/manage vr_validator` - which is used as part of the test suite, but has some configurable parameters.

# Development

This uses ruff for linting and formatting., and djlint for django templates - see `script/lint`.

# To do

- person/policy view (equiv of old publid whip view)
- new motions import
