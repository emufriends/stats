import json
import pathlib
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from phase3_api import Phase3Application, Phase3HTTPHandler
from phase3_duckdb_service import (
    DuckDBServingStore,
    GenerationManager,
    Phase3RequestAdapter,
    ServingStateError,
)


class Phase3ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from phase3_duckdb_service import _load_duckdb

            cls.duckdb = _load_duckdb()
        except ServingStateError as exc:  # pragma: no cover - environment-specific
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temporary.name)
        generations = root / "generations"
        generations.mkdir()
        database = generations / "g1.duckdb"
        connection = self.duckdb.connect(str(database))
        connection.execute(
            "CREATE TABLE card_component_by_table_narrow("
            "card_name VARCHAR, card_type VARCHAR, table_id BIGINT, "
            "delta_count BIGINT, delta_sum DOUBLE, delta_sum_squares DOUBLE)"
        )
        connection.execute(
            "INSERT INTO card_component_by_table_narrow VALUES "
            "('Bamboo Forest','project',1,2,0.4,0.08),"
            "('Bamboo Forest','project',2,1,0.2,0.04)"
        )
        connection.execute(
            "CREATE TABLE game_player_narrow("
            "table_id BIGINT, player VARCHAR, player_id VARCHAR, is_mw INTEGER, "
            "map_name VARCHAR, game_date DATE, game_ended_at TIMESTAMP, "
            "starting_position VARCHAR, pre_match_elo DOUBLE, post_match_elo DOUBLE, "
            "elo_delta DOUBLE, result_code INTEGER, concede BOOLEAN, "
            "end_game_triggered BOOLEAN)"
        )
        connection.execute("CREATE TABLE corrupted_tables_narrow(table_id BIGINT)")
        connection.execute("CREATE TABLE completed_tables_narrow(table_id BIGINT)")
        connection.execute(
            "CREATE TABLE source_full_sample("
            "table_id BIGINT, player VARCHAR, pre_match_elo DOUBLE, elo_delta DOUBLE)"
        )
        connection.execute(
            "INSERT INTO source_full_sample VALUES "
            "(1,'portgard',500,0.2),(2,'portgard',510,0.4)"
        )
        connection.execute(
            "CREATE TABLE prepared_full_sample_narrow AS "
            "SELECT * FROM source_full_sample"
        )
        connection.execute(
            "CREATE TABLE card_play_narrow("
            "table_id BIGINT, player VARCHAR, card_name VARCHAR, "
            "card_type VARCHAR, elo_delta DOUBLE)"
        )
        connection.execute(
            "INSERT INTO card_play_narrow VALUES "
            "(1,'portgard','Bamboo Forest','project',0.2),"
            "(1,'portgard','Bamboo Forest','project',0.3),"
            "(2,'portgard','Bamboo Forest','project',0.4)"
        )
        connection.execute(
            "CREATE TABLE card_in_hand_narrow("
            "table_id BIGINT, player VARCHAR, card_name VARCHAR)"
        )
        connection.execute(
            "INSERT INTO card_in_hand_narrow VALUES "
            "(1,'portgard','Bamboo Forest')"
        )
        connection.execute(
            "CREATE TABLE card_seen_narrow("
            "table_id BIGINT, player VARCHAR, card_name VARCHAR)"
        )
        connection.execute(
            "INSERT INTO card_seen_narrow VALUES "
            "(1,'portgard','Bamboo Forest'),(2,'portgard','Bamboo Forest')"
        )
        connection.execute(
            "CREATE TABLE card_pair_by_table_narrow("
            "card_1 VARCHAR, type_1 VARCHAR, card_2 VARCHAR, type_2 VARCHAR, "
            "table_id BIGINT, player VARCHAR, observation_count BIGINT, "
            "delta_count BIGINT, delta_sum DOUBLE, delta_sum_squares DOUBLE, "
            "elo_count BIGINT, elo_sum DOUBLE)"
        )
        connection.execute(
            "CREATE TABLE card_component_aggregate_narrow AS "
            "SELECT card_name, card_type, SUM(delta_count) AS delta_count, "
            "SUM(delta_sum) AS delta_sum, SUM(delta_sum_squares) AS delta_sum_squares, "
            "COUNT(*) AS cluster_count FROM card_component_by_table_narrow "
            "GROUP BY card_name, card_type"
        )
        connection.execute(
            "CREATE TABLE card_pair_aggregate_narrow AS "
            "SELECT CAST(NULL AS VARCHAR) AS card_1, CAST(NULL AS VARCHAR) AS type_1, "
            "CAST(NULL AS VARCHAR) AS card_2, CAST(NULL AS VARCHAR) AS type_2, "
            "CAST(NULL AS BIGINT) AS observation_count, CAST(NULL AS BIGINT) AS delta_count, "
            "CAST(NULL AS DOUBLE) AS delta_sum, CAST(NULL AS DOUBLE) AS delta_sum_squares, "
            "CAST(NULL AS BIGINT) AS elo_count, CAST(NULL AS DOUBLE) AS elo_sum "
            "WHERE FALSE"
        )
        connection.close()
        (generations / "g1.manifest.json").write_text(
            json.dumps({"status": "ok", "generation": "g1", "data_version": "v1"}),
            encoding="utf-8",
        )
        self.manager = GenerationManager(generations)
        self.manager.activate("g1")
        adapter = Phase3RequestAdapter(DuckDBServingStore(self.manager))
        self.app = Phase3Application(self.manager, adapter)

    def tearDown(self):
        self.temporary.cleanup()

    def test_health_readiness_status_and_capabilities(self):
        status, health = self.app.dispatch("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertTrue(health["ready"])
        self.assertNotIn("database", health)
        self.assertNotIn("manifest", health)
        status, readiness = self.app.dispatch("GET", "/readyz")
        self.assertEqual(status, 200)
        self.assertTrue(readiness["ready"])
        status, serving = self.app.dispatch("GET", "/v1/status")
        self.assertEqual(status, 200)
        self.assertEqual(serving["generation"], "g1")
        self.assertNotIn("database", serving)
        status, capabilities = self.app.dispatch("GET", "/v1/capabilities")
        self.assertEqual(status, 200)
        self.assertFalse(capabilities["phase4_required"])
        self.assertEqual(capabilities["native_route_count"], 50)
        self.assertEqual(capabilities["phase4_pending_route_count"], 0)
        phase4 = {
            (page["stats_page"], view["view"]): view["status"]
            for page in capabilities["pages"]
            for view in page["views"]
        }
        self.assertEqual(phase4[("maps", "metrics")], "native_phase4")
        self.assertEqual(phase4[("endgames", "general")], "native_phase4")
        self.assertEqual(phase4[("endgames", "cp_distribution")], "native_phase4")
        self.assertEqual(phase4[("predictors", "specific")], "native_phase4")
        self.assertEqual(phase4[("combinations", "card_action_card")], "native_phase4")
        self.assertEqual(phase4[("players", "performance_by_map")], "native_phase4")
        self.assertEqual(phase4[("scoring", "final_score")], "native_phase4")
        self.assertEqual(phase4[("icons", "default")], "native_phase4")

    def test_native_query_after_phase4_completion(self):
        status, payload = self.app.dispatch(
            "POST",
            "/v1/query",
            json.dumps({"stats_page": "cards", "limit": 10}).encode(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["row_count"], 1)
        self.assertEqual(payload["data"][0]["n_played"], 2)
        self.assertEqual(payload["data"][0]["delta_played_ci_n"], 3)

    def test_protocol_errors_are_explicit(self):
        self.assertEqual(self.app.dispatch("POST", "/v1/query", b"{")[0], 400)
        self.assertEqual(self.app.dispatch("GET", "/v1/query")[0], 405)
        self.assertEqual(self.app.dispatch("GET", "/missing")[0], 404)

    def test_query_concurrency_is_bounded(self):
        limited = Phase3Application(
            self.manager, self.app.adapter, max_concurrent_queries=1,
            query_slot_wait_seconds=0,
        )
        self.assertTrue(limited.query_slots.acquire(blocking=False))
        try:
            status, payload = limited.dispatch(
                "POST",
                "/v1/query",
                json.dumps({"stats_page": "cards"}).encode(),
            )
            self.assertEqual(status, 503)
            self.assertEqual(payload["error"], "serving_busy")
        finally:
            limited.query_slots.release()

    def test_http_handler_serves_json_without_public_bind(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Phase3HTTPHandler)
        server.phase3_app = self.app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/v1/capabilities",
                timeout=5,
            ) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store, max-age=0")
                payload = json.load(response)
                self.assertEqual(payload["phase4_pending_route_count"], 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
