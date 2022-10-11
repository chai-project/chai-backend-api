# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

import falcon
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response
from pendulum import DateTime, parse

from chai_api.db_definitions import Log, get_home
from chai_api.expected import LogsGet
from chai_api.responses import LogEntry


class LogsResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: LogsGet = from_dict(LogsGet, req.params, config=Config({DateTime: parse}, cast=[int]))

            db_session = req.context.session

            # find the correct home for the user
            home = get_home(request.label, db_session, req.context.get("user", "anonymous"))

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label, or invalid home token"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            query = db_session.query(
                Log
            ).filter(
                Log.home_id == home.id
            ).filter(
                Log.timestamp >= request.start
            )

            if request.category is not None:
                query = query.filter(Log.category == request.category)

            if request.end is not None:
                query = query.filter(Log.timestamp < request.end)

            if request.limit is not None:
                query = query.limit(request.limit)

            result: [Log] = query.all()

            response = [LogEntry(result.timestamp, result.category, result.parameters) for result in result]

            resp.content_type = falcon.MEDIA_JSON
            resp.text = json.dumps([entry.to_dict() for entry in response])
            resp.status = falcon.HTTP_OK
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
