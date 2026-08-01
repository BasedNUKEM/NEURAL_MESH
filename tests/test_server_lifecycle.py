"""REST smoke tests for the integrated lifecycle endpoint."""
from __future__ import annotations

import os
import tempfile
import unittest

import server
from neural_mesh import MemoryLifecycle, Mesh


class TestLifecycleEndpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        server.mesh = Mesh(":memory:")
        server.lifecycle = MemoryLifecycle(
            server.mesh,
            pointer_root=os.path.join(self.tmp.name, "pointers"),
            pointer_threshold=64,
        )
        server.app.config["TESTING"] = True
        self.client = server.app.test_client()

    def tearDown(self):
        server.mesh.db.close()
        self.tmp.cleanup()

    def test_add_endpoint_accepts_memory_type(self):
        response = self.client.post("/mesh/add", json={
            "content": "ship with the release checklist",
            "type": "procedural",
            "provenance": "test",
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["type"], "procedural")

    def test_cycle_endpoint_externalizes_and_serializes_hits(self):
        response = self.client.post("/mesh/cycle", json={
            "payload": "deploy trace " * 20,
            "query": "deploy trace",
            "label": "trace",
            "type": "episodic",
            "hot_ttl": 0,
            "cold_threshold": 0,
        })

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_json()
        self.assertTrue(body["ingest"]["externalized"])
        self.assertEqual(body["retrieval"]["mode"], "hybrid")
        self.assertIsInstance(body["retrieval"]["hits"][0]["id"], str)
        self.assertEqual(body["maintenance"]["lanes"]["promoted"], 1)


if __name__ == "__main__":
    unittest.main()
