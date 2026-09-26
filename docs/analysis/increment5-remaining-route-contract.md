# Increment 5 remaining route contract

This document describes the current local DuckDB contract for the non-card analytical and external-source routes. It is a verification companion to the main handoff, not a deployment record.

## Serving boundary

The implementation uses public contract schema 4 and response-cache schema 8. A database or snapshot created under an earlier contract is ineligible for reuse. These routes become active only through a newly built immutable generation, complete snapshot validation, and atomic pointer activation.

## Analytical contracts

- Predictors General and Icons pair the two rows of a game before filtering. Dataset, map, Elo, date, completion, Starting position, Arena, and Tournament predicates apply to the focal player only.
- Predictors Specific contains 19 real conditions backed by endgame, Logs, played-card, and opening-hand facts. Humphead Wrasse and New Zealand Fur Seal are absent.
- Actions has the four public views and fixed five-action catalogs. Starting position contains four strength rows and five comparison rows. The other Actions views preserve their fixed upgrade-count, action, order, and map schemas.
- Sponsor Endgames uses 31 configured CP sponsors and nine configured Appeal sponsors. Bucket EV and CI moments always use the source Elo delta; endgame points are only the bucket variable.
- Build/Hexes publishes six compact buckets and an exact 0-23 plus 24+ expanded catalog. Empty Petting Zoo means exactly one built Petting Zoo, zero Petting Zoo icons, and no Horse Whisperer.
- Conservation Project Rewards uses the fixed 22-row catalog and separate scoped denominators. CP Rewards calculates frequency from reward opportunities, not only from chosen rewards.
- Scoring returns collapsed and expanded catalogs: Final score 7/52 rows, Appeal 9/75, Conservation 8/42, and Reputation 15/15.
- Icons contains the fixed 16 subjects with independent valid-value denominators. Workers, Maps, and Endgames retain their page-specific observation units and completion contracts.
- Home returns its twelve named measures and is the sole analytical route that retains corrupted games.
- Arena uses numeric player IDs, draw-aware scores, FIDE expected-score performance rating, canonical opponent pre-match Elo, all matched Arena games for Games/Winrate/Peak/Opponent Elo/PR/history, and completed games only for Turns/PPT.
- Records is dataset-neutral. Manual rows are included once, exact-player enrichment is preferred, automatic Fastest/Highest rows require wins, automatic Highest excludes games above 100 turns, dates are YYYY-MM-DD, and icon labels use the public plural names.

## External-source contract

Arena settings, all required season rosters, and the three Records CSVs are refreshed into one moving-source directory. Each source is marked `fresh` or `last_known_good` in `source-status.json`; a complete prior set is retained on download or validation failure. Tournament metadata uses a validated JSON cache and then the active generation as fallback. The candidate manifest includes source fingerprints and fallback state. Missing both fresh and last-known-good input aborts the candidate before activation.

## Focused verification

The static Increment 5 gate validates the fixed catalog sizes and generated population SQL. Unit coverage checks the exact predicates, catalogs, completion rules, Home exception, Arena projection, Records winner/date behavior, expanded payload schemas, snapshot request fields, and tournament fallback.

A representative real-schema builder smoke executes the restored route builders and compares selected unrounded means and counts directly with the same local source relations. Full-generation numerical and performance verification belongs to candidate validation before atomic activation; production is never mutated by these checks.

