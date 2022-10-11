# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

import falcon
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response
from pendulum import DateTime, parse

from chai_api.db_definitions import NetatmoReading, get_home
from chai_api.expected import HistoryGet, HistoryOption


class HistoryResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: HistoryGet = from_dict(HistoryGet, req.params,
                                            config=Config({DateTime: parse}, cast=[HistoryOption]))

            db_session = req.context.session

            # find the correct home for the user
            home = get_home(request.label, db_session, req.context.get("user", "anonymous"))

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label, or invalid home token"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            query = db_session.query(
                NetatmoReading
            ).filter(
                NetatmoReading.netatmo_id == home.netatmoID
            ).filter(
                NetatmoReading.room_id == (2 if request.source == HistoryOption.TEMPERATURE else 3)
            ).filter(
                NetatmoReading.start >= request.start
            )

            if request.end is not None:
                query = query.filter(NetatmoReading.end <= request.end)

            result: [NetatmoReading] = query.all()

            response = [{"timestamp": entry.start.isoformat(), "value": entry.reading} for entry in result]

            resp.content_type = falcon.MEDIA_JSON
            resp.text = json.dumps(response)
            resp.status = falcon.HTTP_OK
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
        except ValueError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters has an invalid value:\n{err}"
