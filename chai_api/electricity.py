# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

import os

import falcon
import ujson as json
from chai_persistence import Homes, EfergyError
from dacite import from_dict, DaciteError
from falcon import Request, Response

from chai_api.expected import CurrentGet
from chai_api.responses import Current
from chai_api.utilities import bearer_authentication, read_config, Configuration

SCRIPT_PATH: str = os.path.dirname(os.path.realpath(__file__))
config: Configuration = read_config(SCRIPT_PATH)


class CurrentResource:
    @bearer_authentication(config.secret)
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: CurrentGet = from_dict(CurrentGet, req.params)
            try:
                current = Homes().get_power(request.label)
                if current is None:
                    resp.content_type = falcon.MEDIA_TEXT
                    resp.status = falcon.HTTP_BAD_REQUEST
                    resp.text = "unknown home label"
                    return
                resp.content_type = falcon.MEDIA_JSON
                resp.text = json.dumps(Current(current))
                resp.status = falcon.HTTP_OK
            except EfergyError:
                resp.status = falcon.HTTP_INTERNAL_SERVER_ERROR
        except (DaciteError, ValueError):
            resp.status = falcon.HTTP_BAD_REQUEST
