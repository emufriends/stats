"""Compare representative public snapshot objects with the private pack.

This is intentionally a read-only snapshot comparison. It does not call the
public filtered API and therefore does not start BigQuery work.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path


PUBLIC_ROOT = "https://storage.googleapis.com/ark-nova-stats-dashboard-cache/"
PRIVATE_ROOT = Path("/home/ascri/phase2_private_data/snapshots/phase5-refresh-20260921-155111-phase5")

ROUTES = {
    "cards_mw": "card-stats/default-mw.json",
    "opening_hand_mw": "card-stats/opening-hand/default-mw.json",
    "maps_metrics_mw": "card-stats/maps/metrics/default-mw.json",
    "actions_starting_position_mw": "card-stats/actions/starting_position/delta/default-mw.json",
    "players_general_mw": "card-stats/players/general/default-mw.json",
    "mw_action_cards_general": "card-stats/mw-action-cards/general/default-mw.json",
    "mw_action_cards_by_map": "card-stats/mw-action-cards/by-map/default-mw.json",
    "mw_action_cards_synergies": "card-stats/mw-action-cards/synergies/default-mw.json",
    "combos_card_card_mw": "card-stats/combinations/card-card/default-mw.json",
    "combos_card_action_card_mw": "card-stats/combinations/card-action-card/default-mw.json",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "phase5-snapshot-audit/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def rows(payload: dict) -> list[dict]:
    data = payload.get("data", payload.get("rows", []))
    return data if isinstance(data, list) else []


def stable_key(row: dict) -> tuple:
    for fields in (
        ("card_name", "card_type"),
        ("action_card_name", "action_card_type"),
        ("card_name", "action_card_name"),
        ("player", "player_id"),
        ("map", "map_name"),
        ("action",),
        ("name", "type"),
    ):
        if any(field in row for field in fields):
            return tuple(row.get(field) for field in fields)
    return (json.dumps(row, sort_keys=True, ensure_ascii=False),)


def main() -> int:
    report = {"status": "ok", "routes": []}
    for name, relative in ROUTES.items():
        private_path = PRIVATE_ROOT / relative
        item = {"route": name, "relative": relative}
        try:
            private = load_json(private_path)
            public = fetch_json(PUBLIC_ROOT + relative)
            private_rows = rows(private)
            public_rows = rows(public)
            private_keys = {stable_key(row) for row in private_rows}
            public_keys = {stable_key(row) for row in public_rows}
            same_data_version = public.get("data_version") == private.get("data_version")
            item.update({
                "public_data_version": public.get("data_version"),
                "private_data_version": private.get("data_version"),
                "same_data_version": same_data_version,
                "public_row_count": public.get("row_count", len(public_rows)),
                "private_row_count": private.get("row_count", len(private_rows)),
                "public_key_count": len(public_keys),
                "private_key_count": len(private_keys),
                "common_key_count": len(public_keys & private_keys),
                "status": "ok" if same_data_version else "stale_public",
            })
            if not same_data_version and report["status"] == "ok":
                report["status"] = "stale_public"
        except Exception as exc:  # diagnostic boundary
            item.update({"status": "error", "error": type(exc).__name__, "message": str(exc)})
            report["status"] = "failed"
        report["routes"].append(item)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
