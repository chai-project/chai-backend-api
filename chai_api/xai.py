# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

from typing import List, Optional

import falcon
import pendulum
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response

from chai_api.db_definitions import Log, Profile, SetpointChange, get_home
from chai_api.expected import XAIGet, ProfileResetGet
from chai_api.responses import XAIRegion, XAIBand, XAIScatter, XAIScatterEntry


class ConfigurationProfile:
    mean1: float = 0.0
    mean2: float = 0.0
    variance1: float = 0.0
    variance2: float = 0.0
    noiseprecision: float = 0.0  # noqa
    correlation1: float = 0.0
    correlation2: float = 0.0
    region_angle: float = 0.0
    region_width: float = 0.0
    region_height: float = 0.0
    prediction_banded = List[List[float]]


class XAIProfileResource:
    profile: Optional[List[ConfigurationProfile]]

    def __init__(self, profiles: List[ConfigurationProfile]):
        self.profiles = profiles

    def get_profile(self, req: Request, resp: Response, parameters: XAIGet, all: bool = False) -> (
    bool, Optional[Profile]):  # noqa
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
                Profile.setpointChange.has(SetpointChange.hidden.is_(False))
            ).filter(
                Profile.id >= subquery.as_scalar()
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

            if success and result is not None:
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
                    if len(self.profiles) >= parameters.profile:
                        default_profile = self.profiles[parameters.profile - 1]
                        response = XAIRegion(
                            profile=parameters.profile, centre_x=default_profile.mean1, centre_y=default_profile.mean2,
                            angle=default_profile.region_angle, width=default_profile.region_width,
                            height=default_profile.region_height, skip=parameters.skip
                        )
                        resp.text = json.dumps(response.to_dict())
                        resp.status = falcon.HTTP_PARTIAL_CONTENT
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

            if success and result is not None:
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
                    if len(self.profiles) >= parameters.profile:
                        default_profile = self.profiles[parameters.profile - 1]
                        band: List[List[float]] = list(zip(*default_profile.prediction_banded))  # noqa
                        response = XAIBand(
                            lower_confidence=band[0], prediction=band[1], upper_confidence=band[2], skip=parameters.skip
                        )
                        resp.text = json.dumps(response.to_dict())
                        resp.status = falcon.HTTP_PARTIAL_CONTENT
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

            if success and results is not None:
                entries = [
                    XAIScatterEntry(result.setpointChange.price, result.setpointChange.temperature)
                    for result in results if result.setpointChange and result.setpointChange.temperature is not None
                ]
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


class ProfileResetResource:
    profile: Optional[List[ConfigurationProfile]]

    def __init__(self, profiles: List[ConfigurationProfile]):
        self.profiles = profiles

    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            parameters: ProfileResetGet = from_dict(ProfileResetGet, req.params, config=Config(cast=[int]))

            if parameters.profile is not None and (parameters.profile < 1 or parameters.profile > 5):
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "invalid value for profile, expected a value between 1 and 5 (inclusive)"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            if parameters.profile is not None and len(self.profiles) < parameters.profile:
                resp.content_type = falcon.MEDIA_TEXT
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.text = f"the profile {parameters.profile} cannot be reset as its default values are not known"
                return

            db_session = req.context.session

            # find the correct home for the user
            home = get_home(parameters.label, db_session, req.context.get("user", "anonymous"))

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label, or invalid home token"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            # assume that [1, 2, 3, 4, 5] is the set of profiles, which is an assumption that is already hardcoded
            for profile_id in range(1, 6) if parameters.profile is None else [parameters.profile]:
                default_profile = self.profiles[profile_id - 1]

                new_profile = Profile(
                    profile_id=profile_id, home_id=home.id,
                    mean1=default_profile.mean1, mean2=default_profile.mean2,
                    variance1=default_profile.variance1, variance2=default_profile.variance2,
                    noiseprecision=default_profile.noiseprecision,
                    correlation1=default_profile.correlation1, correlation2=default_profile.correlation2
                )
                db_session.add(new_profile)

                if not parameters.hidden:
                    db_session.add(Log(
                        home_id=home.id,
                        timestamp=pendulum.now(),
                        category="PROFILE_RESET",
                        parameters=[profile_id]
                    ))

            db_session.commit()
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
        except ValueError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters has an invalid value:\n{err}"
