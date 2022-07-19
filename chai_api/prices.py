# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

import falcon
import pendulum
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response
from pendulum import DateTime, from_timestamp

from chai_api.expected import PricesGet
from chai_api.responses import Rate


class PriceResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: PricesGet = from_dict(PricesGet, req.params, config=Config({DateTime: from_timestamp}))

            if request.end and request.end <= request.start:
                resp.content_type = falcon.MEDIA_TEXT
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.text = "the end date should not be before the start date"
                return
            if request.limit is not None and request.limit < 1:
                resp.content_type = falcon.MEDIA_TEXT
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.text = "the limit should be 1 or more"
                return

            entries = [
                Rate(start=pendulum.datetime(2019, 5, 12, 15, 30), end=pendulum.datetime(2019, 5, 12, 16, 0),
                     rate=13.17, predicted=False),
                Rate(start=pendulum.datetime(2019, 5, 12, 16, 0), end=pendulum.datetime(2019, 5, 12, 16, 30),
                     rate=7.82, predicted=False),
            ]

            resp.content_type = falcon.MEDIA_JSON
            resp.status = falcon.HTTP_OK
            resp.text = json.dumps([entry.to_dict() for entry in entries])
        except DaciteError:
            resp.status = falcon.HTTP_BAD_REQUEST
