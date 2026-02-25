#!/usr/bin/env python3
"""Homematic IP Dashboard - Flask app serving sensor data visualizations."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
DB_PATH = Path("/app/data/homematic.db")

PERIOD_MAP = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/current")
def api_current():
    """Return the latest reading for each device+metric combination."""
    conn = get_db()
    rows = conn.execute("""
        SELECT device_label, device_type, metric, value, value_text, timestamp
        FROM device_readings r1
        WHERE timestamp = (
            SELECT MAX(timestamp) FROM device_readings r2
            WHERE r2.device_id = r1.device_id AND r2.metric = r1.metric
        )
        ORDER BY device_label, metric
    """).fetchall()
    conn.close()

    result = {}
    for row in rows:
        label = row["device_label"]
        if label not in result:
            result[label] = {"device_type": row["device_type"], "metrics": {}}
        result[label]["metrics"][row["metric"]] = {
            "value": row["value"],
            "value_text": row["value_text"],
            "timestamp": row["timestamp"],
        }
    return jsonify(result)


@app.route("/api/security/current")
def api_security_current():
    """Return the latest reading for each security group+metric."""
    conn = get_db()
    rows = conn.execute("""
        SELECT group_label, group_type, metric, value, value_text, timestamp
        FROM security_readings r1
        WHERE timestamp = (
            SELECT MAX(timestamp) FROM security_readings r2
            WHERE r2.group_id = r1.group_id AND r2.metric = r1.metric
        )
        ORDER BY group_type, group_label, metric
    """).fetchall()
    conn.close()

    result = {"zones": {}, "alarms": {}, "rooms": {}}
    for row in rows:
        label = row["group_label"]
        gtype = row["group_type"]

        if gtype == "zone":
            result["zones"][label] = {
                "active": bool(row["value"]),
                "timestamp": row["timestamp"],
            }
        elif gtype == "alarm":
            result["alarms"][label] = {
                "on": bool(row["value"]),
                "timestamp": row["timestamp"],
            }
        elif gtype == "room_security":
            if label not in result["rooms"]:
                result["rooms"][label] = {}
            metric = row["metric"]
            if metric == "window_state":
                result["rooms"][label][metric] = row["value_text"]
            else:
                result["rooms"][label][metric] = row["value"]
            result["rooms"][label]["timestamp"] = row["timestamp"]

    return jsonify(result)


@app.route("/api/security/readings")
def api_security_readings():
    """Return time-series data for security metrics."""
    period = request.args.get("period", "24h")
    metrics = request.args.getlist("metric")

    delta = PERIOD_MAP.get(period, timedelta(hours=24))
    since = (datetime.now(timezone.utc) - delta).isoformat()

    conn = get_db()

    query = """
        SELECT timestamp, group_label, group_type, metric, value, value_text
        FROM security_readings
        WHERE timestamp > ?
    """
    params = [since]

    if metrics:
        placeholders = ",".join("?" for _ in metrics)
        query += f" AND metric IN ({placeholders})"
        params.extend(metrics)

    query += " ORDER BY timestamp ASC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    data = []
    for row in rows:
        data.append({
            "timestamp": row["timestamp"],
            "group_label": row["group_label"],
            "group_type": row["group_type"],
            "metric": row["metric"],
            "value": row["value"],
            "value_text": row["value_text"],
        })
    return jsonify(data)


@app.route("/api/readings")
def api_readings():
    """Return time-series data for given metrics and period."""
    period = request.args.get("period", "24h")
    metrics = request.args.getlist("metric")
    device = request.args.get("device")

    delta = PERIOD_MAP.get(period, timedelta(hours=24))
    since = (datetime.now(timezone.utc) - delta).isoformat()

    conn = get_db()

    query = """
        SELECT timestamp, device_label, metric, value, value_text
        FROM device_readings
        WHERE timestamp > ?
    """
    params = [since]

    if metrics:
        placeholders = ",".join("?" for _ in metrics)
        query += f" AND metric IN ({placeholders})"
        params.extend(metrics)

    if device:
        query += " AND device_label = ?"
        params.append(device)

    query += " ORDER BY timestamp ASC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    data = []
    for row in rows:
        data.append({
            "timestamp": row["timestamp"],
            "device_label": row["device_label"],
            "metric": row["metric"],
            "value": row["value"],
            "value_text": row["value_text"],
        })
    return jsonify(data)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
