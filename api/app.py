"""Vercel Flask entry point for the Terzaghi Settlement Analysis System."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge, UnsupportedMediaType

from settlement_engine import EngineeringValidationError, analyze_settlement


app = Flask(__name__, static_folder="../static", static_url_path="/static")

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
app.config["MAX_CONTENT_LENGTH"] = 2_000_000


@app.route("/api/analyze", methods=["POST"])
def analyze():
    try:
        payload = request.get_json()
        if not isinstance(payload, dict):
            raise EngineeringValidationError(
                {"request": "Analysis request must be a JSON object."}
            )
        return jsonify(analyze_settlement(payload)), 200
    except EngineeringValidationError as error:
        return jsonify({
            "message": "Correct the highlighted engineering inputs.",
            "errors": error.errors,
        }), 422
    except (BadRequest, RequestEntityTooLarge, UnsupportedMediaType):
        return jsonify({"message": "Request body is not valid JSON."}), 400
    except Exception as error:
        print(f"Unexpected calculation error: {error}")
        return jsonify({
            "message": "The analysis could not be completed due to an internal error."
        }), 500


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    if path == "":
        path = "index.html"
    file_path = STATIC / path
    if file_path.exists() and file_path.is_file():
        return send_from_directory(STATIC, path)
    return "Not Found", 404
