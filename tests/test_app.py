import unittest
import json
from pathlib import Path

from api.app import app
from tests.test_settlement_engine import valid_payload


class ApiWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True)
        cls.client = app.test_client()

    def test_complete_browser_to_engine_api_workflow(self):
        response = self.client.post("/api/analyze", json=valid_payload())
        result = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertGreater(result["summary"]["totalPrimarySettlementMm"], 0)
        self.assertEqual(len(result["layers"]), 1)
        self.assertGreater(len(result["calculationDetails"]), 5)
        self.assertEqual(len(result["timeSeries"]), 26)

    def test_api_returns_field_errors_without_calculating(self):
        payload = valid_payload()
        payload["loading"]["q"] = ""

        response = self.client.post("/api/analyze", json=payload)
        result = response.get_json()

        self.assertEqual(response.status_code, 422)
        self.assertIn("loading.q", result["errors"])

    def test_api_rejects_invalid_json(self):
        response = self.client.post(
            "/api/analyze",
            data="not-json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["message"], "Request body is not valid JSON."
        )

    def test_api_rejects_non_json_request(self):
        response = self.client.post("/api/analyze", data="plain text")

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.is_json)

    def test_static_application_is_served(self):
        response = self.client.get("/")
        try:
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.content_type)
            self.assertIn(b"Terzaghi Settlement Analysis", response.data)
        finally:
            response.close()

    def test_static_assets_are_served(self):
        stylesheet = self.client.get("/static/styles.css")
        javascript = self.client.get("/static/app.js")
        try:
            self.assertEqual(stylesheet.status_code, 200)
            self.assertIn("text/css", stylesheet.content_type)
            self.assertEqual(javascript.status_code, 200)
            self.assertIn("javascript", javascript.content_type)
        finally:
            stylesheet.close()
            javascript.close()

    def test_unknown_static_path_returns_404(self):
        response = self.client.get("/missing-file.css")

        self.assertEqual(response.status_code, 404)

    def test_index_uses_relative_same_origin_static_assets(self):
        response = self.client.get("/")
        try:
            html = response.get_data(as_text=True)
            self.assertIn('href="static/styles.css"', html)
            self.assertIn('src="static/app.js"', html)
        finally:
            response.close()

    def test_vercel_routes_api_before_spa_catch_all(self):
        config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))

        self.assertEqual(config["routes"], [
            {"src": "/api/(.*)", "dest": "/api/app.py"},
            {"src": "/(.*)", "dest": "/api/app.py"},
        ])

    def test_navigation_script_is_delivered_with_session_restore(self):
        response = self.client.get("/static/app.js")
        try:
            script = response.get_data(as_text=True)
            self.assertIn("function navigateToSection", script)
            self.assertIn("event.preventDefault()", script)
            self.assertIn("target.hidden = false", script)
            self.assertNotIn("Run a valid analysis before opening result sections", script)
            self.assertIn("sessionStorage.setItem", script)
            self.assertIn("restoreAnalysisSession()", script)
        finally:
            response.close()


if __name__ == "__main__":
    unittest.main()