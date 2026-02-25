# Alarm/Security Status Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Collect alarm and security group data from homematicip and display it in the dashboard with live status cards and historical charts.

**Architecture:** New `security_readings` SQLite table for group-level data (zones, alarms, room security). Collector polls `home.groups` alongside devices. Dashboard gets two new API endpoints and a prominent alarm card + history chart.

**Tech Stack:** Python 3.12, homematicip 2.6.0, SQLite, Flask, Chart.js

**Design doc:** `docs/plans/2026-02-25-alarm-security-status-design.md`

---

### Task 1: Add security_readings table to collector

**Files:**
- Modify: `collector.py:47-73` (init_db function)

**Step 1: Add the security_readings table creation to init_db()**

In `collector.py`, add after the existing `idx_readings_device` index creation (line 70), before `conn.commit()`:

```python
    conn.execute("""
        CREATE TABLE IF NOT EXISTS security_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            group_id TEXT NOT NULL,
            group_label TEXT,
            group_type TEXT,
            metric TEXT NOT NULL,
            value INTEGER,
            value_text TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_security_time
        ON security_readings(timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_security_group
        ON security_readings(group_id, metric)
    """)
```

**Step 2: Verify collector still starts**

Run: `python collector.py` (will fail at API connect, but should print "Database initialized" first)
Expected: Log line "Database initialized at /app/data/homematic.db" (or local path if testing outside Docker)

**Step 3: Commit**

```bash
git add collector.py
git commit -m "feat: add security_readings table to collector init_db"
```

---

### Task 2: Add store_security() and collect_security_data() to collector

**Files:**
- Modify: `collector.py` — add two new functions after `collect_device_data()`

**Step 1: Add store_security() function**

Add after `store_reading()` (line 83):

```python
def store_security(conn, group_id, group_label, group_type, metric, value, value_text=None):
    """Store a single security group reading in the database."""
    conn.execute(
        """INSERT INTO security_readings
           (timestamp, group_id, group_label, group_type, metric, value, value_text)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now(timezone.utc).isoformat(), group_id, group_label, group_type, metric, value, value_text),
    )
```

**Step 2: Add collect_security_data() function**

Add after `collect_device_data()` (after line 143):

```python
def collect_security_data(conn, home):
    """Collect security group states from home.groups."""
    count = 0
    for group in home.groups:
        group_id = group.id
        group_label = group.label
        group_type_name = type(group).__name__

        if group_type_name == 'SecurityZoneGroup':
            store_security(conn, group_id, group_label, 'zone',
                          'zone_active', int(group.active))
            count += 1

        elif group_type_name == 'AlarmSwitchingGroup':
            store_security(conn, group_id, group_label, 'alarm',
                          'siren_on', int(group.on))
            count += 1

        elif group_type_name == 'SecurityGroup':
            if hasattr(group, 'windowState') and group.windowState is not None:
                store_security(conn, group_id, group_label, 'room_security',
                              'window_state', None, str(group.windowState))
            if hasattr(group, 'motionDetected') and group.motionDetected is not None:
                store_security(conn, group_id, group_label, 'room_security',
                              'motion_detected', int(group.motionDetected))
            if hasattr(group, 'sabotage') and group.sabotage is not None:
                store_security(conn, group_id, group_label, 'room_security',
                              'sabotage', int(group.sabotage))
            count += 1

    log.info("Collected security data from %d groups", count)
```

**Step 3: Commit**

```bash
git add collector.py
git commit -m "feat: add store_security and collect_security_data functions"
```

---

### Task 3: Wire collect_security_data into poll_once()

**Files:**
- Modify: `collector.py:146-162` (poll_once function)

**Step 1: Add collect_security_data() call to poll_once()**

In `poll_once()`, add after the device collection loop (after line 161, before `conn.commit()`):

```python
    try:
        collect_security_data(conn, home)
    except Exception as e:
        log.warning("Error collecting security data: %s", e)
```

**Step 2: Commit**

```bash
git add collector.py
git commit -m "feat: wire security data collection into poll_once"
```

---

### Task 4: Add /api/security/current endpoint to dashboard

**Files:**
- Modify: `dashboard/app.py` — add new route after `api_current()`

**Step 1: Add the endpoint**

Add after the `api_current()` function (after line 57):

```python
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
```

**Step 2: Test manually**

Run dashboard locally and hit `http://localhost:8080/api/security/current`.
Expected: `{"zones": {}, "alarms": {}, "rooms": {}}` (empty until collector runs)

**Step 3: Commit**

```bash
git add dashboard/app.py
git commit -m "feat: add /api/security/current endpoint"
```

---

### Task 5: Add /api/security/readings endpoint to dashboard

**Files:**
- Modify: `dashboard/app.py` — add new route after `api_security_current()`

**Step 1: Add the endpoint**

```python
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
```

**Step 2: Commit**

```bash
git add dashboard/app.py
git commit -m "feat: add /api/security/readings endpoint"
```

---

### Task 6: Add I18N keys for alarm/security to dashboard

**Files:**
- Modify: `dashboard/templates/index.html` — extend the `I18N` object

**Step 1: Add German keys**

Add to the `de` object in `I18N` (after `motionAxis` line):

```javascript
                alarmStatus: 'Alarm-Status',
                armed: 'Scharf',
                disarmed: 'Unscharf',
                internalZone: 'Intern',
                externalZone: 'Extern',
                siren: 'Sirene',
                sabotageWarning: 'Sabotage!',
                alarmHistory: 'Alarm-Verlauf',
                roomSecurity: 'Raum-Sicherheit',
                noAlarmData: 'Keine Alarm-Daten',
                sirenActive: 'Sirene aktiv!',
```

**Step 2: Add English keys**

Add to the `en` object in `I18N`:

```javascript
                alarmStatus: 'Alarm Status',
                armed: 'Armed',
                disarmed: 'Disarmed',
                internalZone: 'Internal',
                externalZone: 'External',
                siren: 'Siren',
                sabotageWarning: 'Sabotage!',
                alarmHistory: 'Alarm History',
                roomSecurity: 'Room Security',
                noAlarmData: 'No alarm data',
                sirenActive: 'Siren active!',
```

**Step 3: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "feat: add alarm/security i18n keys (DE/EN)"
```

---

### Task 7: Add alarm status card to dashboard HTML

**Files:**
- Modify: `dashboard/templates/index.html` — add CSS and HTML

**Step 1: Add CSS styles**

Add before `@media` rule (before line 65):

```css
        .alarm-card {
            background: white; border-radius: 10px; padding: 1.2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            grid-column: 1 / -1;
            border-left: 5px solid #27ae60;
        }
        .alarm-card.armed-partial { border-left-color: #f39c12; background: #fffdf0; }
        .alarm-card.armed-full { border-left-color: #e74c3c; background: #fff5f5; }
        .alarm-card.siren-active { border-left-color: #e74c3c; background: #ffe0e0; animation: pulse 1s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.85; } }
        .alarm-card h3 { font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.8rem; }
        .alarm-zones { display: flex; gap: 2rem; margin-bottom: 0.8rem; }
        .alarm-zone { font-size: 1.1rem; }
        .alarm-zone .label { color: #666; margin-right: 0.5rem; }
        .alarm-zone .armed { color: #e74c3c; font-weight: 700; }
        .alarm-zone .disarmed { color: #27ae60; font-weight: 700; }
        .alarm-rooms { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; }
        .alarm-rooms .status-row { font-size: 0.85rem; }
        .siren-warning { color: #e74c3c; font-weight: 700; font-size: 1rem; margin-bottom: 0.5rem; }
        .sabotage-warning { color: #e74c3c; font-weight: 700; font-size: 0.9rem; }
```

**Step 2: Add alarm card HTML placeholder**

In the container div, add before `<div class="cards" id="cards">` (before line 90):

```html
        <div class="alarm-card" id="alarmCard" style="display:none; margin-bottom: 1.5rem;"></div>
```

**Step 3: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "feat: add alarm card HTML structure and CSS"
```

---

### Task 8: Add alarm card JavaScript rendering

**Files:**
- Modify: `dashboard/templates/index.html` — add loadSecurityCurrent() function

**Step 1: Add loadSecurityCurrent() function**

Add after the `loadCurrent()` function:

```javascript
        async function loadSecurityCurrent() {
            let resp;
            try {
                resp = await fetch('/api/security/current');
            } catch (e) {
                return; // API not available yet
            }
            const data = await resp.json();
            const card = document.getElementById('alarmCard');

            const hasData = Object.keys(data.zones).length > 0 || Object.keys(data.alarms).length > 0;
            if (!hasData) {
                card.style.display = 'none';
                return;
            }
            card.style.display = 'block';

            // Determine alarm state
            const zones = data.zones;
            const alarms = data.alarms;
            const rooms = data.rooms;

            const internalActive = zones['INTERNAL']?.active || false;
            const externalActive = zones['EXTERNAL']?.active || false;
            const anySiren = Object.values(alarms).some(a => a.on);

            // Card styling
            card.className = 'alarm-card';
            if (anySiren) card.classList.add('siren-active');
            else if (internalActive && externalActive) card.classList.add('armed-full');
            else if (internalActive || externalActive) card.classList.add('armed-partial');

            let html = `<h3>${t('alarmStatus')}</h3>`;

            // Siren warning
            if (anySiren) {
                html += `<div class="siren-warning">${t('sirenActive')}</div>`;
            }

            // Zone status
            html += `<div class="alarm-zones">`;
            html += `<div class="alarm-zone"><span class="label">${t('internalZone')}:</span><span class="${internalActive ? 'armed' : 'disarmed'}">${internalActive ? t('armed') : t('disarmed')}</span></div>`;
            html += `<div class="alarm-zone"><span class="label">${t('externalZone')}:</span><span class="${externalActive ? 'armed' : 'disarmed'}">${externalActive ? t('armed') : t('disarmed')}</span></div>`;
            html += `</div>`;

            // Room security
            if (Object.keys(rooms).length > 0) {
                html += `<div class="alarm-rooms">`;
                for (const [room, info] of Object.entries(rooms)) {
                    const hasSabotage = info.sabotage === 1;
                    if (hasSabotage) {
                        html += `<div class="status-row"><span class="status-dot open"></span>${room}: <span class="sabotage-warning">${t('sabotageWarning')}</span></div>`;
                    } else {
                        const winState = info.window_state || 'CLOSED';
                        const cls = winState === 'CLOSED' ? 'closed' : 'open';
                        const label = winState === 'CLOSED' ? t('closed') : t('open');
                        html += `<div class="status-row"><span class="status-dot ${cls}"></span>${room}: ${label}</div>`;
                    }
                }
                html += `</div>`;
            }

            card.innerHTML = html;
        }
```

**Step 2: Add loadSecurityCurrent() to loadAll()**

In the `loadAll()` function, add `loadSecurityCurrent()` to the Promise.all array:

```javascript
        async function loadAll() {
            await Promise.all([
                loadCurrent(),
                loadSecurityCurrent(),
                loadTempChart(),
                loadHumidityChart(),
                loadWindowChart(),
                loadMotionChart(),
            ]);
        }
```

**Step 3: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "feat: add alarm status card rendering with live data"
```

---

### Task 9: Add alarm history chart

**Files:**
- Modify: `dashboard/templates/index.html` — add chart HTML and JS

**Step 1: Add chart HTML**

Add after the motion chart-box div (after line 108, before the system-status chart-box):

```html
            <div class="chart-box">
                <h3 id="chartAlarmTitle"></h3>
                <canvas id="chartAlarm"></canvas>
            </div>
```

**Step 2: Update updateStaticLabels()**

Add to `updateStaticLabels()`:

```javascript
            document.getElementById('chartAlarmTitle').textContent = t('alarmHistory');
```

**Step 3: Add loadAlarmChart() function**

Add after `loadMotionChart()`:

```javascript
        async function loadAlarmChart() {
            let resp;
            try {
                resp = await fetch(`/api/security/readings?metric=zone_active&period=${currentPeriod}`);
            } catch (e) {
                return;
            }
            const data = await resp.json();
            if (!data.length) return;

            const grouped = {};
            for (const row of data) {
                const key = row.group_label;
                if (!grouped[key]) grouped[key] = [];
                grouped[key].push(row);
            }

            const datasets = [];
            const zoneColors = { 'INTERNAL': '#e74c3c', 'EXTERNAL': '#3498db' };
            const zoneLabels = { 'INTERNAL': t('internalZone'), 'EXTERNAL': t('externalZone') };

            for (const [label, rows] of Object.entries(grouped)) {
                datasets.push({
                    label: zoneLabels[label] || label,
                    data: rows.map(r => ({ x: new Date(r.timestamp), y: r.value })),
                    borderColor: zoneColors[label] || '#95a5a6',
                    backgroundColor: 'transparent',
                    stepped: true,
                });
            }

            const ctx = document.getElementById('chartAlarm').getContext('2d');
            if (charts['chartAlarm']) charts['chartAlarm'].destroy();
            charts['chartAlarm'] = new Chart(ctx, {
                type: 'line',
                data: { datasets },
                options: {
                    responsive: true,
                    scales: {
                        x: timeScale(),
                        y: {
                            min: -0.1, max: 1.1,
                            ticks: { callback: v => v === 1 ? t('armed') : v === 0 ? t('disarmed') : '' }
                        }
                    },
                    plugins: { legend: { position: 'top' } },
                    elements: { point: { radius: 0 }, line: { borderWidth: 2 } }
                }
            });
        }
```

**Step 4: Add loadAlarmChart() to loadAll()**

```javascript
        async function loadAll() {
            await Promise.all([
                loadCurrent(),
                loadSecurityCurrent(),
                loadTempChart(),
                loadHumidityChart(),
                loadWindowChart(),
                loadMotionChart(),
                loadAlarmChart(),
            ]);
        }
```

**Step 5: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "feat: add alarm history stepped-line chart"
```

---

### Task 10: Rebuild and test with Docker Compose

**Step 1: Rebuild containers**

```bash
docker compose up --build -d
```

**Step 2: Wait for first poll cycle (up to 5 minutes) and verify**

Check collector logs:
```bash
docker compose logs -f collector
```
Expected: "Collected security data from N groups" in log output

**Step 3: Test dashboard endpoints**

```bash
curl http://localhost:8080/api/security/current
curl "http://localhost:8080/api/security/readings?metric=zone_active&period=1h"
```
Expected: JSON with zones/alarms/rooms data after first poll

**Step 4: Verify dashboard UI**

Open `http://localhost:8080` in browser. Verify:
- Alarm status card appears at top with zone status
- Alarm history chart shows after motion chart
- Color coding works (green/yellow/red border)
- Language switch updates alarm labels

**Step 5: Commit any fixes, then final commit**

```bash
git add -A
git commit -m "feat: complete alarm/security status feature (Task #10)"
```
