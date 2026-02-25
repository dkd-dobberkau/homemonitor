# System-Status Card Layout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ersetze das fehlerhafte System-Status Grid durch ein Karten-Grid, bei dem Gerätename und dBm-Wert immer in derselben Karte sitzen.

**Architecture:** Reine CSS+HTML-Änderung in `index.html`. Bestehende Klassen `.system-grid` und `.system-item` werden durch `.system-card-grid` und `.system-card` ersetzt. Das JS-Template wird entsprechend angepasst. Keine Backend-Änderungen nötig.

**Tech Stack:** HTML, CSS Grid, Vanilla JS (kein Framework)

---

### Task 1: CSS ersetzen

**Files:**
- Modify: `dashboard/templates/index.html:58-60`

**Step 1: Alte CSS-Regeln entfernen und neue einfügen**

Ersetze in `index.html` (Zeilen 58–60):

```css
.system-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.8rem; margin-top: 0.5rem; }
.system-item { display: flex; justify-content: space-between; padding: 0.4rem 0; border-bottom: 1px solid #eee; font-size: 0.85rem; }
.system-item .label { color: #666; }
```

durch:

```css
.system-card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 0.8rem; margin-top: 0.5rem; }
.system-card { background: white; border-radius: 8px; padding: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08); display: flex; flex-direction: column; gap: 0.3rem; }
.system-card .card-name { font-size: 0.8rem; color: #666; line-height: 1.3; }
.system-card .card-value { font-size: 1.4rem; font-weight: bold; }
.system-card .card-label { font-size: 0.75rem; }
.system-card .card-battery { font-size: 0.75rem; margin-top: 0.2rem; }
```

**Step 2: Visuell prüfen** — kein automatischer Test möglich für CSS. Fahre direkt mit Step 3 fort.

**Step 3: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "style: replace system-status grid CSS with card layout"
```

---

### Task 2: HTML-Container anpassen

**Files:**
- Modify: `dashboard/templates/index.html:172`

**Step 1: Klasse am Container ändern**

Zeile 172 — ändere `class="system-grid"` zu `class="system-card-grid"`:

```html
<div class="system-card-grid" id="systemStatus"></div>
```

**Step 2: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "style: update system-status container class to card grid"
```

---

### Task 3: JS-Template anpassen

**Files:**
- Modify: `dashboard/templates/index.html:513-530`

**Step 1: Altes Template**

```js
if (rssi !== undefined) {
    sysHtml += `<div class="system-item">
        <span class="label">${name}</span>
        <span class="${rssiClass(rssi)}">${rssi} dBm (${rssiLabel(rssi)})</span>
    </div>`;
}
if (battery === 1) {
    sysHtml += `<div class="system-item">
        <span class="label">${name}</span>
        <span class="rssi-bad">${t('batteryLow')}</span>
    </div>`;
}
```

**Step 2: Neues Template einfügen**

Ersetze den gesamten Block (Zeilen 517–528) durch:

```js
if (rssi !== undefined) {
    const batteryBadge = battery === 1
        ? `<span class="card-battery rssi-bad">${t('batteryLow')}</span>`
        : '';
    sysHtml += `<div class="system-card">
        <span class="card-name">${name}</span>
        <span class="card-value ${rssiClass(rssi)}">${rssi} dBm</span>
        <span class="card-label ${rssiClass(rssi)}">${rssiLabel(rssi)}</span>
        ${batteryBadge}
    </div>`;
}
```

Hinweis: Geräte mit Batterieproblem aber ohne RSSI-Wert fallen weg — das ist bewusst, da der Collector immer RSSI mitliefert wenn ein Gerät erreichbar ist. Falls das sich ändert, kann ein separater `else if`-Block ergänzt werden.

**Step 3: Im Browser prüfen**

Dashboard öffnen unter `http://localhost:8080`. System-Status-Bereich sollte Karten anzeigen mit:
- Gerätename oben (grau, klein)
- dBm-Wert groß in der passenden Farbe
- Label (Gut/OK/Schwach) darunter
- Optional: rotes "Batterie schwach!" Badge

**Step 4: Commit**

```bash
git add dashboard/templates/index.html
git commit -m "feat: render system-status as card grid with name, value, label"
```
