"""Local HTTP integration checks for per-user provider settings and graph persistence."""

import test_http
from test_http import BrowserClient
import unittest
import urllib.parse
import json


class NewFeatureTests(unittest.TestCase):
    # Reuse the HTTP fixture without running the original tests twice.
    @classmethod
    def setUpClass(cls):
        test_http.HTTPTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        test_http.HTTPTests.tearDownClass.__func__(cls)

    def setUp(self):
        test_http.HTTPTests.setUp(self)

    add = test_http.HTTPTests.add
    query = test_http.HTTPTests.query

    def test_ai_settings_ui_and_encrypted_storage(self):
        res, data = self.client.call("/api/ai/settings")
        self.assertEqual(res, 200)
        self.assertFalse(data["settings"]["keys"]["groq"])
        key = "gsk_private_fixture_not_a_real_key"
        res, data = self.client.call(
            "/api/ai/settings",
            "POST",
            {
                "providers": {"chat": "groq", "embeddings": "none", "voice": "none"},
                "keys": {"groq": key},
            },
        )
        self.assertEqual(res, 200, data)
        self.assertTrue(data["settings"]["keys"]["groq"])
        serialized = json.dumps(data)
        self.assertNotIn(key, serialized)
        self.assertEqual(data["ai"]["chat"], "groq")
        res, data = self.client.call("/api/ai/settings")
        self.assertEqual(data["settings"]["providers"]["chat"], "groq")
        other = BrowserClient(self.base)
        other.register()
        self.assertFalse(other.call("/api/ai/settings")[1]["settings"]["keys"]["groq"])
        self.assertEqual(other.call("/api/capabilities")[1]["ai"]["chat"], "offline")
        res, data = self.client.call("/api/ai/settings", "POST", {"remove_keys": ["groq"]})
        self.assertEqual(res, 200, data)
        self.assertFalse(self.client.call("/api/ai/settings")[1]["settings"]["keys"]["groq"])

    def test_mindmap_positions_edges_owner_and_delete(self):
        first = self.add(title="A", body="Graph theory")
        second = self.add(title="B", body="Database notes")
        res, data = self.client.call(
            "/api/mindmap/nodes/" + first["id"], "PATCH", {"x": 234.5, "y": 91}
        )
        self.assertEqual(res, 200, data)
        res, data = self.client.call(
            "/api/mindmap/edge", "POST", {"source": first["id"], "target": second["id"]}
        )
        self.assertEqual(res, 201, data)
        edge = data["edge"]["id"]
        res, data = self.client.call("/api/mindmap")
        self.assertEqual(len(data["nodes"]), 1)
        self.assertEqual(data["nodes"][0]["x"], 234.5)
        self.assertEqual(data["edges"][0]["id"], edge)
        other = BrowserClient(self.base)
        other.register()
        self.assertEqual(other.call("/api/mindmap")[1]["edges"], [])
        self.assertEqual(
            other.call("/api/mindmap/nodes/" + first["id"], "PATCH", {"x": 22, "y": 15})[0], 404
        )
        self.assertEqual(
            other.call(
                "/api/mindmap/edge", "POST", {"source": first["id"], "target": second["id"]}
            )[0],
            400,
        )
        self.assertEqual(self.client.call("/api/mindmap/edges/" + edge, "DELETE")[0], 200)
        self.assertEqual(self.client.call("/api/mindmap/layout", "DELETE")[0], 200)
        self.assertEqual(self.client.call("/api/mindmap")[1], {"nodes": [], "edges": []})

    def test_multiword_search_prefers_relevant_document(self):
        unrelated = self.add(
            title="DBMS Note", body="First Normal Form uses atomic values in data tables"
        )
        relevant = self.add(
            title="Graph Algorithms",
            body="Breadth-first search explores graph nodes level by level",
        )
        matches = self.query("breadth-first search")
        ids = [m["item"]["id"] for m in matches]
        self.assertIn(relevant["id"], ids)
        self.assertNotIn(unrelated["id"], ids)

    def test_mindmap_invalid_coordinates(self):
        first = self.add()
        self.assertEqual(
            self.client.call(
                "/api/mindmap/nodes/" + first["id"], "PATCH", {"x": float("inf"), "y": 1}
            )[0],
            400,
        )
        self.assertEqual(
            self.client.call("/api/mindmap/nodes/" + first["id"], "PATCH", {"x": 10001, "y": 1})[0],
            400,
        )


if __name__ == "__main__":
    unittest.main()
