"""Disk cache for API responses: keyed by a stable hash of the request params."""
import hashlib
import json
import os

DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".fieldbench", "cache")


def _key(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


class Cache:
    def __init__(self, dirname: str = DEFAULT_DIR):
        self.dirname = dirname
        os.makedirs(dirname, exist_ok=True)

    def path(self, namespace: str, payload: dict) -> str:
        ns_dir = os.path.join(self.dirname, namespace)
        os.makedirs(ns_dir, exist_ok=True)
        return os.path.join(ns_dir, _key(payload) + ".json")

    def get(self, namespace: str, payload: dict):
        p = self.path(namespace, payload)
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
        return None

    def set(self, namespace: str, payload: dict, value) -> None:
        p = self.path(namespace, payload)
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(value, f)
        os.replace(tmp, p)
