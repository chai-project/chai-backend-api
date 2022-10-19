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
    OVERRIDE = "override"

    def get_id(self) -> int:
        if self == HeatingModeOption.AUTO:
            return 1
        elif self == HeatingModeOption.ON:
            return 2
        elif self == HeatingModeOption.OFF:
            return 3
        raise ValueError(f"Unknown heating mode '{self.value}'.")


@dataclass
class HeatingMode:
    temperature: float
    mode: HeatingModeOption
    valve: bool
    target: Optional[float]
    expires_at: Optional[DateTime]

    def to_dict(self):  # pylint: disable=missing-function-docstring
        values = {
            "temperature": self.temperature,
            "mode": self.mode.value,
            "valve_open": self.valve,
        }
        if self.target is not None:
            values["target_temperature"] = self.target
        if self.expires_at is not None:
            values["expires_at"] = self.expires_at.isoformat()
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


@dataclass
class XAIRegion:
    profile: int
    centre_x: float
    centre_y: float
    angle: float
    height: float
    width: float
    skip: int

    def to_dict(self):  # pylint: disable=missing-function-docstring
        values = {
            "profile": self.profile,
            "centre_x": round(self.centre_x, 4),
            "centre_y": round(self.centre_y, 4),
            "angle": self.angle,
            "height": self.height,
            "width": self.width,
            "skip": self.skip,
        }
        return values


@dataclass
class XAIBand:
    lower_confidence: List[float]
    prediction: List[float]
    upper_confidence: List[float]
    skip: int

    def to_dict(self):  # pylint: disable=missing-function-docstring
        values = {
            "lower_confidence": self.lower_confidence,
            "prediction": self.prediction,
            "upper_confidence": self.upper_confidence,
            "skip": self.skip,
        }
        return values


@dataclass
class XAIScatterEntry:
    price: float
    temperature: float

    def to_dict(self):
        values = {
            "price": self.price,
            "temperature": self.temperature,
        }
        return values


@dataclass
class XAIScatter:
    entries: List[XAIScatterEntry]
    count: int

    def to_dict(self):
        values = {
            "entries": [entry.to_dict() for entry in self.entries],
            "count": self.count,
        }
        return values
