"""Read-only dashboard filter benchmark.

Runs representative cache-miss-shaped requests for every dynamic view and
records browser wall time plus the Function's Server-Timing/X-Request-Id
headers. It never requests maintenance work and never mutates source data.
"""

import argparse
import json
import time
import urllib.error
import urllib.request


STANDARD_MAPS = [
    "Map 1a: Observation Tower", "Map 2a: Outdoor Areas",
    "Map 3a: Silver Lake", "Map 4a: Commercial Harbor",
    "Map 5a: Park Restaurant", "Map 6a: Research Institute",
    "Map 7a: Ice Cream Parlors", "Map 8a: Hollywood Hills",
    "Map 9: Geographical Zoo", "Map 10: Rescue Station",
    "Map 11: Caves", "Map 12: Artificial Intelligence",
    "Map 13: Drawing Board", "Map 14: Lagoon", "Map T1: Tournament 1",
]


def base(page, **extra):
    payload = {
        "stats_page": page, "is_mw": 1, "maps": STANDARD_MAPS,
        "player_elo_min": 301, "opponent_elo_min": 300,
        "date_from": "2025-01-01",
    }
    payload.update(extra)
    return payload


CASES = [
    ("home", base("home", maps=STANDARD_MAPS[:14])),
    ("cards", base("cards")),
    ("cards-round", base("cards", rounds=["1"])),
    ("opening-hand", base("opening_hand")),
    ("endgames-general", base("endgames", endgames_view="general")),
    ("endgames-cp", base("endgames", endgames_view="cp_distribution")),
    ("endgames-map", base("endgames", endgames_view="cp_by_map")),
    ("maps-metrics", base("maps", maps_view="metrics")),
    ("sponsor-cp", base("sponsor_endgames", sponsor_endgames_view="cp")),
    ("sponsor-appeal", base("sponsor_endgames", sponsor_endgames_view="appeal")),
    ("combos-card-card", base("combinations", combinations_view="card_card", combination_paged=True, combination_page=1, combination_page_size=50, combination_min_plays=1000)),
    ("combos-card-map", base("combinations", combinations_view="card_map", combination_paged=True, combination_page=1, combination_page_size=50, combination_min_plays=1000)),
    ("combos-card-round", base("combinations", combinations_view="card_round", combination_paged=True, combination_page=1, combination_page_size=50, combination_min_plays=1000)),
    ("combos-card-endgame", base("combinations", combinations_view="card_endgame", combination_paged=True, combination_page=1, combination_page_size=50, combination_min_plays=1000)),
    ("combos-card-action", base("combinations", combinations_view="card_action_card", combination_paged=True, combination_page=1, combination_page_size=50, combination_min_plays=1000)),
    ("icons", base("icons")),
    ("predictors-general", base("predictors", predictors_view="general")),
    ("predictors-icon", base("predictors", predictors_view="icon")),
    ("predictors-specific", base("predictors", predictors_view="specific")),
    ("actions-starting", base("actions", actions_view="starting_position")),
    ("actions-upgrades", base("actions", actions_view="upgrades")),
    ("actions-order", base("actions", actions_view="upgrade_order")),
    ("actions-map", base("actions", actions_view="upgrades_by_map")),
    ("mw-action-general", base("mw_action_cards", mw_action_cards_view="general")),
    ("mw-action-map", base("mw_action_cards", mw_action_cards_view="by_map")),
    ("mw-action-synergies", base("mw_action_cards", mw_action_cards_view="synergies")),
    ("build-enclosures", base("build", build_view="enclosures")),
    ("build-hexes", base("build", build_view="hexes")),
    ("conservation-projects", base("conservation", conservation_view="projects")),
    ("conservation-project-rewards", base("conservation", conservation_view="project_rewards")),
    ("conservation-cp-rewards", base("conservation", conservation_view="cp_rewards")),
    ("scoring-score", base("scoring", scoring_view="final_score")),
    ("scoring-appeal", base("scoring", scoring_view="appeal")),
    ("scoring-cp", base("scoring", scoring_view="conservation_points")),
    ("scoring-reputation", base("scoring", scoring_view="reputation")),
    ("workers-general", base("workers", workers_view="general")),
    ("workers-2cp", base("workers", workers_view="two_cp_worker")),
    ("players-general", base("players", players_view="general", maps=STANDARD_MAPS, opponent_elo_min=1, players_player="Propaganda Panda")),
    ("players-comparison", base("players", players_view="comparison", maps=STANDARD_MAPS, opponent_elo_min=1, players_players=["Propaganda Panda", "New Zealand fur seal"])),
]


def run_case(endpoint, name, payload, timeout):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=body,
        headers={"Content-Type": "application/json", "Accept-Encoding": "identity"},
    )
    started = time.perf_counter()
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw).get("message")
        except Exception:
            detail = raw.decode("utf-8", errors="replace")[:500]
        return {
            "name": name, "seconds": round(time.perf_counter() - started, 3),
            "status": exc.code, "error": detail, "within_budget": False,
            "request_id": exc.headers.get("X-Request-Id", ""),
            "server_timing": exc.headers.get("Server-Timing", ""),
        }
    with response:
        raw = response.read()
        status = response.status
        server_timing = response.headers.get("Server-Timing", "")
        request_id = response.headers.get("X-Request-Id", "")
    elapsed = round(time.perf_counter() - started, 3)
    parsed = json.loads(raw)
    return {
        "name": name, "seconds": elapsed, "status": status,
        "rows": len(parsed.get("data") or []), "cache": parsed.get("cache_status"),
        "server_timing": server_timing, "request_id": request_id,
        "within_budget": elapsed <= 5.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("endpoint")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--player-elo-min", type=int,
                        help="Override the benchmark Player Elo minimum.")
    parser.add_argument("--starting-position", choices=("First player", "Second player"),
                        help="Apply the global First-player advantage filter.")
    parser.add_argument("--only", action="append", default=[],
                        help="Run only case names containing this value (repeatable).")
    parser.add_argument("--output")
    args = parser.parse_args()
    results = []
    for _ in range(args.repeat):
        for name, payload in CASES:
            if args.only and not any(value in name for value in args.only):
                continue
            request_payload = dict(payload)
            if args.player_elo_min is not None:
                request_payload["player_elo_min"] = args.player_elo_min
            if args.starting_position:
                request_payload["starting_positions"] = [args.starting_position]
            try:
                result = run_case(args.endpoint, name, request_payload, args.timeout)
            except Exception as exc:  # report and continue through the matrix
                result = {"name": name, "error": str(exc), "within_budget": False}
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(results, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
