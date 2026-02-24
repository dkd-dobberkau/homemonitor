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
from datetime import datetime
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
    PlugableSwitchMeasuring,
    BrandSwitchMeasuring,
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
    conn.commit()
    conn.close()
    log.info("Database initialized at %s", DB_PATH)


def store_reading(conn, device_id, device_label, device_type, metric, value, value_text=None):
    """Store a single reading in the database."""
    conn.execute(
        """INSERT INTO device_readings
           (timestamp, device_id, device_label, device_type, metric, value, value_text)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (datetime.utcnow().isoformat(), device_id, device_label, device_type, metric, value, value_text),
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


async def poll_once(home):
    """Fetch current state from the cloud and store all device data."""
    await home.get_current_state()

    conn = sqlite3.connect(str(DB_PATH))
    count = 0

    for device in home.devices:
        try:
            collect_device_data(conn, device)
            count += 1
        except Exception as e:
            log.warning("Error reading device %s (%s): %s", device.label, device.id, e)

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

    home = Home()
    home.set_auth_token(config.auth_token)
    home.init(config.access_point)

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
