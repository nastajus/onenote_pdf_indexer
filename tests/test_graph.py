from unittest import TestCase

from onenote_indexer.graph import GraphClient


class GraphRetryTests(TestCase):
    def test_retries_transient_graph_failures(self) -> None:
        client = GraphClient("test-token")
        retry = client.session.get_adapter("https://").max_retries

        self.assertEqual(6, retry.total)
        self.assertTrue(retry.respect_retry_after_header)
        self.assertIn(429, retry.status_forcelist)
        self.assertIn(504, retry.status_forcelist)
