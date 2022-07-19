# pylint: disable=line-too-long, missing-module-docstring


from __future__ import annotations

import os

import falcon
from falcon import App
from falcon_auth import FalconAuthMiddleware, TokenAuthBackend
import click
from typing import Optional

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
from chai_persistence import Homes

SCRIPT_PATH: str = os.path.dirname(os.path.realpath(__file__))
WD_PATH: str = os.getcwd()


class Sink:
    def on_get(self, req: Request, resp: Response):  # noqa
        resp.content_type = falcon.MEDIA_TEXT
        resp.status = falcon.HTTP_NOT_FOUND
        resp.text = "unknown API endpoint - make sure you did not omit the trailing slash"


@click.command()
@click.option("--host", default="0.0.0.0", help="The host where to launch the API server.")
@click.option("--port", default=8080, help="The port where to launch the API server.")
@click.option("--bearer_file", default=None, help="The file containing the (single line) bearer token.")
def cli(host, port, bearer_file):
    # verify that the bearer file exists
    if bearer_file and not os.path.isfile(bearer_file):
        click.echo("Bearer file not found. Please provide a valid file path.")
        exit(0)

    bearer = None
    if bearer_file:
        # use the contents of the file as the bearer token
        with open(bearer_file) as f:
            bearer = f.read().strip()
    main(host, port, bearer)


def main(host: str = "0.0.0.0", port: int = 8080, bearer: Optional[str] = None):
    # start the Homes singleton
    homes = Homes()

    # instantiate a callable WSGI app
    # TODO: handle CORS in Falcon, or through reverse proxy?
    token_auth = TokenAuthBackend(user_loader=lambda x: True if x == bearer or bearer is None else None,
                                  auth_header_prefix="Bearer")
    auth_middleware = FalconAuthMiddleware(token_auth)
    app = falcon.App(middleware=[auth_middleware])

    # create routes to resource instances
    app.add_route("/heating/mode/", HeatingResource())
    app.add_route("/battery/mode/", BatteryResource())
    app.add_route("/electricity/prices/", PriceResource())
    app.add_route("/electricity/current/", CurrentResource())
    app.add_sink(Sink().on_get)  # route all unknown traffic to the sink

    print(f"backend server running at {host}:{port}")

    run_server(app, host, port)


if __name__ == "__main__":
    cli()
