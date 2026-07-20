"""Pointer protocol — keep big tool outputs OUT of the LLM context.

A tool returns a short pointer; the full payload lives in an external store
(mmapped file dir or object store). This is the IBM 16,000x token-reduction idea,
built in: only the pointer string ever enters the agent's context window.
"""
from __future__ import annotations

import hashlib
import json
import os
import time


class PointerStore:
    def __init__(self, root: str = ".mesh_pointers"):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def put(self, payload: str, label: str = "") -> str:
        h = hashlib.sha1(payload.encode()).hexdigest()[:16]
        ptr = f"mesh://{label or 'data'}/{h}"
        path = os.path.join(self.root, h + ".json")
        with open(path, "w") as f:
            json.dump({"ptr": ptr, "len": len(payload), "ts": time.time(),
                       "payload": payload}, f)
        return ptr

    def resolve(self, ptr: str) -> str:
        h = ptr.rsplit("/", 1)[-1]
        path = os.path.join(self.root, h + ".json")
        with open(path) as f:
            return json.load(f)["payload"]

    def summarize(self, ptr: str, max_chars: int = 400) -> str:
        p = self.resolve(ptr)
        if len(p) <= max_chars:
            return p
        # cheap extractive summary: first + last + middle slices
        return p[:max_chars // 2] + "\n…[truncated]…\n" + p[-max_chars // 2:]


def store_big_output(payload: str, label: str = "", root: str = ".mesh_pointers") -> str:
    """Return only a pointer. Keep 200KB+ tool output out of context entirely."""
    return PointerStore(root).put(payload, label)
