# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

import falcon
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response
from pendulum import DateTime, parse

from chai_api.db_definitions import Log, get_home
from chai_api.expected import LogsGet, LogsPut
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
            ).order_by(
                Log.timestamp.desc()
            ).offset(
                request.skip
            ).limit(
                request.limit
            )

            if request.category is not None:
                if "," in request.category:
                    categories = [category.strip() for category in request.category.split(",")]
                    query = query.filter(Log.category.in_(categories))
                else:
                    query = query.filter(Log.category == request.category)

            if request.end is not None:
                query = query.filter(Log.timestamp < request.end)

            result: [Log] = query.all()

            response = [LogEntry(result.timestamp, result.category, result.parameters) for result in result]

            resp.content_type = falcon.MEDIA_JSON
            resp.text = json.dumps([entry.to_dict() for entry in response])
            resp.status = falcon.HTTP_OK
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"

    def on_put(self, req: Request, resp: Response):  # noqa
        try:
            options = req.params
            options.update(req.get_media(default_when_empty=[]))  # noqa
            request: LogsPut = from_dict(LogsPut, options, config=Config({DateTime: parse}))
            db_session = req.context.session

            home = get_home(request.label, db_session, req.context.get("user", "anonymous"))

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label, or invalid home token"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            db_session.add(Log(
                home=home, timestamp=request.timestamp,
                category=request.category, parameters=request.parameters
            ))
            db_session.commit()

            resp.content_type = falcon.MEDIA_JSON
            resp.status = falcon.HTTP_OK
        except (DaciteError, ValueError) as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
