# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, unused-argument, missing-function-docstring
# pylint: disable=too-few-public-methods, too-many-locals, too-many-arguments, too-many-branches, too-many-statements

from __future__ import annotations

import os
import sys
from typing import Optional

import click
import falcon
import tomli
from falcon import App
from falcon_auth import FalconAuthMiddleware, TokenAuthBackend as TokenAuth
from falcon_sqla import Manager as SessionManager

try:
    from bjoern import run as run_server
except (ImportError, ModuleNotFoundError):
    from cheroot.wsgi import Server as HTTPServer


    def run_server(app: App, host: str, port: int):  # pylint: disable=missing-function-docstring
        HTTPServer((host, port), app).start()

from chai_api.db_definitions import db_engine, Configuration as DBConfiguration
from chai_api.heating import HeatingResource, ValveResource
from chai_api.history import HistoryResource
from chai_api.logs import LogsResource
from chai_api.prices import PriceResource
from chai_api.schedule import ScheduleResource
from chai_api.profile import ProfileResource
from chai_api.xai import XAIRegionResource, XAIBandResource

SCRIPT_PATH: str = os.path.dirname(os.path.realpath(__file__))
WD_PATH: str = os.getcwd()


class Configuration:  # pylint: disable=too-few-public-methods, too-many-instance-attributes
    """ Configuration used by the API server. """
    host: str = "0.0.0.0"
    port: int = 8080
    bearer: Optional[str] = None  # when None this value should be ignored, a.k.a. open access
    db_server: str = "127.0.0.1"
    db_name: str = "chai"
    db_username: str = ""
    db_password: str = ""
    api_debug: bool = False
    db_debug: bool = False

    def __str__(self):
        return (f"Configuration(host={self.host}, port={self.port}, bearer={self.bearer}, db_server={self.db_server}, "
                f"db_name={self.db_name}, db_username={self.db_username}, db_password={self.db_password}, "
                f"api_debug={self.api_debug}, db_debug={self.db_debug})")


class Sink:  # pylint: disable=missing-class-docstring, missing-function-docstring, undefined-variable
    def on_get(self, req: Request, resp: Response):  # noqa
        resp.content_type = falcon.MEDIA_TEXT
        resp.status = falcon.HTTP_NOT_FOUND
        resp.text = "unknown API endpoint - make sure you did not omit the trailing slash"


@click.command()
@click.option("--config", default=None, help="The TOML configuration file.")
@click.option("--host", default=None, help="The host where to launch the API server, defaults to 0.0.0.0.")
@click.option("--port", default=None, help="The port where to launch the API server, defaults to 8080.")
@click.option("--bearer_file", default=None, help="The file containing the (single line) bearer token.")
@click.option("--dbserver", default=None, help="The server location of the PostgreSQL database, defaults to 127.0.0.1.")
@click.option("--db", default=None, help="The name of the database to access, defaults to chai.")
@click.option("--username", default=None, help="The username to access the database.")
@click.option("--dbpass_file", default=None, help="The file containing the (single line) password for database access.")
@click.option('--debug', is_flag=True, help="Provides debug output for the API server and the database when present.")
def cli(config, host, port, bearer_file, dbserver, db, username, dbpass_file, debug):  # pylint: disable=invalid-name
    settings = Configuration()

    if config and not os.path.isfile(config):
        click.echo("The configuration file is not found. Please provide a valid file path.")
        sys.exit(0)

    if config:
        with open(config, "rb") as file:
            try:
                toml = tomli.load(file)
                # apply the generic debug option to both the API server and the database
                all_debug = bool(toml.get("debug", "False"))
                settings.api_debug = all_debug
                settings.db_debug = all_debug

                if toml_server := toml["server"]:
                    settings.host = str(toml_server.get("host", settings.host))
                    settings.port = int(toml_server.get("port", settings.port))
                    settings.bearer = toml_server.get("bearer", settings.bearer)
                    settings.api_debug = bool(toml_server.get("debug", settings.api_debug))
                if toml_db := toml["database"]:
                    settings.db_server = str(toml_db.get("server", settings.db_server))
                    settings.db_name = str(toml_db.get("name", settings.db_name))
                    settings.db_username = str(toml_db.get("user", settings.db_username))
                    settings.db_password = str(toml_db.get("pass", settings.db_password))
                    settings.db_debug = bool(toml_db.get("debug", settings.db_debug))
            except tomli.TOMLDecodeError:
                click.echo("The configuration file is not valid and cannot be parsed.")
                sys.exit(0)

    # some entries may not be present in the TOML file, or they may be overridden by explicit CLI arguments

    # [overridden/supplemental server settings]
    if host is not None:
        settings.host = host

    if port is not None:
        settings.port = port

    # verify that the bearer file exists
    if bearer_file and not os.path.isfile(bearer_file):
        click.echo("Bearer file not found. Please provide a valid file path.")
        sys.exit(0)

    if bearer_file:
        # use the contents of the file as the bearer token
        with open(bearer_file, encoding="utf-8") as file:
            bearer = file.read().strip()
            settings.bearer = bearer

    # [overridden/supplemental database settings]
    if dbserver is not None:
        settings.db_server = dbserver

    if db is not None:
        settings.db_name = db

    if username is not None:
        settings.db_username = username

    # verify that the password file exists
    if dbpass_file and not os.path.isfile(dbpass_file):
        click.echo("Password file not found. Please provide a valid file path.")
        sys.exit(0)

    if dbpass_file:
        # use the contents of the file as the bearer token
        with open(dbpass_file, encoding="utf-8") as file:
            password = file.read().strip()
            settings.db_password = password

    if debug is True:
        settings.api_debug = True
        settings.db_debug = True

    main(settings)


def main(settings: Configuration):
    """
    Main entry point for the API server.
    :param settings: The configuration settings to use.
    """
    #  create the token authorisation middleware
    bearer = settings.bearer

    def user_loader(token: str) -> Optional[str]:
        """
        The user loader function for the token authorisation middleware.
        :param token: The token to check.
        :return: The user token if given ("anonymous" otherwise) if the bearer is valid, or None.
        """
        parts = token.split(",")
        parts = [part.strip() for part in parts]
        # bearer expected, the user token must be provided as bearer,user_token
        if len(parts) == 1 and parts[0] == bearer:
            return "anonymous"
        elif len(parts) == 2 and parts[0] == bearer:
            return parts[1]
        else:
            return None

    auth = TokenAuth(user_loader=user_loader, auth_header_prefix="Bearer")
    auth_middleware = FalconAuthMiddleware(auth, exempt_routes=[
        "/electricity/prices/",
    ])

    #  create the database session middleware
    db_config = DBConfiguration(username=settings.db_username, password=settings.db_password,
                                server=settings.db_server, database=settings.db_name,
                                enable_debugging=settings.db_debug)
    engine = db_engine(db_config)
    session_middleware = SessionManager(engine).middleware

    # instantiate a callable WSGI app
    app = falcon.App(middleware=[auth_middleware, session_middleware] if bearer is not None else [session_middleware])

    # create routes to resource instances
    app.add_route("/heating/mode/", HeatingResource())
    app.add_route("/heating/valve/", ValveResource())
    app.add_route("/heating/profile/", ProfileResource())
    app.add_route("/heating/historic/", HistoryResource())
    app.add_route("/electricity/prices/", PriceResource())
    app.add_route("/xai/region/", XAIRegionResource())
    app.add_route("/xai/band/", XAIBandResource())
    app.add_route("/logs/", LogsResource())
    app.add_route("/schedule/", ScheduleResource())
    app.add_sink(Sink().on_get)  # route all unknown traffic to the sink

    print(f"backend server running at {settings.host}:{settings.port}")

    run_server(app, settings.host, settings.port)


if __name__ == "__main__":
    # cli()
    # for testing in IDE:
    cli.callback(
        "/Users/kimbauters/Library/Mobile Documents/com~apple~CloudDocs/CHAI/Programming/Python/CHAI_api/settings.toml",
        None, None, None, None, None, None, None, False
    )
