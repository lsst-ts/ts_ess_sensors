# This file is part of ts_envsensors.
#
# Developed for the Vera C. Rubin Observatory Telescope and Site Systems.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__all__ = [
    "Command",
    "DeviceType",
    "DISCONNECTED_VALUE",
    "Key",
    "SensorType",
    "MockTemperatureConfig",
]

import enum
from types import SimpleNamespace

# Minimum and maximum temperatures (deg_C) for creating random sensor data.

# The value emitted by a disconnected channel
DISCONNECTED_VALUE = "9999.9990"

"""The minimum and maximum temperatures used by the mock temperature device."""
MockTemperatureConfig = SimpleNamespace(min=18.0, max=30.0)


class Command(str, enum.Enum):
    """Commands accepted by the Socket Server and Command Handler."""

    CONFIGURE = "configure"
    DISCONNECT = "disconnect"
    EXIT = "exit"
    START = "start"
    STOP = "stop"


class DeviceType(str, enum.Enum):
    """Supported device types."""

    FTDI = "FTDI"
    SERIAL = "Serial"


class Key(str, enum.Enum):
    """Keys that may be present in the device configuration or as command
    parameters."""

    CHANNELS = "channels"
    CONFIGURATION = "configuration"
    DEVICE_TYPE = "device_type"
    DEVICES = "devices"
    FTDI_ID = "ftdi_id"
    NAME = "name"
    RESPONSE = "response"
    SENSOR_TYPE = "sensor_type"
    SERIAL_PORT = "serial_port"
    TELEMETRY = "telemetry"
    TIME = "time"


class SensorType(str, enum.Enum):
    """Supported sensor types."""

    TEMPERATURE = "Temperature"
    WIND = "Wind"
