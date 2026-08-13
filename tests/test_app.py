import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from app import ApplicationHandler
from tests.test_settlement_engine import valid_payload


class ApiWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ApplicationHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=body,
            headers={"Content-Type": "application/json"} if body else {},
            method="POST" if body else "GET",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, response.read(), response.headers

    def test_complete_browser_to_engine_api_workflow(self):
        status, body, headers = self.request("/api/analyze", valid_payload())
        result = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers["Content-Type"])
        self.assertGreater(result["summary"]["totalPrimarySettlementMm"], 0)
        self.assertEqual(len(result["layers"]), 1)
        self.assertGreater(len(result["calculationDetails"]), 5)
        self.assertEqual(len(result["timeSeries"]), 26)

    def test_api_returns_field_errors_without_calculating(self):
        payload = valid_payload()
        payload["loading"]["q"] = ""
        try:
            self.request("/api/analyze", payload)
            self.fail("Expected HTTP 422")
        except urllib.error.HTTPError as error:
            result = json.loads(error.read())
            self.assertEqual(error.code, 422)
            self.assertIn("loading.q", result["errors"])

    def test_static_application_is_served(self):
        status, body, headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"Terzaghi Settlement Analysis", body)


if __name__ == "__main__":
    unittest.main()