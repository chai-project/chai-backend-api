# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

from typing import List, Optional

import falcon
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response

from chai_api.db_definitions import Profile, get_home
from chai_api.expected import XAIGet
from chai_api.responses import XAIRegion, XAIBand, XAIScatter, XAIScatterEntry


class XAIProfileResource:
    def get_profile(self, req: Request, resp: Response, parameters: XAIGet, all: bool = False) -> (bool, Optional[Profile]):  # noqa
        try:
            if parameters.profile < 1 or parameters.profile > 5:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "invalid value for profile, expected a value between 1 and 5 (inclusive)"
                resp.status = falcon.HTTP_BAD_REQUEST
                return False, None

            db_session = req.context.session

            # find the correct home for the user
            home = get_home(parameters.label, db_session, req.context.get("user", "anonymous"))

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label, or invalid home token"
                resp.status = falcon.HTTP_BAD_REQUEST
                return False, None

            subquery = db_session.query(
                Profile.id
            ).filter(
                Profile.home_id == home.id
            ).filter(
                Profile.profile_id == parameters.profile
            ).filter(
                Profile.confidence_region.is_(None)
            ).order_by(
                Profile.id.desc()
            ).limit(1)

            query = db_session.query(
                Profile
            ).filter(
                Profile.id >= subquery
            ).filter(
                Profile.home_id == home.id
            ).filter(
                Profile.profile_id == parameters.profile
            ).order_by(
                Profile.id.desc()
            ).offset(parameters.skip)

            if all:
                return True, query.all()
            return True, query.first()
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
            return False, None
        except ValueError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters has an invalid value:\n{err}"
            return False, None


class XAIRegionResource(XAIProfileResource):
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            parameters: XAIGet = from_dict(XAIGet, req.params, config=Config(cast=[int]))
            (success, result) = self.get_profile(req, resp, parameters)

            if success:
                response = None
                if result and result.confidence_region and len(result.confidence_region) == 3:
                    response = XAIRegion(
                        profile=result.profile_id, centre_x=result.mean1, centre_y=result.mean2,
                        angle=result.confidence_region[0], width=result.confidence_region[1],
                        height=result.confidence_region[2], skip=parameters.skip
                    )

                resp.content_type = falcon.MEDIA_JSON
                if response:
                    resp.text = json.dumps(response.to_dict())
                    resp.status = falcon.HTTP_OK
                else:
                    resp.status = falcon.HTTP_NO_CONTENT
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
        except ValueError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters has an invalid value:\n{err}"


class XAIBandResource(XAIProfileResource):
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            parameters: XAIGet = from_dict(XAIGet, req.params, config=Config(cast=[int]))
            (success, result) = self.get_profile(req, resp, parameters)

            if success:
                response = None
                if result and result.prediction_banded and len(result.prediction_banded) == 36:
                    band: List[List[float]] = list(zip(*result.prediction_banded))  # noqa
                    response = XAIBand(
                        lower_confidence=band[0], prediction=band[1], upper_confidence=band[2], skip=parameters.skip
                    )

                resp.content_type = falcon.MEDIA_JSON
                if response:
                    resp.text = json.dumps(response.to_dict())
                    resp.status = falcon.HTTP_OK
                else:
                    resp.status = falcon.HTTP_NO_CONTENT
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
        except ValueError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters has an invalid value:\n{err}"


class XAIScatterResource(XAIProfileResource):
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            parameters: XAIGet = from_dict(XAIGet, req.params, config=Config(cast=[int]))
            (success, results) = self.get_profile(req, resp, parameters, all=True)

            if success:
                response = None
                if results:
                    entries = [
                        XAIScatterEntry(result.setpointChange.price, result.setpointChange.temperature)
                        for result in results if result.setpointChange and result.setpointChange.temperature is not None
                    ]
                    print(entries)
                    response = XAIScatter(entries, len(entries))
                resp.content_type = falcon.MEDIA_JSON
                if response:
                    resp.text = json.dumps(response.to_dict())
                    resp.status = falcon.HTTP_OK
                else:
                    resp.status = falcon.HTTP_NO_CONTENT
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
        except ValueError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters has an invalid value:\n{err}"
