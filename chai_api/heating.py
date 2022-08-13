# # pylint: disable=line-too-long, missing-module-docstring
# # pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# # pylint: disable=missing-class-docstring, missing-function-docstring

import falcon
import pendulum
import ujson as json
from dacite import from_dict, DaciteError, Config
from datetime import datetime
from falcon import Request, Response
from sqlalchemy import and_
from sqlalchemy.orm import aliased
from sqlalchemy.sql.expression import func

from chai_api.db_definitions import NetatmoReading, get_home, SetpointChange, Schedule, Profile
from chai_api.energy_loop import get_energy_values, ElectricityPrice
from chai_api.expected import HeatingGet, HeatingPut
from chai_api.responses import HeatingMode, HeatingModeOption, ValveStatus


class HeatingResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: HeatingGet = from_dict(HeatingGet, req.params)
            db_session = req.context.session

            # find the correct home for the user
            home = get_home(request.label, db_session)

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label"
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

            # get the mode from the database by looking at setpointChange and see if the last one is unexpired
            # if it is:
            #   - if a manual mode: return on/off
            #   - if an auto mode: return target temperature as set by the user
            # if it is not:
            #   - it must be in auto mode. The setpoint temperature is calculated as the current profile

            active_setpoint = db_session.query(
                SetpointChange
            ).filter(
                SetpointChange.home_id == home.id
            ).filter(
                SetpointChange.expires_at > func.current_timestamp()
            ).first()

            if active_setpoint is not None:
                resp.content_type = falcon.MEDIA_JSON
                option = HeatingModeOption.OVERRIDE if active_setpoint.mode == 1 else (
                    HeatingModeOption.ON if active_setpoint.mode == 2 else HeatingModeOption.OFF
                )
                resp.text = json.dumps(
                    HeatingMode(
                        valve_temperature.reading, option, valve_status.reading > 0,
                        target=active_setpoint.temperature if option == HeatingModeOption.OVERRIDE else None,
                        expires_at=active_setpoint.expires_at
                    ).to_dict())
                resp.status = falcon.HTTP_OK
                return

            # the system is in auto mode
            # grab the current profile for the home, grab the current cost, grab the profile parameters, and calculate
            now = pendulum.now("Europe/London")

            # calculate the 15 min interval for the current time as well as the daymask for the day
            slot = now.hour * 4 + now.minute // 15
            daymask = 2 ** (now.day_of_week - 1)

            # get the cost for the current half hour slot
            values: [ElectricityPrice] = get_energy_values(now, now, limit=1)  # get the current electricity price
            if len(values) != 1:  # if there is no current price, return an error
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "no electricity price available"
                resp.status = falcon.HTTP_INTERNAL_SERVER_ERROR
                return
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
                Schedule.home_id == home.id
            ).filter(
                Schedule.day == daymask
            ).first()

            if schedule is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "no schedule available for today"
                resp.status = falcon.HTTP_INTERNAL_SERVER_ERROR
                return

            # turn the schedule into a list of (int, int) in reversed order, e.g. [(43, 3), (27, 1), (0, 2)]
            profiles_schedule = [(int(key), int(value)) for (key, value) in schedule.schedule.items()]
            profiles_schedule.sort(key=lambda x: x[0], reverse=True)
            # find the first profile with a slot less than or equal to the slot for the current datetime
            current_profile = next(filter(lambda entry: entry[0] <= slot, profiles_schedule), None)
            print(f"profile: {current_profile}")

            # fetch this profile from the database
            subquery = db_session.query(func.max(Profile.id)).filter(
                Profile.home_id == home.id
            ).group_by(Profile.profile_id).subquery()

            profile = db_session.query(
                Profile
            ).filter(
                Profile.id.in_(subquery)
            ).filter(
                Profile.profile_id == current_profile[1]
            ).first()

            if profile is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "no profile available for today"
                resp.status = falcon.HTTP_INTERNAL_SERVER_ERROR
                return

            # calculate the temperature and return the result
            temperature = profile.calculate_temperature(price.price)

            resp.text = json.dumps(
                HeatingMode(valve_temperature.reading, HeatingModeOption.AUTO,
                            valve_status.reading > 0, target=temperature,
                            expires_at=None).to_dict())
            resp.status = falcon.HTTP_OK
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"

    def on_put(self, req: Request, resp: Response):  # noqa
        try:
            print(req.media)
            request: HeatingPut = from_dict(HeatingPut, req.media, config=Config(cast=[HeatingModeOption]))
            db_session = req.context.session

            if request.mode == HeatingModeOption.OVERRIDE:
                resp.content_type = falcon.MEDIA_TEXT
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.text = f"one or more of the parameters was not understood"
                return

            if request.mode == HeatingModeOption.AUTO:
                if request.target is None:
                    resp.content_type = falcon.MEDIA_TEXT
                    resp.text = "target temperature expected for auto mode"
                    resp.status = falcon.HTTP_BAD_REQUEST
                    return
                if not 7 <= request.target <= 30:
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
            home = get_home(request.label, db_session)

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            changed_at = pendulum.now("Europe/London")
            expires_at = changed_at.add(minutes=60)

            setpoint_change = SetpointChange(
                home=home,
                changed_at=datetime.fromtimestamp(changed_at.timestamp(), pendulum.timezone("Europe/London")),
                expires_at=datetime.fromtimestamp(expires_at.timestamp(), pendulum.timezone("Europe/London")),
                duration=60 if not request.timeout else request.timeout, mode=request.mode.get_id(),
                temperature=request.target if request.mode == HeatingModeOption.AUTO else None
            )

            db_session.add(setpoint_change)
            db_session.commit()

            # TODO: trigger Netatmo thermostatic valve change
            resp.status = falcon.HTTP_OK
        except (DaciteError, ValueError) as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"


class ValveResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: HeatingGet = from_dict(HeatingGet, req.params)
            db_session = req.context.session

            # find the correct home for the user
            home = get_home(request.label, db_session)

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label"
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
