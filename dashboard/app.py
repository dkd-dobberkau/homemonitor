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
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_severity(metric, new_value, new_text):
    """Determine event severity based on metric and new value."""
    if metric in ('smoke_alarm',) and new_text and new_text != 'IDLE_OFF':
        return 'critical'
    if metric in ('water_detected', 'moisture_detected', 'sabotage') and new_value == 1:
        return 'critical'
    if metric == 'siren_on' and new_value == 1:
        return 'critical'
    if metric == 'window_state' and new_text == 'OPEN':
        return 'warning'
    if metric in ('low_battery', 'unreachable') and new_value == 1:
        return 'warning'
    return 'info'


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/current")
def api_current():
    """Return the latest reading for each device+metric combination."""
    conn = get_db()
    rows = conn.execute("""
        SELECT r.device_label, r.device_type, r.metric, r.value, r.value_text, r.timestamp
        FROM device_readings r
        INNER JOIN (
            SELECT device_id, metric, MAX(timestamp) AS max_ts
            FROM device_readings
            GROUP BY device_id, metric
        ) latest ON r.device_id = latest.device_id
                 AND r.metric = latest.metric
                 AND r.timestamp = latest.max_ts
        ORDER BY r.device_label, r.metric
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
        SELECT r.group_label, r.group_type, r.metric, r.value, r.value_text, r.timestamp
        FROM security_readings r
        INNER JOIN (
            SELECT group_id, metric, MAX(timestamp) AS max_ts
            FROM security_readings
            GROUP BY group_id, metric
        ) latest ON r.group_id = latest.group_id
                 AND r.metric = latest.metric
                 AND r.timestamp = latest.max_ts
        ORDER BY r.group_type, r.group_label, r.metric
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


@app.route("/api/events")
def api_events():
    """Return state-change events from device and security readings."""
    period = request.args.get("period", "24h")
    event_type = request.args.get("type", "all")
    min_severity = request.args.get("min_severity")

    delta = PERIOD_MAP.get(period, timedelta(hours=24))
    since = (datetime.now(timezone.utc) - delta).isoformat()

    conn = get_db()
    events = []

    # Device state changes
    if event_type in ("all", "device"):
        device_rows = conn.execute("""
            SELECT timestamp, device_label AS source, metric,
                   value, value_text,
                   LAG(value) OVER (PARTITION BY device_id, metric ORDER BY timestamp) AS prev_value,
                   LAG(value_text) OVER (PARTITION BY device_id, metric ORDER BY timestamp) AS prev_text
            FROM device_readings
            WHERE timestamp > ?
              AND metric IN ('window_state', 'motion_detected', 'smoke_alarm',
                             'water_detected', 'moisture_detected', 'low_battery', 'unreachable')
            ORDER BY timestamp DESC
        """, [since]).fetchall()

        for row in device_rows:
            val = row["value"]
            txt = row["value_text"]
            prev_val = row["prev_value"]
            prev_txt = row["prev_text"]

            # Skip if no change (compare text for text metrics, value for numeric)
            if txt is not None:
                if txt == prev_txt:
                    continue
                old_display = prev_txt
                new_display = txt
            else:
                if val == prev_val:
                    continue
                old_display = str(prev_val) if prev_val is not None else None
                new_display = str(val) if val is not None else None

            events.append({
                "timestamp": row["timestamp"],
                "source": row["source"],
                "event": row["metric"],
                "old_value": old_display,
                "new_value": new_display,
                "severity": get_severity(row["metric"], val, txt),
            })

    # Security state changes
    if event_type in ("all", "security"):
        security_rows = conn.execute("""
            SELECT timestamp, group_label AS source, metric,
                   value, value_text,
                   LAG(value) OVER (PARTITION BY group_id, metric ORDER BY timestamp) AS prev_value,
                   LAG(value_text) OVER (PARTITION BY group_id, metric ORDER BY timestamp) AS prev_text
            FROM security_readings
            WHERE timestamp > ?
            ORDER BY timestamp DESC
        """, [since]).fetchall()

        for row in security_rows:
            val = row["value"]
            txt = row["value_text"]
            prev_val = row["prev_value"]
            prev_txt = row["prev_text"]

            if txt is not None:
                if txt == prev_txt:
                    continue
                old_display = prev_txt
                new_display = txt
            else:
                if val == prev_val:
                    continue
                old_display = str(prev_val) if prev_val is not None else None
                new_display = str(val) if val is not None else None

            events.append({
                "timestamp": row["timestamp"],
                "source": row["source"],
                "event": row["metric"],
                "old_value": old_display,
                "new_value": new_display,
                "severity": get_severity(row["metric"], val, txt),
            })

    conn.close()

    # Sort combined events by timestamp descending (newest first)
    events.sort(key=lambda e: e["timestamp"], reverse=True)

    if min_severity:
        severity_order = {'critical': 2, 'warning': 1, 'info': 0}
        min_level = severity_order.get(min_severity, 0)
        events = [e for e in events if severity_order.get(e['severity'], 0) >= min_level]

    return jsonify(events)


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
