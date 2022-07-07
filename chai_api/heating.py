# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

import os
from enum import Enum

import falcon
import ujson as json
from chai_persistence import Homes, DeviceType, NetatmoError
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response

from chai_api.expected import HeatingGet, HeatingPut
from chai_api.responses import HeatingMode, HeatingModeOption, ValveStatus
from chai_api.utilities import bearer_authentication, read_config, Configuration

SCRIPT_PATH: str = os.path.dirname(os.path.realpath(__file__))
config: Configuration = read_config(SCRIPT_PATH)


class HeatingResource:
    @bearer_authentication(config.secret)
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: HeatingGet = from_dict(HeatingGet, req.params)
            try:
                temperature = Homes().get_temperature(request.label, DeviceType.VALVE)
                valve = Homes().get_valve_status(request.label)
                if temperature is None:
                    resp.content_type = falcon.MEDIA_TEXT
                    resp.text = "unknown home label"
                    resp.status = falcon.HTTP_BAD_REQUEST
                    return
                resp.content_type = falcon.MEDIA_JSON
                # TODO: hard-coded mode
                # TODO: hard-coded target
                resp.text = json.dumps(HeatingMode(temperature, HeatingModeOption.AUTO, valve, target=25).to_dict())
                resp.status = falcon.HTTP_OK
            except NetatmoError:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unable to retrieve information from the device"
                resp.status = falcon.HTTP_INTERNAL_SERVER_ERROR
        except DaciteError:
            resp.content_type = falcon.MEDIA_TEXT
            if req.params:
                params = ",".join("=".join((key,val)) for (key,val) in req.params.items())
                resp.text = f"the request is not understood; received parameters {params}"
            else:
                resp.text = f"the request is not understood; expected parameters but none given"
            resp.status = falcon.HTTP_BAD_REQUEST

    @bearer_authentication(config.secret)
    def on_put(self, req: Request, resp: Response):  # noqa
        try:
            request: HeatingPut = from_dict(HeatingPut, req.params, config=Config(cast=[Enum]))

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
    @bearer_authentication(config.secret)
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: HeatingGet = from_dict(HeatingGet, req.params)
            try:
                resp.content_type = falcon.MEDIA_JSON
                status = Homes().get_valve_status(request.label)
                resp.text = json.dumps(ValveStatus(open=status).to_dict())
                resp.status = falcon.HTTP_OK
            except NetatmoError:
                resp.status = falcon.HTTP_INTERNAL_SERVER_ERROR
        except DaciteError:
            resp.status = falcon.HTTP_BAD_REQUEST
