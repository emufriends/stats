import json
import pathlib
import tempfile
import unittest

from phase3_duckdb_service import (
    DuckDBServingStore,
    Phase3AuditLog,
    GenerationManager,
    Phase3PersistentResponseCache,
    Phase3RequestAdapter,
    Phase3ResponseCache,
    PUBLIC_CONTRACT_SCHEMA_VERSION,
    ServingStateError,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]


class Phase3GenerationTests(unittest.TestCase):
    def _generation(self, root, generation_id, value):
        (root / "generations").mkdir(parents=True, exist_ok=True)
        database = root / "generations" / f"{generation_id}.duckdb"
        manifest = root / "generations" / f"{generation_id}.manifest.json"
        database.write_bytes(b"placeholder")
        manifest.write_text(
            json.dumps(
                {
                    "status": "ok",
                    "generation": generation_id,
                    "data_version": generation_id,
                    "test_value": value,
                }
            ),
            encoding="utf-8",
        )

    def test_activation_is_atomic_and_rollback_uses_previous_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._generation(root, "g1", 1)
            self._generation(root, "g2", 2)
            manager = GenerationManager(root / "generations")

            self.assertIsNone(manager.current())
            self.assertEqual(manager.activate("g1").generation_id, "g1")
            self.assertEqual(manager.activate("g2").generation_id, "g2")
            self.assertEqual(manager.status()["previous_generation"], "g1")
            self.assertEqual(manager.rollback().generation_id, "g1")
            self.assertEqual(manager.status()["previous_generation"], "g2")

    def test_invalid_candidate_cannot_change_active_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._generation(root, "good", 1)
            manager = GenerationManager(root / "generations")
            manager.activate("good")

            with self.assertRaises(ServingStateError):
                manager.activate("missing")
            self.assertEqual(manager.current().generation_id, "good")

    def test_staging_validates_before_activation_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._generation(root, "old", 1)
            source_db = root / "incoming.duckdb"
            source_manifest = root / "incoming.manifest.json"
            source_db.write_bytes(b"new-generation")
            source_manifest.write_text(
                json.dumps({"status": "ok", "generation": "new", "data_version": "v2"}),
                encoding="utf-8",
            )
            source_manifest_newer = root / "incoming-newer.manifest.json"
            source_manifest_newer.write_text(
                json.dumps({"status": "ok", "generation": "newer", "data_version": "v3"}),
                encoding="utf-8",
            )
            manager = GenerationManager(root / "generations")
            manager.activate("old")
            staged = manager.stage("new", source_db, source_manifest)
            self.assertEqual(staged.generation_id, "new")
            self.assertEqual(manager.current().generation_id, "old")
            promoted = manager.stage_and_activate("newer", source_db, source_manifest_newer)
            self.assertEqual(promoted.generation_id, "newer")
            self.assertEqual(manager.current().generation_id, "newer")
            with self.assertRaises(ServingStateError):
                manager.stage("new", source_db, source_manifest)

    def test_generation_ids_are_path_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = GenerationManager(pathlib.Path(directory) / "generations")
            with self.assertRaises(ServingStateError):
                manager.activate("../outside")

    def test_cache_key_changes_with_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._generation(root, "g1", 1)
            self._generation(root, "g2", 2)
            manager = GenerationManager(root / "generations")
            request = {"view": "cards", "limit": 100, "offset": 0}
            self.assertNotEqual(
                Phase3ResponseCache.key_for(manager.inspect("g1"), request),
                Phase3ResponseCache.key_for(manager.inspect("g2"), request),
            )

    def test_store_can_pin_an_inactive_candidate_without_changing_pointer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._generation(root, "active", 1)
            self._generation(root, "candidate", 2)
            manager = GenerationManager(root / "generations")
            manager.activate("active")
            store = DuckDBServingStore(manager, generation_id="candidate")
            self.assertEqual(store.generation().generation_id, "candidate")
            self.assertEqual(manager.current().generation_id, "active")

    def test_readiness_checks_active_and_rollback_generations_and_audits_events(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._generation(root, "g1", 1)
            self._generation(root, "g2", 2)
            audit = Phase3AuditLog(root / "audit.jsonl")
            manager = GenerationManager(root / "generations", audit_log=audit)
            manager.activate("g1")
            self.assertTrue(manager.readiness()["ready"])
            self.assertFalse(manager.readiness()["rollback_ready"])
            manager.activate("g2")
            self.assertTrue(manager.readiness()["rollback_ready"])
            manager.rollback()
            events = audit.recent()
            names = [event["event"] for event in events]
            self.assertIn("generation_activated", names)
            self.assertIn("generation_rolled_back", names)
            self.assertIn("readiness_checked", names)
            self.assertTrue(all("sql" not in event for event in events))


class Phase3ReadOnlyStoreTests(unittest.TestCase):

    def test_omitted_limit_preserves_complete_frontend_payload_contract(self):
        normalized = Phase3RequestAdapter.normalize_request({"stats_page": "cards"})
        self.assertEqual(normalized["limit"], Phase3RequestAdapter.MAX_LIMIT)

    def _generation(self, root, generation_id, value):
        (root / "generations").mkdir(parents=True, exist_ok=True)
        database = root / "generations" / f"{generation_id}.duckdb"
        manifest = root / "generations" / f"{generation_id}.manifest.json"
        database.write_bytes(b"placeholder")
        manifest.write_text(
            json.dumps(
                {
                    "status": "ok",
                    "generation": generation_id,
                    "data_version": generation_id,
                    "test_value": value,
                }
            ),
            encoding="utf-8",
        )

    @classmethod
    def setUpClass(cls):
        try:
            from phase3_duckdb_service import _load_duckdb

            cls.duckdb = _load_duckdb()
        except ServingStateError as exc:  # pragma: no cover - environment-specific
            raise unittest.SkipTest(str(exc))

    def test_query_is_pinned_to_active_generation_and_write_sql_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            generations = root / "generations"
            generations.mkdir()
            database = generations / "g1.duckdb"
            connection = self.duckdb.connect(str(database))
            connection.execute("CREATE TABLE sample(value INTEGER)")
            connection.execute("INSERT INTO sample VALUES (42)")
            connection.close()
            (generations / "g1.manifest.json").write_text(
                json.dumps({"status": "ok", "generation": "g1", "data_version": "v1"}),
                encoding="utf-8",
            )
            manager = GenerationManager(generations)
            manager.activate("g1")
            store = DuckDBServingStore(manager)

            result = store.query("SELECT value FROM sample")
            self.assertEqual(result["generation"], "g1")
            self.assertEqual(result["data_version"], "v1")
            self.assertEqual(result["rows"], [{"value": 42}])
            self.assertTrue(store.health()["ready"])
            with self.assertRaises(ValueError):
                store.query("DROP TABLE sample")

    def test_trusted_adapter_preserves_generation_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            generations = root / "generations"
            generations.mkdir()
            database = generations / "g1.duckdb"
            connection = self.duckdb.connect(str(database))
            connection.execute(
                "CREATE TABLE card_component_by_table_narrow("
                "card_name VARCHAR, card_type VARCHAR, table_id BIGINT, "
                "delta_count BIGINT, delta_sum DOUBLE, delta_sum_squares DOUBLE, "
                "is_mw INTEGER)"
            )
            connection.execute(
                "INSERT INTO card_component_by_table_narrow VALUES "
                "('Bamboo Forest','project',1,2,0.4,0.08,1),"
                "('Bamboo Forest','project',2,1,0.2,0.04,1),"
                "('Sun Bear','animal',1,1,0.3,0.09,1)"
            )
            connection.execute(
                "CREATE TABLE prepared_full_sample_narrow("
                "table_id BIGINT, player VARCHAR, player_identity VARCHAR, "
                "is_mw INTEGER, Map VARCHAR, pre_match_elo DOUBLE, "
                "opponent_pre_match_elo DOUBLE, post_match_elo DOUBLE, "
                "elo_delta DOUBLE, game_ended_at TIMESTAMP, "
                "starting_position VARCHAR, arena_season VARCHAR, "
                "is_arena_game BOOLEAN, is_tournament BOOLEAN, "
                "is_completed_game BOOLEAN, is_corrupted_game BOOLEAN)"
            )
            connection.execute(
                "INSERT INTO prepared_full_sample_narrow VALUES "
                "(1,'portgard','player:portgard',1,'Map 1a: Observation Tower',"
                "500,490,510,0.2,TIMESTAMP '2026-01-01 00:00:00','First player',"
                "NULL,FALSE,FALSE,TRUE,FALSE),"
                "(2,'other','player:other',1,'Map 1a: Observation Tower',"
                "480,500,475,-0.1,TIMESTAMP '2026-01-02 00:00:00','Second player',"
                "NULL,FALSE,FALSE,TRUE,FALSE)"
            )
            connection.execute(
                "CREATE TABLE card_play_narrow("
                "table_id BIGINT, player VARCHAR, card_name VARCHAR, "
                "card_type VARCHAR, elo_delta DOUBLE)"
            )
            connection.execute(
                "INSERT INTO card_play_narrow VALUES "
                "(1,'portgard','Bamboo Forest','project',0.2),"
                "(1,'portgard','Sun Bear','animal',0.2),"
                "(2,'other','Sun Bear','animal',-0.1),"
                "(2,'other','Bamboo Forest','project',-0.1)"  # second table: component CI needs >=2 clusters
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
                "(1,'portgard','Bamboo Forest'),(2,'other','Sun Bear')"
            )
            connection.execute(
                "CREATE TABLE game_player_narrow("
                "table_id BIGINT, player VARCHAR, player_id VARCHAR, is_mw INTEGER, "
                "map_name VARCHAR, game_date DATE, game_ended_at TIMESTAMP, "
                "starting_position VARCHAR, pre_match_elo DOUBLE, post_match_elo DOUBLE, "
                "elo_delta DOUBLE, result_code INTEGER, concede BOOLEAN, "
                "end_game_triggered BOOLEAN)"
            )
            connection.execute(
                "INSERT INTO game_player_narrow VALUES "
                "(1,'portgard','p1',1,'Map 1a',DATE '2026-01-01',NULL,'First player',"
                "500,510,0.2,1,FALSE,TRUE)"
            )
            connection.execute("CREATE TABLE corrupted_tables_narrow(table_id BIGINT)")
            connection.execute("CREATE TABLE completed_tables_narrow(table_id BIGINT)")
            connection.execute(
                "CREATE TABLE card_pair_by_table_narrow("
                "card_1 VARCHAR, type_1 VARCHAR, card_2 VARCHAR, type_2 VARCHAR, "
                "table_id BIGINT, player VARCHAR, observation_count BIGINT, "
                "delta_count BIGINT, delta_sum DOUBLE, delta_sum_squares DOUBLE, "
                "elo_count BIGINT, elo_sum DOUBLE)"
            )
            connection.execute(
                "INSERT INTO card_pair_by_table_narrow VALUES "
                "('Bamboo Forest','project','Sun Bear','animal',1,'portgard',1,1,0.2,0.04,1,500)"
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
                "SELECT card_1, type_1, card_2, type_2, SUM(observation_count) AS observation_count, "
                "SUM(delta_count) AS delta_count, SUM(delta_sum) AS delta_sum, "
                "SUM(delta_sum_squares) AS delta_sum_squares, SUM(elo_count) AS elo_count, "
                "SUM(elo_sum) AS elo_sum FROM card_pair_by_table_narrow "
                "GROUP BY card_1, type_1, card_2, type_2"
            )
            connection.close()
            (generations / "g1.manifest.json").write_text(
                json.dumps({"status": "ok", "generation": "g1", "data_version": "v1"}),
                encoding="utf-8",
            )
            manager = GenerationManager(generations)
            manager.activate("g1")
            adapter = Phase3RequestAdapter(DuckDBServingStore(manager))

            cards = adapter.execute({"stats_page": "cards", "limit": 10})
            self.assertEqual(cards["generation"], "g1")
            self.assertEqual(cards["row_count"], 2)
            cached = adapter.execute({"stats_page": "cards", "limit": 10})
            self.assertEqual(cached["cache_status"], "private_hit")
            pair = adapter.execute(
                {
                    "stats_page": "combinations",
                    "combinations_view": "card_card",
                    "is_mw": 1,
                    "combination_min_plays": 1,
                }
            )
            self.assertEqual(pair["row_count"], 1)
            ci = adapter.execute(
                {
                    "stats_page": "cards",
                    "component_ci": True,
                    "card_name": "Bamboo Forest",
                    "card_type": "project",
                    "is_mw": 1,
                }
            )
            self.assertEqual(ci["row_count"], 1)
            self.assertIsNotNone(ci["data"][0]["ci95_low"])

    def test_adapter_rejects_unknown_views_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = GenerationManager(pathlib.Path(directory) / "generations")
            adapter = Phase3RequestAdapter(DuckDBServingStore(manager))
            with self.assertRaises(ValueError):
                adapter.normalize_request(
                    {"stats_page": "not_a_page"}
                )

    def test_default_snapshot_fast_path_requires_matching_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self._generation(root, "g1", 1)
            snapshot = root / "snapshots" / "g1" / "card-stats" / "players" / "general"
            snapshot.mkdir(parents=True)
            (snapshot / "default-mw.json").write_text(
                json.dumps({
                    "status": "ok", "data_version": "g1",
                    "contract_schema_version": PUBLIC_CONTRACT_SCHEMA_VERSION,
                    "data": [{"metric": "Games", "all": 42}],
                }),
                encoding="utf-8",
            )
            manager = GenerationManager(root / "generations")
            manager.activate("g1")
            adapter = Phase3RequestAdapter(DuckDBServingStore(manager))
            response = adapter.execute({
                "stats_page": "players", "players_view": "general",
                "is_mw": 1, "limit": 1, "offset": 0,
                "maps": [
                    "1a", "2a", "3a", "4a", "5a", "6a", "7a", "8a",
                    "9", "10", "11", "12", "13", "14", "T1",
                ],
            })
            self.assertEqual(response["source"], "duckdb_private_snapshot")
            self.assertEqual(response["data"], [{"metric": "Games", "all": 42}])
            selected = adapter.normalize_request({
                "stats_page": "players", "players_view": "general",
                "is_mw": 1, "limit": 1, "offset": 0,
                "players_player": "trusting-seagull275",
                "maps": [
                    "1a", "2a", "3a", "4a", "5a", "6a", "7a", "8a",
                    "9", "10", "11", "12", "13", "14", "T1",
                ],
            })
            self.assertIsNone(
                adapter._default_snapshot_response(selected, manager.current())
            )

    def test_cached_responses_are_isolated_from_caller_mutation(self):
        cache = Phase3ResponseCache()
        value = {"data": [{"card_name": "Bamboo Forest"}]}
        cache.put("key", value)
        first = cache.get("key")
        first["data"][0]["card_name"] = "mutated"
        self.assertEqual(cache.get("key")["data"][0]["card_name"], "Bamboo Forest")

    def test_persistent_cache_survives_new_process_cache_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "responses.sqlite3"
            persistent = Phase3PersistentResponseCache(path, max_items=2)
            first = Phase3ResponseCache(persistent=persistent)
            value = {"generation": "g1", "data_version": "v1", "data": [1]}
            first.put("phase3/v1/key", value)

            second = Phase3ResponseCache(
                max_items=2,
                persistent=Phase3PersistentResponseCache(path, max_items=2)
            )
            self.assertEqual(second.get("phase3/v1/key"), value)
            second.put("phase3/v1/key-2", {"generation": "g1", "data": [2]})
            second.put("phase3/v1/key-3", {"generation": "g1", "data": [3]})
            self.assertIsNone(second.get("phase3/v1/key"))


if __name__ == "__main__":
    unittest.main()
