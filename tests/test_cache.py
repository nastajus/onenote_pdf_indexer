from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from onenote_indexer import cache


class ReplaceResourcesTests(TestCase):
    def test_duplicate_urls_are_stored_once(self) -> None:
        with TemporaryDirectory() as directory:
            db = cache.connect(Path(directory) / "cache.sqlite3")
            resources = [
                {"url": "https://example.test/resource", "kind": "application/pdf", "alt": "first"},
                {"url": "https://example.test/resource", "kind": "application/pdf", "alt": "duplicate"},
            ]

            cache.replace_resources(db, "page-1", resources)

            stored = cache.get_resources(db, "page-1")
            self.assertEqual(1, len(stored))
            self.assertEqual("first", stored[0]["alt"])
