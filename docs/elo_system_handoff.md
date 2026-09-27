# Elo Peak Updater and Standalone Leaderboard — Current AI Handoff

Use this document for work on the Elo/Arena peak spreadsheet, its daily updater,
the standalone leaderboard, or the dashboard Records/Elo Leaderboard. Use
`ark_nova_dashboard_handoff.md` for the main statistics application.

This file is intentionally secret-free. Never record webhook URLs, OAuth tokens,
service-account JSON, private keys, or maintenance credentials.

## System boundaries

Three independently deployed components share the same maintained peak data:

1. **Peak spreadsheet and updater** — the authoritative maintained values and a
   dedicated daily Cloud Function.
2. **Standalone full leaderboard** — a static site that reads the public sheet.
3. **Dashboard Records/Elo Leaderboard** — a Top 100 snapshot in the main stats
   dashboard with a link to the full leaderboard.

Do not edit the main dashboard for a request that concerns only the updater or
standalone site.

## Local paths

```text
Updater source:
C:\Users\ascri\Desktop\ark-nova-function\elo_peak_updater

Standalone leaderboard:
C:\Users\ascri\Desktop\arknova-leaderboard-main

Main dashboard frontend:
C:\Users\ascri\Desktop\ark-nova-stats-dashboard

Main dashboard backend:
C:\Users\ascri\Desktop\ark-nova-function
```

Verify the standalone folder's Git/deployment state before assuming a local edit
is public.

## Authoritative spreadsheet

```text
Sheet ID: 1NG3FPP70riMzhHPJ6Suz30bhJxUocFd_rKDKxn0kZbM
Tabs: Masters, Experts, Candidates, Ineligible
```

Relevant columns on every tab:

| Column | Meaning |
|---|---|
| C | Player display name |
| F | Peak Elo, two decimals, linked to the peak game |
| G | Elo peak game date as a real Sheets date displayed `yyyy-mm-dd` |
| H | Peak Arena rating, linked to the peak Arena game |
| I | Peak Arena finish; used by the standalone site |
| K | BGA `player_id`; authoritative identity |
| M | Peak Elo `table_id` |
| N | Peak Arena `table_id` |

The source relation is `freestyle-190711.ark_nova.all_games_stat`. The updater
uses `post_match_elo`, `post_match_arena_rating`, `player_id`, `table_id`, `url`,
and `game_ended_at`. It queries all sheet player IDs in one grouped job. Tied
maxima choose the latest game end, then table ID, then URL.

## Updater contract

Entry point: `main.py:update_peaks`; implementation: `updater.py`.

- Process every row with a player ID across all four tabs.
- Compare ratings rounded to two decimals.
- If the database rating is higher, update the rating and its permitted metadata.
- If equal, repair date/table/link metadata only.
- If lower, preserve the maintained sheet values; the sheet may contain a peak
  from an unsupported higher-player-count game.
- Blank or `n/a` Peak Arena is a valid value meaning that no Arena peak is known.
  It compares as zero and is replaced when a real peak is found.
- Elo writes columns F, G, and M. Arena writes H and N.
- Do not insert, delete, or reorder rows and do not modify unrelated columns.
- F and H links use the database `url`.
- G is a numeric Sheets date serial formatted `yyyy-mm-dd`, never display text.
- Apply planned writes in one Sheets batch update.

## Discord notification contract

The webhook is stored only in Secret Manager:

```text
Secret: discord-elo-peaks-webhook
Function environment variable: DISCORD_WEBHOOK_URL
```

Only actual Elo increases from Masters and Experts are listed. Arena increases
and metadata-only repairs are excluded. Entries are ordered by new Elo
descending. The message format is:

```text
__**New elo peaks: YYYY-MM-DD**__
- __Player name:__ prior_elo → **new_elo**
```

When no qualifying increase exists, use `- None`. Split messages below Discord's
content limit and use an underlined/bold `(continued)` header. Persist successful
notification state only after every webhook request succeeds.

## Idempotency

Run state is stored under:

```text
gs://ark-nova-stats-dashboard-cache/elo-peak-updater/runs/
```

Scheduled retries use `X-CloudScheduler-ScheduleTime` as the idempotency key. A
scheduler timestamp more than five minutes in the future is treated as an
on-demand invocation and receives a unique `manual-...` key. This prevents a
manual scheduler invocation from consuming the next midnight run's state.

State flags:

```text
sheet_update_applied
notification_sent
```

Retries can therefore resume notification without reapplying a successful sheet
batch.

## Google Cloud contract

```text
Project: ark-nova-stats-dashboard
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

Scheduler job: update-elo-peaks-daily
Schedule: 0 0 * * *
Timezone: UTC
Method: POST
Authentication: OIDC
Invoker service account:
  elo-peak-updater-scheduler@ark-nova-stats-dashboard.iam.gserviceaccount.com
Attempt deadline: 180 seconds
Retries: 3 with a 5-second minimum backoff
```

The updater schedule is independent of the dashboard's DuckDB refresh. Do not
merge their schedules, run state, or completion timestamps.

## Test, deploy, and diagnose

Run from the updater directory:

```powershell
python -m unittest discover -s tests -v
```

Deploy with the existing function identity and secret mapping:

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

An on-demand production run mutates the sheet and sends a Discord message:

```powershell
gcloud scheduler jobs run update-elo-peaks-daily `
  --project ark-nova-stats-dashboard `
  --location europe-west1
```

Start diagnostics with read-only `gcloud scheduler jobs describe`, `gcloud
functions describe`, Cloud Run revision logs for `update-elo-peaks`, and the
state-bucket run prefix. Inspect state and metadata, never secret values.

## Standalone and dashboard presentation

The standalone site displays the complete maintained ranking. The dashboard
Records/Elo Leaderboard publishes a compact Top 100 snapshot, loads it once
across MW/Base, has no Filter sidebar, and may display `n/a` for Peak Arena.
`n/a` is data, not an error or missing-row reason.

When changing spreadsheet columns, update the updater, standalone parser,
dashboard snapshot builder, tests, and this document together. Preserve player
ID as the authoritative identity even when display names change.
