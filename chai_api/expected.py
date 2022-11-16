# pylint: disable=line-too-long, invalid-name, missing-module-docstring, missing-class-docstring

from dataclasses import dataclass
from enum import Enum
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
    timeout: Optional[int]
    hidden: Optional[bool]

    def __post_init__(self):
        if self.hidden is None:
            self.hidden = False


class HistoryOption(Enum):
    TEMPERATURE = "temperature"
    VALVE_STATUS = "valve_status"


@dataclass
class HistoryGet:
    label: str
    source: HistoryOption
    start: Optional[DateTime]  # defaults to one week ago, or one week before end
    end: Optional[DateTime]

    def __post_init__(self):
        if self.start is None:
            if self.end is None:
                self.start = DateTime.now("Europe/London").add(days=-7)
            else:
                self.start = self.end.add(days=-7)


@dataclass
class ScheduleGet:
    label: str
    daymask: int


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
class LogsGet:
    label: str
    category: Optional[str]
    start: Optional[DateTime]  # defaults to one week ago, or one week before end
    end: Optional[DateTime]
    limit: Optional[int]
    skip: Optional[int]

    def __post_init__(self):
        if self.start is None:
            if self.end is None:
                self.start = DateTime.now("Europe/London").add(days=-7)
            else:
                self.start = self.end.add(days=-7)

        if self.limit is None:
            self.limit = 25
        elif self.limit < 0:
            self.limit = 0

        if self.skip is None or self.skip < 0:
            self.skip = 0


@dataclass
class LogsPut:
    label: str
    category: str
    timestamp: DateTime
    parameters: list


@dataclass
class ProfileGet:
    label: str
    profile: Optional[int]


@dataclass
class XAIGet:
    label: str
    profile: int
    skip: Optional[int]

    def __post_init__(self):
        if self.skip is None or self.skip < 0:
            self.skip = 0


@dataclass
class AttackPut:
    modifier: float
    duration: Optional[int]  # in minutes, must be multiple of 30

    def __post_init__(self):
        if self.duration is None:
            self.duration = 60
