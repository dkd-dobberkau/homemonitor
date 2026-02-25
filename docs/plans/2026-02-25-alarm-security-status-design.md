# Design: Alarm/Security Status (Task #10)

## Goal

Add alarm and security group data collection to the collector and display it prominently in the dashboard with live status and historical charts.

## Data Sources (homematicip 2.6.0)

From `home.groups`:
- **SecurityZoneGroup**: INTERNAL/EXTERNAL with `active` bool
- **AlarmSwitchingGroup**: SIREN, SIREN_SAFETY, ALARM, BACKUP_ALARM_SIREN with `on` bool
- **SecurityGroup**: per room (Wohnzimmer, Flur, Kueche) with `windowState`, `motionDetected`, `sabotage`

## Database Schema

New table `security_readings`:

```sql
CREATE TABLE security_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    group_id TEXT NOT NULL,
    group_label TEXT,
    group_type TEXT,        -- 'zone', 'alarm', 'room_security'
    metric TEXT NOT NULL,   -- 'zone_active', 'siren_on', 'sabotage', 'window_state', 'motion_detected'
    value INTEGER,          -- 0/1 for booleans
    value_text TEXT
);
CREATE INDEX idx_security_time ON security_readings(timestamp);
CREATE INDEX idx_security_group ON security_readings(group_id, metric);
```

`group_type` values: `zone`, `alarm`, `room_security`

## Collector Changes

New functions in `collector.py`:

- `store_security(conn, group_id, group_label, group_type, metric, value, value_text=None)` — writes to `security_readings`
- `collect_security_data(conn, home)` — iterates `home.groups`, detects type by class name:
  - `SecurityZoneGroup` -> metric `zone_active`, value `int(group.active)`
  - `AlarmSwitchingGroup` -> metric `siren_on`, value `int(group.on)`
  - `SecurityGroup` -> metrics `window_state`, `motion_detected`, `sabotage`
- Called in `poll_once()` after device collection

## Dashboard API

### `/api/security/current`

Returns latest reading per group+metric:

```json
{
  "zones": {"INTERNAL": {"active": true, "timestamp": "..."}, "EXTERNAL": {"active": false}},
  "alarms": {"SIREN": {"on": false}, "ALARM": {"on": false}},
  "rooms": {"Wohnzimmer": {"window_state": "CLOSED", "motion_detected": 0, "sabotage": 0}}
}
```

### `/api/security/readings`

Time-series data with `period` and `metric` params (same pattern as `/api/readings`).

## Dashboard UI

### Alarm Status Card (top position, before existing cards)

- Full-width card at the top of the dashboard
- Color-coded background: green (disarmed, no alarm), yellow (partially armed), red (siren active)
- Shows: "Intern: Scharf / Extern: Unscharf"
- Room security as compact status dots (like window/door contacts)
- Red sabotage warning if active

### Alarm History Chart

- Stepped-line chart (like windows chart) showing zone activation over time
- 2 lines: Internal zone (active/inactive), External zone (active/inactive)
- Placed after motion chart, before system status section

### I18N Keys

New keys for DE/EN: `alarmStatus`, `armed`, `disarmed`, `internalZone`, `externalZone`, `siren`, `sabotageWarning`, `alarmHistory`, `roomSecurity`

## Files Modified

1. `collector.py` — new table init, `store_security()`, `collect_security_data()`, update `poll_once()`
2. `dashboard/app.py` — new endpoints `/api/security/current`, `/api/security/readings`
3. `dashboard/templates/index.html` — alarm card, alarm chart, i18n keys
