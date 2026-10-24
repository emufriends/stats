# Daily Elo and Arena Peak Updater

This directory is the deployable source for the independent Google Cloud
Function that maintains the Elo peak spreadsheet. It is not part of the stats
dashboard request path.

For cross-component context and production resource names, start with:

```text
C:\Users\ascri\Desktop\ark-nova-stats-dashboard\elo_system_handoff.md
```

Never place a Discord webhook URL, service-account key, OAuth token, or other
credential in this repository or its documentation.

## Production data contract

Spreadsheet ID:

```text
1NG3FPP70riMzhHPJ6Suz30bhJxUocFd_rKDKxn0kZbM
```

Every run processes `Masters`, `Experts`, `Candidates`, and `Ineligible`.

| Column | Meaning |
|---|---|
| C | Player display name |
| F | Peak Elo and hyperlink |
| G | Elo peak date |
| H | Peak Arena rating and hyperlink |
| K | BGA `player_id` |
| M | Peak Elo `table_id` |
| N | Peak Arena `table_id` |

The BigQuery source is
`freestyle-190711.ark_nova.all_games_stat`. The query uses `player_id`,
`post_match_elo`, `post_match_arena_rating`, `table_id`, `url`, and
`game_ended_at`. All player IDs are fetched in one grouped query. Tied maximum
ratings select the latest `game_ended_at`, then `table_id`, then URL.

## Update rules

- Ratings are compared after rounding to two decimal places.
- A higher database rating updates the rating and its permitted metadata.
- An equal database rating repairs incorrect metadata or hyperlinks.
- A lower database rating changes nothing. This preserves manually maintained
  peaks from game types that are not present in the source table.
- Blank or `n/a` Arena ratings compare as zero.
- Elo updates F, G, and M. Arena updates H and N.
- No rows are inserted, deleted, or reordered, and no other columns are edited.
- Hyperlinks in F and H use the source row's `url`.
- G is written as a numeric Google Sheets date serial with number format
  `yyyy-mm-dd`. This is deliberate: text dates can appear blank on the public
  leaderboard. Equal-rating rows with text dates are repaired.

## Discord notification

Only actual Elo increases in `Masters` and `Experts` are included. Arena
increases and metadata-only corrections are omitted. Entries are sorted by
**new Elo descending**.

```text
__**New elo peaks: YYYY-MM-DD**__
- __Player name:__ old_elo → **new_elo**
```

When there are no qualifying increases, the message contains `- None`. Long
messages are split below Discord's content limit. The webhook is injected from
Secret Manager as `DISCORD_WEBHOOK_URL`.

## Idempotency and retries

Run state is stored under:

```text
gs://ark-nova-stats-dashboard-cache/elo-peak-updater/runs/
```

The state tracks `sheet_update_applied` and `notification_sent`, allowing a
retry after a Discord failure without repeating a successful Sheets update.

Scheduled retries use `X-CloudScheduler-ScheduleTime` as the run key. Manual
`gcloud scheduler jobs run` requests can carry the next future schedule time;
`_scheduled_run_id()` therefore treats timestamps more than five minutes in
the future as unique manual runs. Keep this guard—it prevents a manual test
from consuming the following midnight run's idempotency key.

## Production deployment contract

```text
Google Cloud project: ark-nova-stats-dashboard
Region: europe-west1
Function: update-elo-peaks (Gen 2)
Runtime: python311
Entry point: update_peaks
Runtime service account:
  dashboard-backend@ark-nova-stats-dashboard.iam.gserviceaccount.com
Max instances: 1
Max request concurrency: 1
Timeout: 540 seconds
State bucket: ark-nova-stats-dashboard-cache
Secret: discord-elo-peaks-webhook

Scheduler job: update-elo-peaks-daily
Schedule: 0 0 * * *
Timezone: UTC
Method/authentication: POST with OIDC
Invoker service account:
  elo-peak-updater-scheduler@ark-nova-stats-dashboard.iam.gserviceaccount.com
```

## Source and tests

- `main.py` exposes the `update_peaks` HTTP entry point.
- `updater.py` contains all query, comparison, Sheets, Discord, and state logic.
- `tests/test_updater.py` is the unit and mocked integration suite.

Run from this directory:

```powershell
python -m unittest discover -s tests -v
```

The suite covers higher/equal/lower comparisons,
metadata repair, typed dates, `n/a` Arena handling, deterministic ties,
Discord formatting and new-Elo ordering, and retry-safe state handling.

## Deploy

Deploy from this directory using the existing production configuration:

```powershell
gcloud functions deploy update-elo-peaks `
  --gen2 `
  --runtime python311 `
  --region europe-west1 `
  --project ark-nova-stats-dashboard `
  --source . `
  --entry-point update_peaks `
  --trigger-http `
  --no-allow-unauthenticated `
  --max-instances 1 `
  --concurrency 1 `
  --timeout 540s `
  --service-account dashboard-backend@ark-nova-stats-dashboard.iam.gserviceaccount.com `
  --set-secrets DISCORD_WEBHOOK_URL=discord-elo-peaks-webhook:latest
```

The runtime identity needs BigQuery job/read access, Sheets Editor access to
the workbook, object access to the state bucket, and Secret Manager access to
the webhook secret. The Scheduler OIDC identity needs invoker permission.

## Manual production run and verification

This is a real external mutation: it can update the spreadsheet and always
sends a Discord message, including `- None`.

```powershell
gcloud scheduler jobs run update-elo-peaks-daily `
  --project ark-nova-stats-dashboard `
  --location europe-west1
```

Verify the function request log and persisted state rather than relying only on
the Discord channel:

```powershell
gcloud logging read `
  'resource.type="cloud_run_revision" AND resource.labels.service_name="update-elo-peaks"' `
  --project ark-nova-stats-dashboard `
  --limit=30 `
  --order=desc

gcloud storage ls --recursive `
  gs://ark-nova-stats-dashboard-cache/elo-peak-updater/runs/
```

The function logs failures but does not print its full success summary. The
persisted JSON object is authoritative; inspect only selected fields because
it also contains a large request plan and notification content. A state object
filename may reflect the Scheduler header's UTC offset and look one calendar
day earlier; use its `created_at` value or convert the offset before assigning
the run to a UTC date.

Warnings that `httplib2` does not support per-request timeout have appeared on
otherwise successful runs and are not, by themselves, evidence of a failure.

## Optional environment overrides

Production uses the defaults in `updater.py`. Tests or separate deployments can
override:

- `PEAKS_SPREADSHEET_ID`
- `PEAKS_SOURCE_TABLE`
- `PEAKS_STATE_BUCKET`
- `PEAKS_STATE_PREFIX`
- `DISCORD_WEBHOOK_URL`
