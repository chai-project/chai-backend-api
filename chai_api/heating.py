# # pylint: disable=line-too-long, missing-module-docstring
# # pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# # pylint: disable=missing-class-docstring, missing-function-docstring

import falcon
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response

from chai_api.db_definitions import NetatmoReading, get_home
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

            resp.content_type = falcon.MEDIA_JSON
            # TODO: hard-coded mode
            # TODO: hard-coded target
            resp.text = json.dumps(
                HeatingMode(valve_temperature.reading, HeatingModeOption.AUTO, valve_status.reading > 0,
                            target=25).to_dict())
            resp.status = falcon.HTTP_OK
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"

    def on_put(self, req: Request, resp: Response):  # noqa
        try:
            request: HeatingPut = from_dict(HeatingPut, req.params, config=Config(cast=[HeatingModeOption]))

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

                # TODO: implement PUT /heating/mode

        except (DaciteError, ValueError):
            resp.status = falcon.HTTP_BAD_REQUEST


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

        except DaciteError:
            resp.status = falcon.HTTP_BAD_REQUEST
