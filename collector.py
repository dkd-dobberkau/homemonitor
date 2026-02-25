#!/usr/bin/env python3
"""
Homematic IP Data Collector POC
Polls the Homematic IP Cloud API every 5 minutes and stores sensor data in SQLite.
"""

import asyncio
import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

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
POLL_INTERVAL = 300  # 5 minutes


def init_db():
    """Create the SQLite database and tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
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


def store_reading(conn, device_id, device_label, device_type, metric, value, value_text=None):
    """Store a single reading in the database."""
    conn.execute(
        """INSERT INTO device_readings
           (timestamp, device_id, device_label, device_type, metric, value, value_text)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now(timezone.utc).isoformat(), device_id, device_label, device_type, metric, value, value_text),
    )


def store_security(conn, group_id, group_label, group_type, metric, value, value_text=None):
    """Store a single security group reading in the database."""
    conn.execute(
        """INSERT INTO security_readings
           (timestamp, group_id, group_label, group_type, metric, value, value_text)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (datetime.now(timezone.utc).isoformat(), group_id, group_label, group_type, metric, value, value_text),
    )


def collect_device_data(conn, device):
    """Extract relevant metrics from a Homematic IP device."""
    device_id = device.id
    device_label = device.label
    device_type = type(device).__name__

    # Common: reachability and low battery
    if hasattr(device, "unreach") and device.unreach is not None:
        store_reading(conn, device_id, device_label, device_type, "unreachable", int(device.unreach))
    if hasattr(device, "lowBat") and device.lowBat is not None:
        store_reading(conn, device_id, device_label, device_type, "low_battery", int(device.lowBat))
    if hasattr(device, "rssiDeviceValue") and device.rssiDeviceValue is not None:
        store_reading(conn, device_id, device_label, device_type, "rssi", device.rssiDeviceValue)

    # Window/door contacts
    if hasattr(device, "windowState") and device.windowState is not None:
        state = str(device.windowState)
        store_reading(conn, device_id, device_label, device_type, "window_state", None, state)

    # Motion detectors
    if hasattr(device, "motionDetected") and device.motionDetected is not None:
        store_reading(conn, device_id, device_label, device_type, "motion_detected", int(device.motionDetected))
    if hasattr(device, "illumination") and device.illumination is not None:
        store_reading(conn, device_id, device_label, device_type, "illumination", device.illumination)

    # Temperature and humidity
    if hasattr(device, "actualTemperature") and device.actualTemperature is not None:
        store_reading(conn, device_id, device_label, device_type, "temperature", device.actualTemperature)
    if hasattr(device, "humidity") and device.humidity is not None:
        store_reading(conn, device_id, device_label, device_type, "humidity", device.humidity)

    # Thermostat set point
    if hasattr(device, "setPointTemperature") and device.setPointTemperature is not None:
        store_reading(conn, device_id, device_label, device_type, "setpoint_temperature", device.setPointTemperature)
    if hasattr(device, "valvePosition") and device.valvePosition is not None:
        store_reading(conn, device_id, device_label, device_type, "valve_position", device.valvePosition)

    # Weather sensors
    if hasattr(device, "windSpeed") and device.windSpeed is not None:
        store_reading(conn, device_id, device_label, device_type, "wind_speed", device.windSpeed)
    if hasattr(device, "sunshine") and device.sunshine is not None:
        store_reading(conn, device_id, device_label, device_type, "sunshine", int(device.sunshine))

    # Power measurement (plugs/switches)
    if hasattr(device, "currentPowerConsumption") and device.currentPowerConsumption is not None:
        store_reading(conn, device_id, device_label, device_type, "power_consumption", device.currentPowerConsumption)
    if hasattr(device, "energyCounter") and device.energyCounter is not None:
        store_reading(conn, device_id, device_label, device_type, "energy_counter", device.energyCounter)

    # Smoke detector
    if hasattr(device, "smokeDetectorAlarmType") and device.smokeDetectorAlarmType is not None:
        store_reading(conn, device_id, device_label, device_type, "smoke_alarm", None, str(device.smokeDetectorAlarmType))

    # Water sensor
    if hasattr(device, "waterlevelDetected") and device.waterlevelDetected is not None:
        store_reading(conn, device_id, device_label, device_type, "water_detected", int(device.waterlevelDetected))
    if hasattr(device, "moistureDetected") and device.moistureDetected is not None:
        store_reading(conn, device_id, device_label, device_type, "moisture_detected", int(device.moistureDetected))


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


async def poll_once(home):
    """Fetch current state from the cloud and store all device data."""
    await home.get_current_state_async()

    conn = sqlite3.connect(str(DB_PATH))
    count = 0

    for device in home.devices:
        try:
            collect_device_data(conn, device)
            count += 1
        except Exception as e:
            log.warning("Error reading device %s (%s): %s", device.label, device.id, e)

    try:
        collect_security_data(conn, home)
    except Exception as e:
        log.warning("Error collecting security data: %s", e)

    conn.commit()
    conn.close()
    log.info("Collected data from %d devices", count)


async def main():
    log.info("Starting Homematic IP Data Collector")
    log.info("Poll interval: %d seconds", POLL_INTERVAL)

    config = homematicip.find_and_load_config_file()
    if config is None:
        log.error("No config.ini found! Run 'hmip_generate_auth_token' first.")
        return

    init_db()

    home = Home()
    await home.init_async(config.access_point, auth_token=config.auth_token)

    log.info("Connected to Access Point: %s", config.access_point)

    while True:
        try:
            await poll_once(home)
        except Exception as e:
            log.error("Poll error: %s", e)

        log.info("Next poll in %d seconds...", POLL_INTERVAL)
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
