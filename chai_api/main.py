# pylint: disable=line-too-long, missing-module-docstring


from __future__ import annotations

import os

import falcon
from falcon import App

try:
    from bjoern import run as run_server
except (ImportError, ModuleNotFoundError):
    from cheroot.wsgi import Server as HTTPServer

    def run_server(app: App, host: str, port: int):
        HTTPServer((host, port), app).start()


from chai_api.battery import BatteryResource
from chai_api.heating import HeatingResource
from chai_api.prices import PriceResource
from chai_api.electricity import CurrentResource
from chai_api.utilities import read_config, Configuration
from chai_persistence import Homes

SCRIPT_PATH: str = os.path.dirname(os.path.realpath(__file__))
config: Configuration = read_config(SCRIPT_PATH)


class Sink:
    def on_get(self, req: Request, resp: Response):  # noqa
        resp.content_type = falcon.MEDIA_TEXT
        resp.status = falcon.HTTP_NOT_FOUND
        resp.text = "unknown API endpoint - make sure you did not omit the trailing slash"


# start the Homes singleton
homes = Homes()

# instantiate a callable WSGI app
# TODO: CORS support should *only* be enabled until the SSL certificates are sorted out
app = falcon.App(middleware=falcon.CORSMiddleware(allow_origins="*", allow_credentials="*"))

# create routes to resource instances
app.add_route("/heating/mode/", HeatingResource())
app.add_route("/battery/mode/", BatteryResource())
app.add_route("/electricity/prices/", PriceResource())
app.add_route("/electricity/current/", CurrentResource())
app.add_sink(Sink().on_get)  # route all unknown traffic to the sink

print(f"backend server running at {config.host}:{config.port}")

run_server(app, config.host, config.port)
