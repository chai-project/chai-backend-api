# pylint: disable=line-too-long, invalid-name, missing-module-docstring, missing-class-docstring

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional
from pendulum import DateTime


class BatteryChargeStatus(Enum):
    CHARGE = "charge"
    DISCHARGE = "discharge"
    OFF = "off"


class BatteryModeOption(Enum):
    AUTO = "auto"
    CHARGE = "charge"
    DISCHARGE = "discharge"
    OFF = "off"


class HeatingModeOption(Enum):
    AUTO = "auto"
    ON = "on"
    OFF = "off"


@dataclass
class HeatingMode:
    temperature: float
    mode: HeatingModeOption
    valve: bool
    target: Optional[float]

    def to_dict(self):  # pylint: disable=missing-function-docstring
        values = {
            "temperature": self.temperature,
            "mode": self.mode.value,
            "valve_open": self.valve,
        }
        if self.target is not None:
            values["target_temperature"] = self.target
        return values


@dataclass
class ValveStatus:
    open: bool

    def to_dict(self):  # pylint: disable=missing-function-docstring
        return asdict(self)
