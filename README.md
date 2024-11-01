# twfy-votes-django

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/mysociety/twfy-votes)

Voting information platform.

This takes the divisions data from TheyWorkForYou and votes.parliament.uk and adds layers of analysis. 

In turn, it powers the voting record summaries in TheyWorkForYou. 

# The general data approach

The public facing components of this are a normal django/postgres approach.

However, most of the data crunching happens in duckdb as part of the populate process. 

This uses a set of SQL queries to create aggregate analysis or transformations. This can pull from parquet files, or from postgres tables.

The goal of this is that little heavy lifting should happen at run time - and that the kind of analysis we're doing is most efficient to do in bulk at the start. 

# Populating the database

`script/populate -all` - will run through all the steps to create the database from scratch.

Individual steps can be run with `scripts/populate --group votes` - see 'populate/register.py` for a list of groups. 

This populate command can also take an `--update-since` isodate. Where this make sense, it is respected (biggest benefit is not reloading all votes all vote).
The policy calculation respects this as a flag that makes it only compare the hashes since it was last calculated. 

To add new steps, follow the example of one of files in `votes/populate` - adding a Group to the ImportOrder enum if necessary. 

Groups and models are different concepts when multiple models logically can be created at the same time (order doens't matter) - but before or after other steps. 

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
- twfy api view
- new motions import
