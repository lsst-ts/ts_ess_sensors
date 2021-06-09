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

__all__ = ["CommandHandler"]

import asyncio
import logging
import platform
import time
from typing import Any, Callable, Dict, List, Optional, Union

from .command_error import CommandError
from .constants import Command, Key, DeviceType
from .ess_instrument_object import EssInstrument
from .mock.mock_temperature_sensor import MockTemperatureSensor
from .response_code import ResponseCode
from .sel_temperature_reader import SelTemperature


class CommandHandler:
    """Handle incoming commands and send replies. Apply configuration and read
    sensor data.

    Parameters
    ----------
    callback: `Callable`
        The callback coroutine handling the sensor telemetry. This can be a
        coroutine that sends the data via a socket connection or a coroutine in
        a test class to verify that the command has been handled correctly.
    simulation_mode: `int`
        Indicating if a simulation mode (> 0) or not (0) is active.

    The commands that can be handled are:

        configure: Load the configuration that is passed on with the command
        and connect to the devices specified in that configuration. This
        command can be sent multiple times before a start is received and only
        the last configuration is kept.
        start: Start reading the sensor data of the connected devices and send
        it as plain text via the socket. If no configuration was sent then the
        start command is ignored. Once started no configuration changes can be
        done anymore.
        stop: Stop sending sensor data and disconnect from all devices. Once
        stopped, configuration changes can be done again and/or reading of
        sensor data can be started again.

    """

    valid_simulation_modes = (0, 1)

    def __init__(self, callback: Callable, simulation_mode: int) -> None:
        self.log = logging.getLogger(type(self).__name__)
        if simulation_mode not in self.valid_simulation_modes:
            raise ValueError(
                f"simulation_mode={simulation_mode} "
                f"not in valid_simulation_modes={self.valid_simulation_modes}"
            )

        self.simulation_mode = simulation_mode

        self._callback = callback
        self._configuration: Optional[Dict[str, Any]] = None
        self._started = False
        self._ess_instruments: List[EssInstrument] = []

        self.dispatch_dict: Dict[str, Callable] = {
            Command.CONFIGURE: self.configure,
            Command.START: self.start_sending_telemetry,
            Command.STOP: self.stop_sending_telemetry,
        }

        # Unit tests may set this to an integer value to simulate a
        # disconnected or missing sensor.
        self.disconnected_channel = None

    async def handle_command(self, command: str, **kwargs: Any) -> None:
        """Handle incomming commands and parameters.

        Parameters
        ----------
        command: `str`
            The command to handle.
        kwargs:
            The parameters to the command.
        """
        self.log.info(f"Handling command {command} with kwargs {kwargs}")
        func = self.dispatch_dict[command]
        try:
            await func(**kwargs)
            response = {Key.RESPONSE: ResponseCode.OK}
        except CommandError as e:
            response = {Key.RESPONSE: e.response_code}
        await self._callback(response)

    def _validate_configuration(self, configuration: Dict[str, Any]):
        """Validate the configuration.

        Parameters
        ----------
        configuration: `dict`
            A dict representing the configuration. The format of the dict
            follows the configuration of the ts_ess project.

        Raises
        ------
        `CommandError`:
            In case the provided configuration is incorrect.

        """
        # Key.DEVICES is mandatory.
        if Key.DEVICES not in configuration:
            raise CommandError(
                msg=f"Missing configuration key {Key.DEVICES}.",
                response_code=ResponseCode.INVALID_CONFIGURATION,
            )
        # Only one key allowed.
        if len(configuration.keys()) != 1:
            raise CommandError(
                msg=f"Expected one configuration key but got {len(configuration.keys())}.",
                response_code=ResponseCode.INVALID_CONFIGURATION,
            )
        # Validate the device configurations.
        device_configurations = configuration[Key.DEVICES]
        if not device_configurations:
            raise CommandError(
                msg=f"The configuration data for key {Key.DEVICES} is missing.",
                response_code=ResponseCode.INVALID_CONFIGURATION,
            )
        for device_configuration in device_configurations:
            self._validate_device_configuration(
                device_configuration=device_configuration
            )

    def _validate_device_configuration(self, device_configuration: Dict[str, Any]):
        """Validate the device configuration.

        Parameters
        ----------
        device_configuration: `dict`
            A dict representing the device configuration. The format of the
            dict follows the configuration of the ts_ess project.

        Raises
        ------
        `CommandError`:
            In case the provided configuration is incorrect.

        """
        # Key.NAME, Key.CHANNELS and Key.TYPE are mandatory.
        if (
            Key.NAME not in device_configuration
            or Key.CHANNELS not in device_configuration
            or Key.TYPE not in device_configuration
        ):
            raise CommandError(
                msg=f"The configuration keys {Key.NAME}, {Key.CHANNELS} and {Key.TYPE} are mandatory.",
                response_code=ResponseCode.INVALID_CONFIGURATION,
            )

        # Make sure that Key.TYPE has the correct value.
        if device_configuration[Key.TYPE] not in [DeviceType.FTDI, DeviceType.SERIAL]:
            raise CommandError(
                msg=f"The value for key {Key.TYPE} must be either {DeviceType.FTDI} or {DeviceType.SERIAL}",
                response_code=ResponseCode.INVALID_CONFIGURATION,
            )

        # Make sure that Key.FTDI_ID is present for DeviceType.FTDI devices.
        if device_configuration[Key.TYPE] == DeviceType.FTDI:
            if Key.FTDI_ID not in device_configuration:
                raise CommandError(
                    msg=f"Missing configuration key {Key.FTDI_ID} for device of type {DeviceType.FTDI}",
                    response_code=ResponseCode.INVALID_CONFIGURATION,
                )
        # Make sure that Key.SERIAL_PORT is present for DeviceType.SERIAL
        # devices.
        if device_configuration[Key.TYPE] == DeviceType.SERIAL:
            if Key.SERIAL_PORT not in device_configuration:
                raise CommandError(
                    msg=f"Missing configuration key {Key.SERIAL_PORT} for device of type {DeviceType.SERIAL}",
                    response_code=ResponseCode.INVALID_CONFIGURATION,
                )

    async def configure(self, configuration: Dict[str, Any]) -> None:
        """Apply the configuration.

        Parameters
        ----------
        configuration: `dict`
            The contents of the dict depend on the type of sensor. See the
            ts_ess configuration schema for more details.

        Returns
        -------
        response_code: `ResponseCode`
            OK if the command handler was not started.
            ALREADY_STARTED if the command handler was started.

        """
        self.log.info(f"configure with configuration data {configuration}")
        if self._started:
            raise CommandError(
                msg="Ignoring the configuration because telemetry loop already running. Send a stop first.",
                response_code=ResponseCode.ALREADY_STARTED,
            )
        self._validate_configuration(configuration=configuration)

        self._configuration = configuration

    async def start_sending_telemetry(self) -> None:
        """Connect the sensors and start reading the sensor data.

        Returns
        -------
        response_code: `ResponseCode`
            OK if the command handler was configured.
            NOT_CONFIGURED if the command handler was not configured.

        """
        self.log.info("start_sending_telemetry")
        if not self._configuration:
            raise CommandError(
                msg="No configuration has been received yet. Ignoring start command.",
                response_code=ResponseCode.NOT_CONFIGURED,
            )
        await self.connect_devices()
        self._started = True

    async def connect_devices(self) -> None:
        """Loop over the configuration and start all devices."""
        self.log.info("connect_devices")
        device_configurations = self._configuration[Key.DEVICES]  # type: ignore
        for device_configuration in device_configurations:
            device = self._get_device(device_configuration)
            sel_temperature = SelTemperature(
                name=device_configuration[Key.NAME],
                uart_device=device,
                channels=device_configuration[Key.CHANNELS],
                log=self.log,
            )
            ess_instrument = EssInstrument(
                name=device_configuration[Key.NAME],
                reader=sel_temperature,
                callback_func=self._process_sensor_telemetry,
                log=self.log,
            )

            self._ess_instruments.append(ess_instrument)
            await ess_instrument.start()

    async def stop_sending_telemetry(self) -> ResponseCode:
        """Stop reading the sensor data.

        Returns
        -------
        response_code: `ResponseCode`
            OK if the command handler was started.
            NOT_STARTED if the command handler was not started.

        """
        self.log.info("stop_sending_telemetry")
        if not self._started:
            raise CommandError(
                msg="Not started yet. Ignoring stop command.",
                response_code=ResponseCode.NOT_STARTED,
            )
        self._started = False
        for ess_instrument in self._ess_instruments:
            await ess_instrument.stop()
            self._ess_instruments.remove(ess_instrument)
        return ResponseCode.OK

    async def _process_sensor_telemetry(self, telemetry: list) -> None:
        """wrap the telemetry in a dictionary and pass it on to the callback
        coroutine.

        It is up to the callback coroutine to handle the telemetry further
        (e.g. in case of the SocketServer the telemetry gets sent to the
        client).

        Parameters
        ----------
        telemetry: `list`
            The telemetry data to send.
        """
        self.log.debug(f"Processing sensor data {telemetry}")
        data = {Key.TELEMETRY: telemetry}
        await self._callback(data)

    def _get_device(self, device_configuration: dict) -> Optional[Any]:
        """Get the device to connect to by using the configuration of the CSC
        and by detecting whether the code is running on an aarch64 architecture
        or not.

        Parameters
        ----------
        device_configuration: `dict`
            A dict representing the device to connect to. The format of the
            dict follows the configuration of the ts_ess project.

        Returns
        -------
        device: `MockTemperatureSensor` or `VcpFtdi` or `RpiSerialHat` or
            `None`
            The device to connect to.

        Raises
        ------
        RuntimeError
            In case an incorrect configuration has been loaded.
        """
        device: Any = None
        if self.simulation_mode == 1:
            self.log.info("Connecting to the mock sensor.")
            device = MockTemperatureSensor(
                device_configuration[Key.NAME],
                device_configuration[Key.CHANNELS],
                disconnected_channel=self.disconnected_channel,
            )
        elif device_configuration[Key.TYPE] == DeviceType.FTDI:
            from .vcp_ftdi import VcpFtdi

            device = VcpFtdi(
                device_configuration[Key.NAME],
                device_configuration[Key.FTDI_ID],
                self.log,
            )
        elif device_configuration[Key.TYPE] == DeviceType.SERIAL:
            # make sure we are on a Raspberry Pi4
            if "aarch64" in platform.platform():
                from .rpi_serial_hat import RpiSerialHat

                device = RpiSerialHat(
                    device_configuration[Key.NAME],
                    device_configuration[Key.SERIAL_PORT],
                    self.log,
                )

        if device is None:
            raise RuntimeError(
                f"Could not get a {device_configuration['type']!r} device on "
                f"architecture {platform.platform()}. Please check the "
                f"configuration."
            )
        return device
