# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring
import math

import falcon
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response
from pendulum import DateTime, parse

from chai_api.expected import PricesGet
from chai_api.energy_loop import get_energy_values, ElectricityPrice


class PriceResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: PricesGet = from_dict(PricesGet, req.params, config=Config({DateTime: parse}, cast=[int]))

            if request.end is not None and request.default_start:
                resp.content_type = falcon.MEDIA_TEXT
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.text = "when providing an end date you should also provide a start date"
                return
            if request.end is not None and request.end <= request.start:
                resp.content_type = falcon.MEDIA_TEXT
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.text = "the end date should not be before the start date"
                return
            if request.limit is not None and request.limit < 1:
                resp.content_type = falcon.MEDIA_TEXT
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.text = "the limit should be 1 or more"
                return

            if request.end is None:
                if request.limit is None:
                    request.end = request.start.add(days=1)
                else:
                    request.end = request.start.add(days=math.ceil(request.limit / 46))

            entries: [ElectricityPrice] = get_energy_values(request.start, request.end, request.limit)

            resp.content_type = falcon.MEDIA_JSON
            resp.status = falcon.HTTP_OK
            resp.text = json.dumps([entry.to_dict() for entry in entries])
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
