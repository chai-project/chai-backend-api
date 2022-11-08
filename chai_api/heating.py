# # pylint: disable=line-too-long, missing-module-docstring
# # pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# # pylint: disable=missing-class-docstring, missing-function-docstring

import os
import shelve
import sys
from dataclasses import dataclass
from typing import Optional

import click
import falcon
import pendulum
import tomli
import ujson as json
from chai_data_sources import NetatmoClient, SetpointMode, DeviceType
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response
from pushover_complete import PushoverAPI as Pushover
from sqlalchemy import and_
from sqlalchemy.orm import aliased, Session
from sqlalchemy.sql.expression import func

from chai_api.db_definitions import NetatmoReading, NetatmoDevice, get_home, SetpointChange, Schedule, Profile, Home
from chai_api.db_definitions import db_engine_manager, db_session_manager, Configuration as DBConfiguration
from chai_api.energy_loop import get_energy_values, ElectricityPrice
from chai_api.expected import HeatingGet, HeatingPut
from chai_api.responses import HeatingMode, HeatingModeOption, ValveStatus


class MissingPriceError(Exception):
    """ Raised when a price is missing for a given time. """
    pass

    def __str__(self):
        return f"MissingPriceError"


class MissingScheduleError(Exception):
    """ Raised when a schedule is missing for the given time. """
    pass

    def __str__(self):
        return f"MissingScheduleError"


class MissingProfileError(Exception):
    """ Raised when a profile is missing for the given time. """
    pass

    def __str__(self):
        return f"MissingProfileError"


@dataclass
class HeatingStatus:
    mode: HeatingModeOption
    temperature: float
    expires_at: Optional[pendulum.DateTime]


def _get_heating_status(home_id: int, db_session: Session, shelve_db: str) -> HeatingStatus:
    """
    Get the current heating status for the given home.
    :param home_id: The ID of the home to get the status for.
    :param db_session: The database session to use when accessing DB information.
    :param shelve_db: The path to the shelve database to use for pricing attacks.
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
    day_of_week = now.day_of_week
    day_of_week = day_of_week if day_of_week != 0 else 7
    daymask = 2 ** (day_of_week - 1)

    # get the cost for the current half hour slot
    values: [ElectricityPrice] = get_energy_values(now, now, limit=1, shelve_db=shelve_db)  # get current elec price
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
                        client_id: str, client_secret: str) -> bool:
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
    client = NetatmoClient(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=device.refreshToken
    )
    valve_mode = SetpointMode.MANUAL
    if mode == HeatingModeOption.OFF:
        valve_mode = SetpointMode.OFF
        temperature = None
    if mode == HeatingModeOption.ON:
        valve_mode = SetpointMode.MANUAL
        temperature = 30

    if temperature is not None:
        temperature = temperature

    print(f"setting {device.refreshToken} to {temperature}°C in mode {valve_mode}")
    return client.set_device(device=DeviceType.VALVE, mode=valve_mode, temperature=temperature, minutes=60)


class HeatingResource:
    client_id: str = ""
    client_secret: str = ""
    shelve_db: str = ""

    def __init__(self, client_id, client_secret, shelve_location):
        self.client_id = client_id
        self.client_secret = client_secret
        self.shelve_db = shelve_location

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
                heating_status = _get_heating_status(home.id, db_session, shelve_db=self.shelve_db)
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
                price=get_energy_values(changed_at, changed_at, limit=1, shelve_db=self.shelve_db)[0].price,
                temperature=request.target if request.mode == HeatingModeOption.AUTO else None
            )

            db_session.add(setpoint_change)
            db_session.commit()

            heating_status = _get_heating_status(home.id, db_session, shelve_db=self.shelve_db)
            set_netatmo_heating(
                home.relay, heating_status.temperature, heating_status.mode,
                self.client_id, self.client_secret
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


@click.command()
@click.option("--config", default=None, help="The TOML configuration file.")
def cli(config):  # pylint: disable=invalid-name
    db_server = ""
    db_name = ""
    db_username = ""
    db_password = ""
    pushover_app = ""
    pushover_user = ""
    netatmo_id = ""
    netatmo_secret = ""

    if config and not os.path.isfile(config):
        click.echo("The configuration file is not found. Please provide a valid file path.")
        sys.exit(0)

    if config:
        with open(config, "rb") as file:
            try:
                toml = tomli.load(file)

                shelve_location = toml["server"]["shelve"]
                with shelve.open(shelve_location) as shelve_db:
                    shelve_db["test"] = "test"
                    del shelve_db["test"]

                if toml_db := toml["database"]:
                    db_server = str(toml_db["server"])
                    db_name = str(toml_db["dbname"])
                    db_username = str(toml_db["user"])
                    db_password = str(toml_db["pass"])
                if toml_pushover := toml["pushover"]:
                    pushover_app = str(toml_pushover["app"])
                    pushover_user = str(toml_pushover["user"])
                if toml_netatmo := toml["netatmo"]:
                    netatmo_id = str(toml_netatmo["client_id"])
                    netatmo_secret = str(toml_netatmo["client_secret"])

                main(
                    db_server=db_server, db_name=db_name, db_username=db_username, db_password=db_password,
                    pushover_app=pushover_app, pushover_user=pushover_user,
                    client_id=netatmo_id, client_secret=netatmo_secret,
                    shelve_db=shelve_location
                )

            except tomli.TOMLDecodeError:
                click.echo("The configuration file is not valid and cannot be parsed.")
                sys.exit(0)
            except KeyError as err:
                click.echo(f"The configuration file is missing some expected values: {err}.")
                sys.exit(0)
            except AssertionError:
                click.echo("Make sure the prediction_banded list for each profile has 36 entries, each of 3 elements.")
                sys.exit(0)
            except Exception as err:
                click.echo(f"Unable to open and write to the shelve file: {err}")
                sys.exit(0)


def main(*, db_server: str, db_name: str, db_username: str, db_password: str,
         pushover_app: str, pushover_user: str, client_id: str, client_secret: str, shelve_db: str):

    pushover = Pushover(pushover_app)

    def send_message(message: str, title="CHAI API Netatmo") -> None:
        if pushover is not None:
            print("sending Pushover message")
            pushover.send_message(pushover_user, message, title=title)

    # connect to the database
    with db_engine_manager(DBConfiguration(db_server, db_username, db_password, db_name)) as db_engine:
        with db_session_manager(db_engine) as session:
            # fetch all active homes
            home_alias = aliased(Home)
            homes = session.query(
                Home
            ).outerjoin(
                home_alias, and_(Home.label == home_alias.label, Home.revision < home_alias.revision)
            ).filter(
                home_alias.revision == None  # noqa: E711
            ).all()

            for home in homes:
                # calculate the desired temperature point
                status = _get_heating_status(home.id, session, shelve_db=shelve_db)
                # make the Netatmo call to change the temperature
                try:
                    set_netatmo_heating(home.relay, status.temperature, status.mode, client_id, client_secret)
                    print(f"set the Netatmo valve for the property with the label {home.label}")
                except Exception as _err:  # noqa
                    send_message(f"Failed to set the Netatmo valve for the property with label {home.label}.")


if __name__ == "__main__":
    cli()
