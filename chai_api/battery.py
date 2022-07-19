# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

from enum import Enum
import falcon
from falcon import Request, Response
import ujson as json
from dacite import from_dict, DaciteError, Config

from chai_api.expected import BatteryGet, BatteryPut
from chai_api.responses import BatteryMode, BatteryModeOption, BatteryChargeStatus


class BatteryResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: BatteryGet = from_dict(BatteryGet, req.params)

            resp.content_type = falcon.MEDIA_JSON
            # TODO: hard-coded mode
            # TODO: hard-coded status
            # TODO: hard-coded percentage
            resp.text = json.dumps(BatteryMode(BatteryModeOption.AUTO, BatteryChargeStatus.CHARGE, 71))
            resp.status = falcon.HTTP_OK
        except DaciteError:
            resp.status = falcon.HTTP_BAD_REQUEST

    def on_put(self, req: Request, resp: Response):  # noqa
        try:
            request: BatteryPut = from_dict(BatteryPut, req.params, config=Config(cast=[Enum]))
            # TODO: implement PUT /battery/mode

        except (DaciteError, ValueError):
            resp.status = falcon.HTTP_BAD_REQUEST
