# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring
# pylint: disable=singleton-comparison

import falcon
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response
from sqlalchemy import and_
from sqlalchemy.orm import aliased

from chai_api.db_definitions import get_home, Schedule
from chai_api.expected import ScheduleGet
from chai_api.responses import ScheduleEntry


class ScheduleResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: ScheduleGet = from_dict(ScheduleGet, req.params, config=Config(cast=[int]))
            db_session = req.context.session

            if request.daymask <= 0 or request.daymask > 127:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "daymask must be a value in the range [1, 127]"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            home = get_home(request.label, db_session)

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            schedule_alias = aliased(Schedule)
            schedules = db_session.query(
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
                Schedule.day.op('&')(request.daymask) != 0
            ).all()

            response = []

            for day in [1, 2, 4, 8, 16, 32, 64]:
                if day & request.daymask == day:
                    match = next(filter(lambda schedule: schedule.day == day, schedules), None)  # pylint: disable=W0640
                    if match:
                        response.append(ScheduleEntry(day, match.schedule))

            resp.content_type = falcon.MEDIA_JSON
            resp.text = json.dumps([entry.to_dict() for entry in response])
            resp.status = falcon.HTTP_OK
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"

    def on_put(self, req: Request, resp: Response):  # noqa
        # MUST be split up in day parts
        pass
