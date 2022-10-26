# # pylint: disable=line-too-long, missing-module-docstring
# # pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# # pylint: disable=missing-class-docstring, missing-function-docstring

from dataclasses import dataclass
from typing import Optional

import falcon
import pendulum
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response
from sqlalchemy import and_
from sqlalchemy.orm import aliased, Session
from sqlalchemy.sql.expression import func

from chai_api.db_definitions import NetatmoReading, NetatmoDevice, get_home, SetpointChange, Schedule, Profile
from chai_api.energy_loop import get_energy_values, ElectricityPrice
from chai_api.expected import HeatingGet, HeatingPut
from chai_api.responses import HeatingMode, HeatingModeOption, ValveStatus


class MissingPriceError(Exception):
    """ Raised when a price is missing for a given time. """
    pass


class MissingScheduleError(Exception):
    """ Raised when a schedule is missing for the given time. """
    pass


class MissingProfileError(Exception):
    """ Raised when a profile is missing for the given time. """
    pass


@dataclass
class HeatingStatus:
    mode: HeatingModeOption
    temperature: float
    expires_at: Optional[pendulum.DateTime]


def get_heating_status(home_id: int, db_session: Session) -> HeatingStatus:
    """
    Get the current heating status for the given home.
    :param home_id: The ID of the home to get the status for.
    :param db_session: The database session to use when accessing DB information.
    :return: The current heating status. The mode will be one out of the 4 available options. For each mode the
             target temperature to send to Netatmo devices is returned. The expires_at field is only set when the
             current heating status is not controlled by the AI (i.e. pure AUTO mode that isn't OVERRIDE).
    """
    # identify the heating status for the home by first looking for any setpoint changes,
    # and if there are none using the active profile to determine the desired temperature

    # get the mode from the database by looking at setpointChange and see if the last one is unexpired
    # if it is:
    #   - if a manual mode: return on/off
    #   - if an auto mode: return target temperature as set by the user
    #   - if in auto mode, but without a target temperature: the user switched back to default auto mode
    # if it is not:
    #   - it must be in auto mode. The setpoint temperature is calculated as the current profile
    active_setpoint = db_session.query(
        SetpointChange
    ).filter(
        SetpointChange.home_id == home_id
    ).filter(
        SetpointChange.expires_at > func.current_timestamp()
    ).order_by(
        SetpointChange.id.desc()
    ).first()

    if active_setpoint is not None and (active_setpoint.mode != 1 or active_setpoint.temperature is not None):
        mode = HeatingModeOption.OVERRIDE if active_setpoint.mode == 1 else (
            HeatingModeOption.ON if active_setpoint.mode == 2 else HeatingModeOption.OFF
        )
        temperature = active_setpoint.temperature if active_setpoint.mode == 1 else (
            30 if active_setpoint == 2 else 6
        )
        return HeatingStatus(mode, temperature, active_setpoint.expires_at)

    # if we reach this point we know that the system is in auto mode, and we need to calculate the temperature
    # the system is in auto mode
    # grab the current profile for the home, grab the current cost, grab the profile parameters, and calculate
    now = pendulum.now("Europe/London")

    # calculate the 15 min interval for the current time as well as the daymask for the day
    slot = now.hour * 4 + now.minute // 15
    daymask = 2 ** (now.day_of_week - 1)

    # get the cost for the current half hour slot
    values: [ElectricityPrice] = get_energy_values(now, now, limit=1)  # get the current electricity price
    if len(values) != 1:  # if there is no current price, return an error
        raise MissingPriceError
    price = values[0]

    # find the schedule for the given day
    schedule_alias = aliased(Schedule)
    schedule = db_session.query(
        Schedule
    ).outerjoin(
        schedule_alias, and_(
            Schedule.home_id == schedule_alias.home_id,
            Schedule.revision < schedule_alias.revision,
            Schedule.day == schedule_alias.day)
    ).filter(
        schedule_alias.revision == None  # noqa: E711
    ).filter(
        Schedule.home_id == home_id
    ).filter(
        Schedule.day == daymask
    ).first()

    if schedule is None:
        raise MissingScheduleError

    # turn the schedule into a list of (int, int) in reversed order, e.g. [(43, 3), (27, 1), (0, 2)]
    profiles_schedule = [(int(key), int(value)) for (key, value) in schedule.schedule.items()]
    profiles_schedule.sort(key=lambda x: x[0], reverse=True)
    # find the first profile with a slot less than or equal to the slot for the current datetime
    current_profile = next(filter(lambda entry: entry[0] <= slot, profiles_schedule), None)

    # fetch this profile from the database
    subquery = db_session.query(func.max(Profile.id)).filter(
        Profile.home_id == home_id
    ).group_by(Profile.profile_id).subquery()

    profile = db_session.query(
        Profile
    ).filter(
        Profile.id.in_(subquery)
    ).filter(
        Profile.profile_id == current_profile[1]
    ).first()

    if profile is None:
        raise MissingProfileError

    # calculate the temperature and return the result
    temperature = profile.calculate_temperature(price.price)

    return HeatingStatus(HeatingModeOption.AUTO, temperature, None)


def set_netatmo_heating(device: NetatmoDevice, temperature: float, mode: HeatingModeOption,
                        client_id: str, client_secret: str, db_session: Session) -> bool:
    """
    Set the Netatmo device to the desired temperature
    :param device: The Netatmo device to manipulate.
    :param temperature: The temperature to set the device to.
    :param mode: The mode to set the device to.
    :param client_id: The client ID to use when connecting to Netatmo.
    :param client_secret: The client secret to use when connecting to Netatmo.
    :param db_session: The database session to use when accessing DB information.
    :return: The current heating status.
    """
    print(f"simulating Netatmo setting with {client_id} and {client_secret}, for {device.refreshToken} to {temperature}°C on {mode}")
    return True

    # client = NetatmoClient(
    #     client_id=client_id,
    #     client_secret=client_secret,
    #     refresh_token=device.refreshToken
    # )
    # valve_mode = SetpointMode.MANUAL
    # if mode == HeatingModeOption.OFF:
    #     valve_mode = SetpointMode.OFF
    #     temperature = None
    # if mode == HeatingModeOption.ON:
    #     valve_mode = SetpointMode.MAX
    #     temperature = None
    #
    # return client.set_device(device=DeviceType.VALVE, mode=valve_mode, temperature=temperature, minutes=60)


class HeatingResource:
    client_id: str = ""
    client_secret: str = ""

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: HeatingGet = from_dict(HeatingGet, req.params)  # noqa
            db_session = req.context.session

            # find the correct home for the user
            home = get_home(request.label, db_session, req.context.get("user", "anonymous"))

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label, or invalid home token"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            valve_status = db_session.query(
                NetatmoReading
            ).filter(
                NetatmoReading.netatmo_id == home.netatmoID
            ).filter(
                NetatmoReading.room_id == 3  # valve percentage
            ).order_by(
                NetatmoReading.start.desc()
            ).first()

            if valve_status is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "no valve status available"
                resp.status = falcon.HTTP_INTERNAL_SERVER_ERROR
                return

            valve_temperature = db_session.query(
                NetatmoReading
            ).filter(
                NetatmoReading.netatmo_id == home.netatmoID
            ).filter(
                NetatmoReading.room_id == 2  # valve temperature
            ).order_by(
                NetatmoReading.start.desc()
            ).first()

            if valve_temperature is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "no temperature available"
                resp.status = falcon.HTTP_INTERNAL_SERVER_ERROR
                return

            try:
                heating_status = get_heating_status(home.id, db_session)
                resp.content_type = falcon.MEDIA_JSON
                resp.status = falcon.HTTP_OK

                target = heating_status.temperature
                if heating_status.mode in (HeatingModeOption.ON, HeatingModeOption.OFF):
                    target = None
                resp.text = json.dumps(
                    HeatingMode(
                        valve_temperature.reading, heating_status.mode, valve_status.reading > 0,
                        target=target, expires_at=heating_status.expires_at
                    ).to_dict())
            except (MissingPriceError, MissingScheduleError, MissingProfileError) as err:
                resp.content_type = falcon.MEDIA_TEXT
                if isinstance(err, MissingPriceError):
                    resp.text = "no electricity price available"
                elif isinstance(err, MissingScheduleError):
                    resp.text = "no schedule available for today"
                elif isinstance(err, MissingProfileError):
                    resp.text = "no profile available for today"
                resp.status = falcon.HTTP_INTERNAL_SERVER_ERROR
                return
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"

    def on_put(self, req: Request, resp: Response):  # noqa
        try:
            options = req.params
            options.update(req.get_media(default_when_empty=[]))  # noqa
            request: HeatingPut = from_dict(HeatingPut, options, config=Config(cast=[HeatingModeOption, int, float]))
            db_session = req.context.session

            if request.mode == HeatingModeOption.OVERRIDE:
                resp.content_type = falcon.MEDIA_TEXT
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.text = f"do not use 'override' to change mode, use 'on' or 'off' instead"
                return

            if request.mode == HeatingModeOption.AUTO:
                if request.target is not None and (not 7 <= request.target <= 30):
                    resp.content_type = falcon.MEDIA_TEXT
                    resp.text = "target temperature expected between 7 and 30"
                    resp.status = falcon.HTTP_BAD_REQUEST
                    return

            if request.timeout is not None:
                if not 1 <= request.timeout <= 1440:
                    resp.content_type = falcon.MEDIA_TEXT
                    resp.text = "timeout expected between 1 (exclusive) and 1440 (inclusive) minutes"
                    resp.status = falcon.HTTP_BAD_REQUEST
                    return

            # all is looking good, we can link this to the home
            home = get_home(request.label, db_session, req.context.get("user", "anonymous"))

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label, or invalid home token"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            changed_at = pendulum.now("Europe/London")
            duration = 60 if not request.timeout else request.timeout
            expires_at = changed_at.add(minutes=duration)

            # noinspection PyTypeChecker
            setpoint_change = SetpointChange(
                home=home,
                # ignore the warnings; DateTime is a datetime.datetime (compatible) instance
                changed_at=changed_at,
                expires_at=expires_at,
                duration=duration,
                mode=request.mode.get_id(),
                price=get_energy_values(changed_at, changed_at, limit=1)[0].price,
                temperature=request.target if request.mode == HeatingModeOption.AUTO else None
            )

            db_session.add(setpoint_change)
            db_session.commit()

            heating_status = get_heating_status(home.id, db_session)
            set_netatmo_heating(
                home.relay, heating_status.temperature, heating_status.mode,
                self.client_id, self.client_secret, db_session
            )

            resp.content_type = falcon.MEDIA_JSON
            resp.status = falcon.HTTP_OK
        except (DaciteError, ValueError) as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"


class ValveResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: HeatingGet = from_dict(HeatingGet, req.params)  # noqa
            db_session = req.context.session

            # find the correct home for the user
            home = get_home(request.label, db_session, req.context.get("user", "anonymous"))

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label, or invalid home token"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            reading = db_session.query(
                NetatmoReading
            ).filter(
                NetatmoReading.netatmo_id == home.netatmoID
            ).filter(
                NetatmoReading.room_id == 3  # valve percentage
            ).order_by(
                NetatmoReading.start.desc()
            ).first()

            if reading is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "no valve status available"
                resp.status = falcon.HTTP_INTERNAL_SERVER_ERROR
                return

            resp.content_type = falcon.MEDIA_JSON
            resp.text = json.dumps(ValveStatus(open=reading.reading > 0).to_dict())
            resp.status = falcon.HTTP_OK

        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
