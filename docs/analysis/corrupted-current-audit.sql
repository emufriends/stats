WITH source AS (
  SELECT
    SAFE_CAST(table_id AS INT64) AS table_id,
    SAFE_CAST(is_mw AS INT64) AS is_mw,
    Map AS map_name,
    SAFE_CAST(game_ended_at AS DATE) AS game_date,
    player,
    SAFE_CAST(Game_result AS INT64) AS game_result,
    SAFE_CAST(Number_of_turns AS FLOAT64) AS turns,
    SAFE_CAST(Animals_actions AS FLOAT64) AS animals_actions,
    SAFE_CAST(Association_actions AS FLOAT64) AS association_actions,
    SAFE_CAST(Build_actions AS FLOAT64) AS build_actions,
    SAFE_CAST(Cards_actions AS FLOAT64) AS cards_actions,
    SAFE_CAST(Sponsors_actions AS FLOAT64) AS sponsors_actions,
    SAFE_CAST(X_Tokens_gained_instead_of_action AS FLOAT64) AS x_tokens
  FROM `freestyle-190711.ark_nova.all_games_stat`
), losing AS (
  SELECT *,
    turns - (animals_actions + association_actions + build_actions
      + cards_actions + sponsors_actions + x_tokens) AS gap
  FROM source
  WHERE game_result = 2
    AND turns IS NOT NULL
    AND animals_actions IS NOT NULL
    AND association_actions IS NOT NULL
    AND build_actions IS NOT NULL
    AND cards_actions IS NOT NULL
    AND sponsors_actions IS NOT NULL
    AND x_tokens IS NOT NULL
), corrupted AS (
  SELECT
    table_id,
    MAX(gap) AS max_gap,
    ANY_VALUE(is_mw) AS is_mw,
    ANY_VALUE(map_name) AS map_name,
    MIN(game_date) AS game_date,
    ARRAY_AGG(STRUCT(
      player,
      turns,
      animals_actions + association_actions + build_actions
        + cards_actions + sponsors_actions + x_tokens AS counted_actions,
      gap
    ) ORDER BY gap DESC LIMIT 1)[OFFSET(0)] AS worst_row
  FROM losing
  GROUP BY table_id
  HAVING MAX(gap) >= 2
)
SELECT AS STRUCT
  (SELECT COUNT(*) FROM corrupted) AS corrupted_tables,
  (SELECT COUNT(DISTINCT table_id) FROM source) AS source_tables,
  (SELECT COUNT(*) FROM source) AS source_rows,
  ARRAY(
    SELECT AS STRUCT max_gap, COUNT(*) AS tables
    FROM corrupted GROUP BY max_gap ORDER BY max_gap
  ) AS gap_distribution,
  ARRAY(
    SELECT AS STRUCT is_mw, COUNT(*) AS tables
    FROM corrupted GROUP BY is_mw ORDER BY is_mw
  ) AS dataset_distribution,
  ARRAY(
    SELECT AS STRUCT map_name, COUNT(*) AS tables
    FROM corrupted GROUP BY map_name ORDER BY tables DESC LIMIT 20
  ) AS map_distribution,
  ARRAY(
    SELECT AS STRUCT EXTRACT(YEAR FROM game_date) AS year,
      EXTRACT(MONTH FROM game_date) AS month, COUNT(*) AS tables
    FROM corrupted GROUP BY year, month ORDER BY year, month
  ) AS month_distribution,
  ARRAY(
    SELECT AS STRUCT
      table_id, is_mw, map_name, game_date,
      worst_row.player AS losing_player,
      worst_row.turns, worst_row.counted_actions, worst_row.gap
    FROM corrupted
    ORDER BY FARM_FINGERPRINT(CAST(table_id AS STRING))
    LIMIT 10
  ) AS random_sample
