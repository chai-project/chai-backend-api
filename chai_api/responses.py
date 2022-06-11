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
    target: Optional[float]

    def to_dict(self):
        values = {
            "temperature": self.temperature,
            "mode": self.mode.value,
        }
        if self.target is not None:
            values["target_temperature"] = self.target
        return values


@dataclass
class ValveStatus:
    open: bool

    def to_dict(self):
        return asdict(self)


@dataclass
class BatteryMode:
    mode: BatteryModeOption
    status: BatteryChargeStatus
    percentage: int

    def to_dict(self):
        return {
            "mode": self.mode.value,
            "status": self.status.value,
            "percentage": max(0, min(100, self.percentage))
        }


@dataclass
class Rate:
    start: DateTime
    end: DateTime
    rate: float
    predicted: bool

    def to_dict(self):
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "rate": self.rate,
            "predicted": self.predicted,
        }


@dataclass
class Current:
    power: int

    def to_dict(self):
        return {
            "power": self.power,
        }
