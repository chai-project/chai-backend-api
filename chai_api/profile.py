# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

import falcon
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response
from sqlalchemy.sql.expression import func

from chai_api.db_definitions import Profile, get_home
from chai_api.expected import ProfileGet
from chai_api.responses import ProfileEntry


class ProfileResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: ProfileGet = from_dict(ProfileGet, req.params, config=Config(cast=[int]))

            db_session = req.context.session

            # find the correct home for the user
            home = get_home(request.label, db_session, req.context.get("user", "anonymous"))

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label, or invalid home token"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            if request.profile is not None and (request.profile < 0 or request.profile > 5):
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "a profile ID is expected to be between 0 and 5"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            #  SELECT *
            #  FROM profile
            #  WHERE id IN (SELECT MAX(id) FROM profile GROUP BY profile_id)

            subquery = db_session.query(func.max(Profile.id)).filter(
                Profile.home_id == home.id
            ).group_by(Profile.profile_id).subquery()

            query = db_session.query(
                Profile
            ).filter(
                Profile.id.in_(subquery)
            )

            if request.profile is not None:
                query = query.filter(Profile.profile_id == request.profile)

            result: [Profile] = query.all()

            response = sorted([ProfileEntry(result.profile_id, result.mean2, result.mean1) for result in result],
                              key=lambda x: x.profile)

            resp.content_type = falcon.MEDIA_JSON
            resp.text = json.dumps([entry.to_dict() for entry in response])
            resp.status = falcon.HTTP_OK
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
