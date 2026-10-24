"""Authenticated Pub/Sub receiver that stops the DuckDB VM at the hard budget threshold."""

from __future__ import annotations

import base64
import ast
import json
import os
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession
from flask import Flask, jsonify, request

try:
    from .policy import evaluate_budget_notification
except ImportError:  # Cloud Run source deployment imports app.py as a module root.
    from policy import evaluate_budget_notification


PROJECT = os.environ.get("COMPUTE_PROJECT", "ark-nova-stats-dashboard")
ZONE = os.environ.get("COMPUTE_ZONE", "europe-west1-c")
INSTANCE = os.environ.get("COMPUTE_INSTANCE", "ark-nova-duckdb-test")
BILLING_CURRENCY = os.environ.get("BUDGET_CURRENCY", "EUR").upper()
HARD_LIMIT = float(os.environ.get("BUDGET_HARD_LIMIT", "40"))
STOP_URL = (
    "https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}"
    "/instances/{instance}/stop"
)

app = Flask(__name__)


def _budget_payload(envelope: dict[str, Any]) -> dict[str, Any]:
    message = envelope.get("message") or envelope
    raw = message.get("data") if isinstance(message, dict) else None
    if isinstance(raw, str):
        decoded = base64.b64decode(raw).decode("utf-8")
        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            # The gcloud Windows CLI can serialize ad-hoc test messages with
            # Python-style quotes; accept that harmless compatibility form.
            value = ast.literal_eval(decoded)
            if isinstance(value, dict):
                return value
            raise
    if isinstance(message, dict):
        return message
    raise ValueError("budget notification payload is not an object")


@app.post("/")
def budget_alert():
    payload = _budget_payload(request.get_json(silent=True) or {})
    decision = evaluate_budget_notification(
        payload, currency=BILLING_CURRENCY, hard_limit=HARD_LIMIT
    )
    if decision["action"] == "ignored_currency_mismatch":
        return jsonify(decision), 409
    if decision["action"] != "stop":
        return jsonify(decision)

    credentials, _ = google.auth.default()
    session = AuthorizedSession(credentials)
    response = session.post(
        STOP_URL.format(project=PROJECT, zone=ZONE, instance=INSTANCE),
        timeout=30,
    )
    response.raise_for_status()
    return jsonify({
        "action": "stop_requested",
        "instance": INSTANCE,
        "threshold": decision["threshold"],
        "hard_limit": HARD_LIMIT,
        "currency": BILLING_CURRENCY,
    })


@app.get("/healthz")
def healthz():
    return jsonify({
        "status": "ok", "billing_currency": BILLING_CURRENCY,
        "hard_limit": HARD_LIMIT, "instance": INSTANCE,
    }), 200
