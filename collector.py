#!/usr/bin/env python3
"""
Homematic IP Data Collector
Uses websocket events for real-time updates with periodic full-state fallback.
"""

import asyncio
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

import homematicip
from homematicip.home import Home
from homematicip.device import (
    ShutterContact,
    ShutterContactMagnetic,
    MotionDetectorIndoor,
    MotionDetectorOutdoor,
    MotionDetectorPushButton,
    WallMountedThermostatPro,
    TemperatureHumiditySensorWithoutDisplay,
    TemperatureHumiditySensorDisplay,
    TemperatureHumiditySensorOutdoor,
    WeatherSensor,
    WeatherSensorPlus,
    WeatherSensorPro,
    FullFlushShutter,
    SwitchMeasuring,
    SmokeDetector,
    WaterSensor,
    AlarmSirenIndoor,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

DB_PATH = Path("/app/data/homematic.db")
FULL_STATE_INTERVAL = 3600  # Full state poll every hour (fallback)
MIN_WRITE_INTERVAL = 60  # Min seconds between writes per device/group


class EventCollector:
    """Collects Homematic IP data via websocket events with periodic full-state fallback."""

    def __init__(self):
        self._last_write = {}  # (entity_id, metric) -> timestamp

    def _should_write(self, entity_id, metric):
        """Debounce: only write if MIN_WRITE_INTERVAL has passed for this entity+metric."""
        key = (entity_id, metric)
        now = time.monotonic()
        last = self._last_write.get(key, 0)
        if now - last < MIN_WRITE_INTERVAL:
            return False
        self._last_write[key] = now
        return True

    def store_reading(self, conn, device_id, device_label, device_type, metric, value, value_text=None):
        """Store a single device reading if debounce allows."""
        if not self._should_write(device_id, metric):
            return
        conn.execute(
            """INSERT INTO device_readings
               (timestamp, device_id, device_label, device_type, metric, value, value_text)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), device_id, device_label, device_type, metric, value, value_text),
        )

    def store_security(self, conn, group_id, group_label, group_type, metric, value, value_text=None):
        """Store a single security reading if debounce allows."""
        if not self._should_write(group_id, metric):
            return
        conn.execute(
            """INSERT INTO security_readings
               (timestamp, group_id, group_label, group_type, metric, value, value_text)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(timezone.utc).isoformat(), group_id, group_label, group_type, metric, value, value_text),
        )

    def collect_device_data(self, conn, device):
        """Extract relevant metrics from a Homematic IP device."""
        device_id = device.id
        device_label = device.label
        device_type = type(device).__name__

        if hasattr(device, "unreach") and device.unreach is not None:
            self.store_reading(conn, device_id, device_label, device_type, "unreachable", int(device.unreach))
        if hasattr(device, "lowBat") and device.lowBat is not None:
            self.store_reading(conn, device_id, device_label, device_type, "low_battery", int(device.lowBat))
        if hasattr(device, "rssiDeviceValue") and device.rssiDeviceValue is not None:
            self.store_reading(conn, device_id, device_label, device_type, "rssi", device.rssiDeviceValue)

        if hasattr(device, "windowState") and device.windowState is not None:
            state = str(device.windowState)
            self.store_reading(conn, device_id, device_label, device_type, "window_state", None, state)

        if hasattr(device, "motionDetected") and device.motionDetected is not None:
            self.store_reading(conn, device_id, device_label, device_type, "motion_detected", int(device.motionDetected))
        if hasattr(device, "illumination") and device.illumination is not None:
            self.store_reading(conn, device_id, device_label, device_type, "illumination", device.illumination)

        if hasattr(device, "actualTemperature") and device.actualTemperature is not None:
            self.store_reading(conn, device_id, device_label, device_type, "temperature", device.actualTemperature)
        if hasattr(device, "humidity") and device.humidity is not None:
            self.store_reading(conn, device_id, device_label, device_type, "humidity", device.humidity)

        if hasattr(device, "setPointTemperature") and device.setPointTemperature is not None:
            self.store_reading(conn, device_id, device_label, device_type, "setpoint_temperature", device.setPointTemperature)
        if hasattr(device, "valvePosition") and device.valvePosition is not None:
            self.store_reading(conn, device_id, device_label, device_type, "valve_position", device.valvePosition)

        if hasattr(device, "windSpeed") and device.windSpeed is not None:
            self.store_reading(conn, device_id, device_label, device_type, "wind_speed", device.windSpeed)
        if hasattr(device, "sunshine") and device.sunshine is not None:
            self.store_reading(conn, device_id, device_label, device_type, "sunshine", int(device.sunshine))

        if hasattr(device, "currentPowerConsumption") and device.currentPowerConsumption is not None:
            self.store_reading(conn, device_id, device_label, device_type, "power_consumption", device.currentPowerConsumption)
        if hasattr(device, "energyCounter") and device.energyCounter is not None:
            self.store_reading(conn, device_id, device_label, device_type, "energy_counter", device.energyCounter)

        if hasattr(device, "smokeDetectorAlarmType") and device.smokeDetectorAlarmType is not None:
            self.store_reading(conn, device_id, device_label, device_type, "smoke_alarm", None, str(device.smokeDetectorAlarmType))

        if hasattr(device, "waterlevelDetected") and device.waterlevelDetected is not None:
            self.store_reading(conn, device_id, device_label, device_type, "water_detected", int(device.waterlevelDetected))
        if hasattr(device, "moistureDetected") and device.moistureDetected is not None:
            self.store_reading(conn, device_id, device_label, device_type, "moisture_detected", int(device.moistureDetected))

    def collect_security_data(self, conn, home):
        """Collect security group states from home.groups."""
        count = 0
        for group in home.groups:
            group_id = group.id
            group_label = group.label
            group_type_name = type(group).__name__

            if group_type_name == 'SecurityZoneGroup':
                if group.active is not None:
                    self.store_security(conn, group_id, group_label, 'zone',
                                        'zone_active', int(group.active))
                count += 1

            elif group_type_name == 'AlarmSwitchingGroup':
                if group.on is not None:
                    self.store_security(conn, group_id, group_label, 'alarm',
                                        'siren_on', int(group.on))
                count += 1

            elif group_type_name == 'SecurityGroup':
                if hasattr(group, 'windowState') and group.windowState is not None:
                    self.store_security(conn, group_id, group_label, 'room_security',
                                        'window_state', None, str(group.windowState))
                if hasattr(group, 'motionDetected') and group.motionDetected is not None:
                    self.store_security(conn, group_id, group_label, 'room_security',
                                        'motion_detected', int(group.motionDetected))
                if hasattr(group, 'sabotage') and group.sabotage is not None:
                    self.store_security(conn, group_id, group_label, 'room_security',
                                        'sabotage', int(group.sabotage))
                count += 1

        log.info("Collected security data from %d groups", count)

    def collect_full_state(self, home):
        """Full state collection for all devices and security groups (bypasses debounce)."""
        self._last_write.clear()  # Reset debounce for full state
        conn = sqlite3.connect(str(DB_PATH))
        count = 0

        for device in home.devices:
            try:
                self.collect_device_data(conn, device)
                count += 1
            except Exception as e:
                log.warning("Error reading device %s (%s): %s", device.label, device.id, e)

        try:
            self.collect_security_data(conn, home)
        except Exception as e:
            log.warning("Error collecting security data: %s", e)

        conn.commit()
        conn.close()
        log.info("Full state: collected data from %d devices", count)

    def on_device_changed(self, json_data, event_type=None, obj=None):
        """Callback for device state changes via websocket."""
        if obj is None:
            return
        try:
            conn = sqlite3.connect(str(DB_PATH))
            self.collect_device_data(conn, obj)
            conn.commit()
            conn.close()
            log.debug("Event: device %s (%s) updated", obj.label, obj.id)
        except Exception as e:
            log.warning("Error processing device event for %s: %s", getattr(obj, 'label', '?'), e)

    def on_group_changed(self, json_data, event_type=None, obj=None):
        """Callback for group state changes via websocket."""
        if obj is None:
            return
        group_type_name = type(obj).__name__
        if group_type_name not in ('SecurityZoneGroup', 'AlarmSwitchingGroup', 'SecurityGroup'):
            return
        try:
            conn = sqlite3.connect(str(DB_PATH))
            group_id = obj.id
            group_label = obj.label

            if group_type_name == 'SecurityZoneGroup' and obj.active is not None:
                self.store_security(conn, group_id, group_label, 'zone', 'zone_active', int(obj.active))
            elif group_type_name == 'AlarmSwitchingGroup' and obj.on is not None:
                self.store_security(conn, group_id, group_label, 'alarm', 'siren_on', int(obj.on))
            elif group_type_name == 'SecurityGroup':
                if hasattr(obj, 'windowState') and obj.windowState is not None:
                    self.store_security(conn, group_id, group_label, 'room_security',
                                        'window_state', None, str(obj.windowState))
                if hasattr(obj, 'motionDetected') and obj.motionDetected is not None:
                    self.store_security(conn, group_id, group_label, 'room_security',
                                        'motion_detected', int(obj.motionDetected))
                if hasattr(obj, 'sabotage') and obj.sabotage is not None:
                    self.store_security(conn, group_id, group_label, 'room_security',
                                        'sabotage', int(obj.sabotage))

            conn.commit()
            conn.close()
            log.debug("Event: group %s (%s) updated", group_label, group_id)
        except Exception as e:
            log.warning("Error processing group event for %s: %s", getattr(obj, 'label', '?'), e)


def init_db():
    """Create the SQLite database and tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS device_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            device_id TEXT NOT NULL,
            device_label TEXT,
            device_type TEXT,
            metric TEXT NOT NULL,
            value REAL,
            value_text TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_time
        ON device_readings(timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_device
        ON device_readings(device_id, metric)
    """)
    # Covering-Index für /api/current ("neuester Wert je device_id+metric").
    # Ohne timestamp im Index muss MAX(timestamp) GROUP BY device_id, metric die
    # ganze Tabelle scannen (bei ~600k Zeilen 6-7 s → ESP-HTTP-Timeout). Mit
    # (device_id, metric, timestamp) wird daraus ein Skip-Scan auf die letzten
    # Einträge pro Gruppe (~ms).
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_readings_latest
        ON device_readings(device_id, metric, timestamp)
    """)
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
    conn.commit()
    conn.close()
    log.info("Database initialized at %s", DB_PATH)


BACKUP_DIR = DB_PATH.parent / "backup"


def backup_to_parquet():
    """Export last 24h of readings to daily Parquet files."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    conn = sqlite3.connect(str(DB_PATH))
    tables = ["device_readings", "security_readings"]

    for table in tables:
        df = pd.read_sql_query(
            f"SELECT * FROM {table} WHERE timestamp >= ?",  # noqa: S608
            conn,
            params=(cutoff,),
            parse_dates=["timestamp"],
        )
        if df.empty:
            log.info("Backup: no data in %s for last 24h, skipping", table)
            continue

        path = BACKUP_DIR / f"{table}_{today}.parquet"
        df.to_parquet(path, index=False)
        log.info("Backup: wrote %d rows to %s", len(df), path)

    conn.close()


async def main():
    log.info("Starting Homematic IP Data Collector (event-driven)")

    config = homematicip.find_and_load_config_file()
    if config is None:
        log.error("No config.ini found! Run 'hmip_generate_auth_token' first.")
        return

    init_db()

    home = Home()
    await home.init_async(config.access_point, auth_token=config.auth_token)
    log.info("Connected to Access Point: %s", config.access_point)

    # Initial full state fetch
    await home.get_current_state_async()

    collector = EventCollector()
    collector.collect_full_state(home)

    # Register event callbacks on all existing devices and groups
    for device in home.devices:
        device.on_update(collector.on_device_changed)
    for group in home.groups:
        group.on_update(collector.on_group_changed)

    # Register callback for newly added devices/groups
    def on_create(data, event_type=None, obj=None):
        if obj is None:
            return
        if hasattr(obj, 'actualTemperature') or hasattr(obj, 'windowState') or hasattr(obj, 'lowBat'):
            obj.on_update(collector.on_device_changed)
            log.info("Registered event handler for new device: %s", getattr(obj, 'label', obj.id))
        elif type(obj).__name__ in ('SecurityZoneGroup', 'AlarmSwitchingGroup', 'SecurityGroup'):
            obj.on_update(collector.on_group_changed)
            log.info("Registered event handler for new group: %s", getattr(obj, 'label', obj.id))

    home.on_create(on_create)

    # Start websocket event listener
    await home.enable_events()
    log.info("Websocket events enabled — listening for changes")

    home.set_on_connected_handler(lambda: log.info("Websocket connected"))
    home.set_on_disconnected_handler(lambda: log.warning("Websocket disconnected — will auto-reconnect"))

    last_backup_date = None
    last_full_state = time.monotonic()

    while True:
        await asyncio.sleep(60)

        # Periodic full-state fallback (hourly)
        if time.monotonic() - last_full_state >= FULL_STATE_INTERVAL:
            try:
                log.info("Hourly full state refresh...")
                await home.get_current_state_async()
                collector.collect_full_state(home)
                last_full_state = time.monotonic()
            except Exception as e:
                log.error("Full state poll error: %s", e)

        # Daily Parquet backup
        today_utc = datetime.now(timezone.utc).date()
        if last_backup_date != today_utc:
            try:
                backup_to_parquet()
                last_backup_date = today_utc
            except Exception as e:
                log.error("Backup error: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
