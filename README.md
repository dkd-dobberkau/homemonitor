# Homematic IP Data Collector POC

Sammelt Sensordaten vom Homematic IP Access Point über die Cloud API
und speichert sie in einer SQLite-Datenbank.

## Setup

### 1. Auth-Token generieren

Zuerst brauchst du einen Auth-Token für deinen Access Point.
Installiere die homematicip-Bibliothek temporär:

```bash
# Mit uv (empfohlen)
uvx hmip_generate_auth_token

# Oder mit pip
pip install homematicip
hmip_generate_auth_token
```

Das Skript fragt nach:
- **SGTIN**: Steht auf der Rückseite deines Access Points (z.B. 3014-xxxx-xxxx-xxxx-xxxx-xxxx)
- **PIN**: Falls in der App gesetzt, sonst leer lassen

Dann die **blaue Taste** am Access Point drücken.

Es wird eine `config.ini` im aktuellen Verzeichnis erstellt.

### 2. config.ini in dieses Verzeichnis kopieren

```bash
cp /pfad/zur/config.ini ./config.ini
```

### 3. Docker Container starten

```bash
docker compose up -d
```

### 4. Logs prüfen

```bash
docker compose logs -f
```

### 5. Daten abfragen

Die SQLite-Datenbank liegt unter `./data/homematic.db`:

```bash
# Alle Geräte anzeigen
sqlite3 data/homematic.db "SELECT DISTINCT device_label, device_type FROM device_readings;"

# Letzte Temperaturwerte
sqlite3 data/homematic.db "SELECT timestamp, device_label, value FROM device_readings WHERE metric='temperature' ORDER BY timestamp DESC LIMIT 20;"

# Fensterstatus
sqlite3 data/homematic.db "SELECT timestamp, device_label, value_text FROM device_readings WHERE metric='window_state' ORDER BY timestamp DESC LIMIT 20;"

# Bewegungsmeldungen
sqlite3 data/homematic.db "SELECT timestamp, device_label, value FROM device_readings WHERE metric='motion_detected' AND value=1 ORDER BY timestamp DESC LIMIT 20;"
```

## Konfiguration

- **Poll-Intervall**: Standard 5 Minuten (300 Sekunden), anpassbar in `collector.py` über `POLL_INTERVAL`
- **Datenbank**: `./data/homematic.db` (SQLite)

## Unterstützte Metriken

| Metrik | Beschreibung | Gerätetyp |
|--------|-------------|-----------|
| temperature | Temperatur in °C | Thermostate, Sensoren |
| humidity | Luftfeuchtigkeit in % | Sensoren |
| window_state | Fenster/Tür offen/geschlossen | Fensterkontakte |
| motion_detected | Bewegung erkannt | Bewegungsmelder |
| illumination | Helligkeit in Lux | Bewegungsmelder |
| power_consumption | Stromverbrauch in W | Schaltaktoren |
| energy_counter | Energiezähler in Wh | Schaltaktoren |
| smoke_alarm | Rauchalarm | Rauchmelder |
| water_detected | Wasser erkannt | Wassersensor |
| low_battery | Batterie schwach | Alle batteriebetriebenen |
| rssi | Signalstärke | Alle Geräte |
