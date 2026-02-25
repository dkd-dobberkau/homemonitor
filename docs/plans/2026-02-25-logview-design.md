# Design: Event Logview

## Goal

Add a second view to the HomeMonitor dashboard showing a chronological event log of all state changes (device + security), accessible via tabs in the header.

## Architecture

Backend change-detection using SQL `LAG()` window functions to identify state changes across consecutive poll readings. A single `/api/events` endpoint combines changes from both `device_readings` and `security_readings` tables.

Frontend renders events as a compact, color-coded list. Navigation via tab buttons in the header (SPA-style, no page reload).

## API — `/api/events`

**Parameters:**
- `period` — 1h, 6h, 24h, 7d (default: 24h)
- `type` — `device`, `security`, `all` (default: all)

**SQL approach:** `LAG()` window function compares current value with previous value per device/group + metric. Only rows where value changed are returned. Both tables queried and UNION'd.

**Tracked metrics from device_readings:**
- `window_state` (text comparison)
- `motion_detected` (numeric)
- `smoke_alarm` (text)
- `water_detected` (numeric)
- `moisture_detected` (numeric)
- `low_battery` (numeric)
- `unreachable` (numeric)

**Tracked metrics from security_readings:**
- `zone_active` (numeric)
- `siren_on` (numeric)
- `sabotage` (numeric)
- `window_state` (text)
- `motion_detected` (numeric)

**Response format:**
```json
[
  {
    "timestamp": "2026-02-25T08:15:00+00:00",
    "source": "Haustuer",
    "event": "window_state",
    "old_value": "CLOSED",
    "new_value": "OPEN",
    "severity": "warning"
  }
]
```

**Severity mapping (computed in backend):**
- `critical`: smoke_alarm (not IDLE_OFF), water_detected=1, sabotage=1, siren_on=1
- `warning`: window_state=OPEN, low_battery=1, unreachable=1
- `info`: everything else (motion, zone changes, window closed, battery ok, reachable)

## Navigation

Tab buttons in the header, left of period buttons:

```
[HomeMonitor]   [Dashboard] [Log]   |  1h  6h  24h  7d  |  DE  EN
```

- Active tab highlighted (same style as active period button)
- Tab switch shows/hides containers (no page reload, pure JS)
- Period buttons and auto-refresh apply to both views
- URL stays `/`

## Logview UI

Chronological event list (newest first), color-coded by severity:

- Each row: `[Timestamp] [Severity-Icon] [Source] [Event description]`
- Red background: critical events
- Yellow/amber background: warning events
- Neutral/no background: info events
- Compact rows, mobile-friendly
- Auto-refresh every 60s (same as dashboard)
- Empty state: "Keine Ereignisse im Zeitraum" / "No events in this period"

**I18N:** Event descriptions translated (DE/EN). New keys for event type labels and severity descriptions.

**No additional filters** (no dropdown for event type) — YAGNI.

## Files Modified

1. `dashboard/app.py` — new `/api/events` endpoint with LAG() window function queries
2. `dashboard/templates/index.html` — tab navigation, log container, log rendering JS, i18n keys, CSS
