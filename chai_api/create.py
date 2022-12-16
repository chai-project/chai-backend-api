import os
import sys

import click
import pendulum
import requests
import tomli

from db_definitions import Configuration as DBConfiguration, db_engine_manager, db_session_manager, Log
from utilities import create_user_token


def main(config: DBConfiguration, refresh_token: str, home_label: str, bearer: str):
    auth_token = create_user_token()

    with db_engine_manager(config) as engine:
        with db_session_manager(engine) as session:
            result = session.execute(
                """
                INSERT INTO 
                  netatmodevice(refreshtoken) 
                VALUES (:refresh)
                RETURNING id
                """,
                {
                    "refresh": refresh_token
                }
            )

            device_id = result.fetchone()[0]
            print(f"created Netatmo device with id {device_id}")

            result = session.execute(
                """
                INSERT INTO 
                  home (label, revision, netatmoid, token) 
                VALUES (:label, :revision, :netatmoid, :token)
                RETURNING id
                """,
                {
                    "label": home_label, "revision": pendulum.now().start_of("day").isoformat(),
                    "netatmoid": device_id, "token": auth_token
                }
            )

            home_id = result.fetchone()[0]
            print(f"created home with id {home_id}")
            print()
            print(f"==============================================")
            print(f"=== access token: {auth_token} ===")
            print(f"==============================================")
            print()

            weekday_schedule = '{"0":"1","26":"2","38":"3","72":"4","88":"1"}'
            weekend_schedule = '{"0":"1","32":"2","44":"5","72":"4","88":"1"}'
            for day in [1, 2, 4, 8, 16, 32, 64]:
                session.execute(
                    """
                    INSERT INTO 
                      schedule (homeid, revision, day, schedule) 
                    VALUES (:homeid, :revision, :day, :schedule)
                    """, {
                        "homeid": home_id, "revision": pendulum.now().start_of("day").isoformat(),
                        "day": day, "schedule": weekend_schedule if day in [32, 64] else weekday_schedule
                    }
                )

            print("created schedules")

            session.add(Log(
                home_id=home_id,
                timestamp=pendulum.now(),
                category="WELCOME",
                parameters=[home_label]
            ))

            # call the API to make sure the profiles for this new user are set up correctly
            session.commit()
            for i in range(5):
                requests.get(
                    "http://localhost:8080/profile/reset/",
                    params={"label": home_label, "profile": i + 1, "hidden": True},
                    headers={"Authorization": f"Bearer {bearer},{auth_token}"}
                )

            print("reset profiles")


@click.command()
@click.option("--config", default=None, help="The TOML configuration file.")
@click.option("--refreshtoken", help="The Netatmo device access refresh token.")
@click.option("--label", help="The label associated with the home.")
def cli(config, refreshtoken, label):  # pylint: disable=invalid-name
    if config and not os.path.isfile(config):
        click.echo("The configuration file is not found. Please provide a valid file path.")
        sys.exit(0)

    if not refreshtoken:
        click.echo("The Netatmo refresh token should be provided and should not be empty.")
        sys.exit(0)

    if not label:
        click.echo("The label for the home should be provided and should not be empty.")
        sys.exit(0)

    if config:
        with open(config, "rb") as file:
            try:
                toml = tomli.load(file)
                if toml_db := toml["database"]:
                    db_server = str(toml_db["server"])
                    db_name = str(toml_db["dbname"])
                    db_username = str(toml_db["user"])
                    db_password = str(toml_db["pass"])
                    db_debug = bool(toml_db["debug"])

                    main(
                        DBConfiguration(db_server, db_username, db_password, db_name, db_debug),
                        refreshtoken, label, str(toml["server"]["bearer"])
                    )
            except tomli.TOMLDecodeError:
                click.echo("The configuration file is not valid and cannot be parsed.")
                sys.exit(0)
            except KeyError as err:
                click.echo(f"The configuration file is missing some expected values: {err}.")
                sys.exit(0)
            except AssertionError:
                click.echo("Make sure the prediction_banded list for each profile has 36 entries, each of 3 elements.")
                sys.exit(0)


if __name__ == "__main__":
    cli()
