# Event Logview Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an event log view showing all state changes (device + security) as a chronological, color-coded list, accessible via tabs in the dashboard header.

**Architecture:** New `/api/events` endpoint uses SQL `LAG()` window functions to detect state changes across consecutive readings in both `device_readings` and `security_readings` tables. Frontend adds tab navigation (Dashboard/Log) with SPA-style container switching and a compact event list renderer.

**Tech Stack:** Python 3.12, SQLite (3.25+ for window functions), Flask, vanilla JS

**Design doc:** `docs/plans/2026-02-25-logview-design.md`

---

### Task 1: Add /api/events endpoint to dashboard

**Files:**
- Modify: `dashboard/app.py` — add new route + severity helper

**Step 1: Add severity helper function**

Add before the route definitions (after `get_db()`, around line 25):

```python
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
```

**Step 2: Add the /api/events endpoint**

Add after the existing `/api/security/readings` route (after line 141):

```python
@app.route("/api/events")
def api_events():
    """Return state-change events from device and security readings."""
    period = request.args.get("period", "24h")
    event_type = request.args.get("type", "all")

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

    return jsonify(events)
```

**Step 3: Test manually**

```bash
curl -s "http://localhost:8080/api/events?period=24h" | python3 -m json.tool
```

Expected: JSON array of event objects (may be empty if no state changes occurred, or contain events if states changed between polls).

**Step 4: Commit**

```bash
git add dashboard/app.py
git commit -m "feat: add /api/events endpoint with LAG() change detection"
```

---

### Task 2: Add I18N keys for Logview

**Files:**
- Modify: `dashboard/templates/index.html` — extend I18N objects

**Step 1: Add German keys**

Add to the `de` object after `sirenActive` (after line 185):

```javascript
                tabDashboard: 'Dashboard',
                tabLog: 'Log',
                eventLog: 'Ereignis-Log',
                noEvents: 'Keine Ereignisse im Zeitraum',
                eventWindowOpened: 'Fenster ge\u00f6ffnet',
                eventWindowClosed: 'Fenster geschlossen',
                eventMotionOn: 'Bewegung erkannt',
                eventMotionOff: 'Keine Bewegung',
                eventZoneArmed: 'Alarm scharf geschaltet',
                eventZoneDisarmed: 'Alarm unscharf geschaltet',
                eventSirenOn: 'Sirene aktiviert',
                eventSirenOff: 'Sirene deaktiviert',
                eventSmokeAlarm: 'Rauchmelder-Alarm',
                eventSmokeOff: 'Rauchmelder: Entwarnung',
                eventWaterDetected: 'Wasser erkannt',
                eventWaterClear: 'Wasser: Entwarnung',
                eventBatteryLow: 'Batterie schwach',
                eventBatteryOk: 'Batterie OK',
                eventUnreachable: 'Ger\u00e4t nicht erreichbar',
                eventReachable: 'Ger\u00e4t wieder erreichbar',
                eventSabotageOn: 'Sabotage erkannt',
                eventSabotageOff: 'Sabotage: Entwarnung',
                eventMoistureOn: 'Feuchtigkeit erkannt',
                eventMoistureOff: 'Feuchtigkeit: Entwarnung',
```

**Step 2: Add English keys**

Add to the `en` object after `sirenActive` (after line 228):

```javascript
                tabDashboard: 'Dashboard',
                tabLog: 'Log',
                eventLog: 'Event Log',
                noEvents: 'No events in this period',
                eventWindowOpened: 'Window opened',
                eventWindowClosed: 'Window closed',
                eventMotionOn: 'Motion detected',
                eventMotionOff: 'No motion',
                eventZoneArmed: 'Alarm armed',
                eventZoneDisarmed: 'Alarm disarmed',
                eventSirenOn: 'Siren activated',
                eventSirenOff: 'Siren deactivated',
                eventSmokeAlarm: 'Smoke alarm',
                eventSmokeOff: 'Smoke alarm: all clear',
                eventWaterDetected: 'Water detected',
                eventWaterClear: 'Water: all clear',
                eventBatteryLow: 'Battery low',
                eventBatteryOk: 'Battery OK',
                eventUnreachable: 'Device unreachable',
                eventReachable: 'Device reachable again',
                eventSabotageOn: 'Sabotage detected',
                eventSabotageOff: 'Sabotage: all clear',
                eventMoistureOn: 'Moisture detected',
                eventMoistureOff: 'Moisture: all clear',
```

**Step 3: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "feat: add logview i18n keys (DE/EN)"
```

---

### Task 3: Add tab navigation to header

**Files:**
- Modify: `dashboard/templates/index.html` — add CSS, HTML, JS for tabs

**Step 1: Add CSS for tabs**

Add before `@media` rule (before the line with `@media (max-width: 768px)`):

```css
        .view-tabs { display: flex; gap: 0.3rem; }
        .view-tabs button {
            background: #16213e; border: 1px solid #0f3460; color: #ccc;
            padding: 0.4rem 1rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem;
        }
        .view-tabs button.active { background: #0f3460; color: white; border-color: #53a8b6; }
```

**Step 2: Add tab buttons to header HTML**

In the header's `.header-controls` div, add a `.view-tabs` div BEFORE the `.period-buttons` div:

```html
            <div class="view-tabs">
                <button data-view="dashboard" class="active" id="tabDashboardBtn"></button>
                <button data-view="log" id="tabLogBtn"></button>
            </div>
```

**Step 3: Wrap existing dashboard content**

Wrap the existing container content (from `<div class="alarm-card"...>` through the closing `</div>` of charts) in a new div:

```html
    <div class="container">
        <div id="viewDashboard">
            <div class="alarm-card" id="alarmCard" style="display:none; margin-bottom: 1.5rem;"></div>
            <div class="cards" id="cards"></div>
            <div class="charts">
                ... (all existing chart boxes stay here unchanged)
            </div>
        </div>
        <div id="viewLog" style="display:none;"></div>
    </div>
```

**Step 4: Add tab switching JavaScript**

Add after the language switch event listeners (after the language switch block):

```javascript
        let currentView = 'dashboard';

        document.querySelectorAll('.view-tabs button').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelector('.view-tabs .active').classList.remove('active');
                btn.classList.add('active');
                currentView = btn.dataset.view;
                document.getElementById('viewDashboard').style.display = currentView === 'dashboard' ? '' : 'none';
                document.getElementById('viewLog').style.display = currentView === 'log' ? '' : 'none';
                if (currentView === 'log') loadEvents();
            });
        });
```

**Step 5: Update updateStaticLabels() to set tab button text**

Add to `updateStaticLabels()`:

```javascript
            document.getElementById('tabDashboardBtn').textContent = t('tabDashboard');
            document.getElementById('tabLogBtn').textContent = t('tabLog');
```

**Step 6: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "feat: add tab navigation (Dashboard/Log) to header"
```

---

### Task 4: Add event log CSS and HTML container

**Files:**
- Modify: `dashboard/templates/index.html` — add log view styles

**Step 1: Add CSS for event log**

Add before `@media` rule:

```css
        .event-log { max-width: 900px; }
        .event-log h3 { font-size: 0.9rem; color: #555; margin-bottom: 1rem; }
        .event-item {
            display: flex; align-items: center; gap: 0.8rem;
            padding: 0.6rem 0.8rem; border-bottom: 1px solid #eee;
            font-size: 0.9rem; border-radius: 6px; margin-bottom: 2px;
        }
        .event-item.severity-critical { background: #ffe0e0; border-left: 4px solid #e74c3c; }
        .event-item.severity-warning { background: #fff8e1; border-left: 4px solid #f39c12; }
        .event-item.severity-info { background: white; border-left: 4px solid #bdc3c7; }
        .event-time { color: #888; font-size: 0.8rem; min-width: 4rem; font-family: monospace; }
        .event-icon { font-size: 1rem; min-width: 1.5rem; text-align: center; }
        .event-source { font-weight: 600; min-width: 8rem; }
        .event-desc { color: #444; }
        .event-empty { text-align: center; color: #999; padding: 3rem; font-size: 0.95rem; }
```

**Step 2: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "feat: add event log CSS styles"
```

---

### Task 5: Add event log JavaScript rendering

**Files:**
- Modify: `dashboard/templates/index.html` — add loadEvents() and event description helper

**Step 1: Add event description helper function**

Add after the `formatTime()` function:

```javascript
        function eventDescription(event) {
            const m = event.event;
            const nv = event.new_value;
            switch (m) {
                case 'window_state':
                    return nv === 'OPEN' ? t('eventWindowOpened') : t('eventWindowClosed');
                case 'motion_detected':
                    return nv === '1' ? t('eventMotionOn') : t('eventMotionOff');
                case 'zone_active':
                    return nv === '1' ? t('eventZoneArmed') : t('eventZoneDisarmed');
                case 'siren_on':
                    return nv === '1' ? t('eventSirenOn') : t('eventSirenOff');
                case 'smoke_alarm':
                    return nv && nv !== 'IDLE_OFF' ? t('eventSmokeAlarm') : t('eventSmokeOff');
                case 'water_detected':
                    return nv === '1' ? t('eventWaterDetected') : t('eventWaterClear');
                case 'moisture_detected':
                    return nv === '1' ? t('eventMoistureOn') : t('eventMoistureOff');
                case 'low_battery':
                    return nv === '1' ? t('eventBatteryLow') : t('eventBatteryOk');
                case 'unreachable':
                    return nv === '1' ? t('eventUnreachable') : t('eventReachable');
                case 'sabotage':
                    return nv === '1' ? t('eventSabotageOn') : t('eventSabotageOff');
                default:
                    return `${m}: ${event.old_value} → ${nv}`;
            }
        }

        function severityIcon(severity) {
            switch (severity) {
                case 'critical': return '\u{1F6A8}';
                case 'warning': return '\u26a0\ufe0f';
                default: return '\u2139\ufe0f';
            }
        }
```

**Step 2: Add loadEvents() function**

Add after `loadAlarmChart()`:

```javascript
        async function loadEvents() {
            const logDiv = document.getElementById('viewLog');
            let resp;
            try {
                resp = await fetch(`/api/events?period=${currentPeriod}`);
            } catch (e) {
                return;
            }
            const events = await resp.json();

            if (!events.length) {
                logDiv.innerHTML = `<div class="event-log"><h3>${t('eventLog')}</h3><div class="event-empty">${t('noEvents')}</div></div>`;
                return;
            }

            let html = `<div class="event-log"><h3>${t('eventLog')}</h3>`;
            for (const ev of events) {
                html += `<div class="event-item severity-${ev.severity}">
                    <span class="event-time">${formatTime(ev.timestamp)}</span>
                    <span class="event-icon">${severityIcon(ev.severity)}</span>
                    <span class="event-source">${ev.source}</span>
                    <span class="event-desc">${eventDescription(ev)}</span>
                </div>`;
            }
            html += `</div>`;
            logDiv.innerHTML = html;
        }
```

**Step 3: Update loadAll() to also load events when log tab is active**

Update `loadAll()`:

```javascript
        async function loadAll() {
            const promises = [
                loadCurrent(),
                loadSecurityCurrent(),
                loadTempChart(),
                loadHumidityChart(),
                loadWindowChart(),
                loadMotionChart(),
                loadAlarmChart(),
            ];
            if (currentView === 'log') {
                promises.push(loadEvents());
            }
            await Promise.all(promises);
        }
```

**Step 4: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "feat: add event log rendering with severity icons and i18n"
```

---

### Task 6: Docker Compose rebuild and test

**Step 1: Rebuild containers**

```bash
docker compose up --build -d
```

**Step 2: Test /api/events endpoint**

```bash
curl -s "http://localhost:8080/api/events?period=24h" | python3 -m json.tool
```

Expected: JSON array of event objects with timestamp, source, event, old_value, new_value, severity.

**Step 3: Verify dashboard UI**

Open `http://localhost:8080` in browser. Verify:
- Tab buttons "Dashboard" and "Log" appear in header
- Dashboard tab shows existing content (alarm card, charts, etc.)
- Clicking "Log" tab switches to event log view
- Event log shows chronological events with color coding
- Period buttons work for both views
- Language switch updates event descriptions

**Step 4: Take screenshot and commit any fixes**

```bash
git add -A
git commit -m "feat: complete event logview feature"
```
