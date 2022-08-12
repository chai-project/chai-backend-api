# pylint: disable=line-too-long, invalid-name, missing-module-docstring, missing-class-docstring

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, List, Dict
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


@dataclass
class LogEntry:
    timestamp: DateTime
    category: str
    parameters: List

    def to_dict(self):  # pylint: disable=missing-function-docstring
        values = {
            "timestamp": self.timestamp.isoformat(),
            "category": self.category.upper(),
            "parameters": self.parameters,
        }
        return values


@dataclass
class ScheduleEntry:
    day: int
    schedule: Dict[str, str]

    def to_dict(self):  # pylint: disable=missing-function-docstring
        values = {
            "day": self.day,
            "schedule": self.schedule,
        }
        return values


@dataclass
class ProfileEntry:
    profile: int
    slope: float
    bias: float

    def to_dict(self):  # pylint: disable=missing-function-docstring
        values = {
            "profile": self.profile,
            "slope": self.slope,
            "bias": self.bias,
        }
        return values
