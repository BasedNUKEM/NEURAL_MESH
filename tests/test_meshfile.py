"""
Tests for .mesh file format — export/import round-trip, schema validation, re-embedding.
"""
import json
import os
import tempfile
import unittest

from neural_mesh import Mesh, MemoryType, export_mesh, import_mesh


class TestMeshFile(unittest.TestCase):
    def setUp(self):
        self.mesh = Mesh()
        # Seed some test nodes
        self.mesh.add("Base L2 is the home of onchain agents", type=MemoryType.SEMANTIC)
        self.mesh.add("x402 enables agent-to-agent payments", type=MemoryType.SEMANTIC)
        self.mesh.add("NEURAL_MESH ships with cross-agent sharing", type=MemoryType.PROCEDURAL)
        self.mesh.add("Cody is the based chad principal", type=MemoryType.EPISODIC)
        self.mesh.add("Old version of this fact", type=MemoryType.SEMANTIC)
        # Supersede the last one
        nodes = self.mesh._load()
        old_id = None
        for n in nodes.values():
            if n.content == "Old version of this fact":
                old_id = n.id
                break
        if old_id:
            self.mesh.add("Updated version of this fact",
                          type=MemoryType.SEMANTIC,
                          supersedes=old_id)

    def test_export_creates_valid_file(self):
        with tempfile.NamedTemporaryFile(suffix=".mesh", delete=False) as f:
            path = f.name
        try:
            result = export_mesh(self.mesh, path)
            self.assertGreater(result["nodes"], 0)
            self.assertTrue(os.path.exists(path))
            # Check it's valid JSONL
            with open(path) as fh:
                lines = fh.readlines()
                self.assertGreater(len(lines), 1)
                header = json.loads(lines[0])
                self.assertIn("mesh", header)
                self.assertEqual(header["mesh"]["version"], 1)
        finally:
            os.unlink(path)

    def test_round_trip_preserves_content(self):
        with tempfile.NamedTemporaryFile(suffix=".mesh", delete=False) as f:
            path = f.name
        try:
            export_mesh(self.mesh, path)
            # Import into fresh mesh
            fresh = Mesh()
            result = import_mesh(path, fresh, reembed=False)
            self.assertGreater(result["loaded"], 0)
            # Verify content matches
            orig_nodes = {n.content: n for n in self.mesh._load().values()
                          if n.superseded_by != "__pruned__"}
            imported = {n.content: n for n in fresh._load().values()}
            for content, node in orig_nodes.items():
                self.assertIn(content, imported,
                              f"'{content}' should survive round-trip")
        finally:
            os.unlink(path)

    def test_round_trip_preserves_links(self):
        # Add linked nodes — auto_link creates semantic links
        mesh = Mesh()
        n_a = mesh.add("A", type=MemoryType.SEMANTIC)
        n_b = mesh.add("B is related to A", type=MemoryType.SEMANTIC)
        # Manually link B -> A
        n_b.links[n_a.id] = 0.85
        mesh._save(n_b)
        with tempfile.NamedTemporaryFile(suffix=".mesh", delete=False) as f:
            path = f.name
        try:
            export_mesh(mesh, path)
            fresh = Mesh()
            import_mesh(path, fresh, reembed=False)
            imported = {n.content: n for n in fresh._load().values()}
            self.assertIn("A", imported)
            self.assertIn("B is related to A", imported)
            b_node = imported["B is related to A"]
            # Links in .mesh use node IDs, so we check the count
            self.assertGreater(len(b_node.links), 0,
                               "Imported node should retain its links")
        finally:
            os.unlink(path)

    def test_reembed_recomputes_vectors(self):
        with tempfile.NamedTemporaryFile(suffix=".mesh", delete=False) as f:
            path = f.name
        try:
            export_mesh(self.mesh, path)
            fresh = Mesh()
            result = import_mesh(path, fresh, reembed=True)
            self.assertGreater(result["loaded"], 0)
            # Vectors should be non-empty when reembedded
            for n in fresh._load().values():
                self.assertTrue(len(n.embedding) > 0,
                                f"Node '{n.content[:30]}' should have non-empty embedding after reembed")
        finally:
            os.unlink(path)

    def test_rejects_wrong_version(self):
        with tempfile.NamedTemporaryFile(suffix=".mesh", delete=False) as f:
            path = f.name
        try:
            with open(path, "w") as fh:
                fh.write(json.dumps({"mesh": {"version": 999, "embedder": None,
                                              "generated_at": 0, "node_count": 0}}) + "\n")
            with self.assertRaises(ValueError):
                import_mesh(path, Mesh())
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()