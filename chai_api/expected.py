# pylint: disable=line-too-long, invalid-name, missing-module-docstring, missing-class-docstring

from dataclasses import dataclass
from pendulum import DateTime
from typing import Optional

from pendulum import DateTime

from chai_api.responses import HeatingModeOption


@dataclass
class HeatingGet:
    label: str


@dataclass
class HeatingPut:
    label: str
    mode: HeatingModeOption
    target: Optional[float]


@dataclass
class BatteryGet:
    label: str


@dataclass
class BatteryPut:
    label: str
    mode: BatteryModeOption


@dataclass
class PricesGet:
    start: Optional[DateTime]  # defaults to right now
    end: Optional[DateTime]
    limit: Optional[int]
    default_start: Optional[bool]

    def __post_init__(self):
        if self.start is None:
            self.start = DateTime.now("Europe/London")
            self.default_start = True
        else:
            self.default_start = False


@dataclass
class CurrentGet:
    label: str
