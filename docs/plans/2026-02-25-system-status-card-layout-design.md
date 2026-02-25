# Design: System-Status Karten-Grid Layout

**Datum:** 2026-02-25
**Status:** Genehmigt

## Problem

Der aktuelle System-Status Bereich nutzt ein `auto-fit` CSS-Grid mit `flex`-Rows pro Gerät. Bei langen Gerätenamen (z.B. "Temperatur- und Luftfeuchtigkeitssensor - außen") bricht der Name um und der dBm-Wert erscheint abgekoppelt in einer anderen Spalte. Außerdem ist der Bereich zu eng und das Raster unübersichtlich.

## Lösung: Option A — Karten-Grid

Jedes Gerät erhält eine eigene Karte. Name und Wert sind immer in derselben Box.

### Kartenstruktur

```
┌─────────────────────────────┐
│  Balkon 1                   │
│                             │
│       -54 dBm               │
│         Gut                 │
└─────────────────────────────┘
```

### CSS-Spezifikation

- **Grid:** `repeat(auto-fill, minmax(160px, 1fr))`
- **Karte:** weißer Hintergrund, leichter Box-Shadow, `border-radius: 8px`, `padding: 1rem`
- **Gerätename:** oben, `font-size: 0.8rem`, `color: #666`, Zeilenumbruch erlaubt
- **dBm-Wert:** mittig, `font-size: 1.4rem`, `font-weight: bold`, farbkodiert (grün/orange/rot)
- **Label** (Gut/OK/Schwach): darunter, `font-size: 0.75rem`, gleiche Farbe wie Wert
- **Batteriewarnung:** Badge unten rechts in der Karte (`rssi-bad` Farbe)

### Farbkodierung (unverändert)

- `rssi-good` (#27ae60): ≥ -60 dBm
- `rssi-ok` (#f39c12): -60 bis -75 dBm
- `rssi-bad` (#e74c3c): < -75 dBm

## Betroffene Dateien

- `dashboard/templates/index.html`
  - CSS: `.system-grid`, `.system-item` ersetzen durch `.system-card-grid`, `.system-card`
  - JS: `sysHtml` Template anpassen
