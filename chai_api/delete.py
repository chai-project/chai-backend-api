import os
import sys

import click
import tomli

from db_definitions import Configuration as DBConfiguration, db_engine_manager, db_session_manager


def main(config: DBConfiguration, home_label: str):
    with db_engine_manager(config) as engine:
        with db_session_manager(engine) as session:
            result = session.execute("SELECT id AS homeid, netatmoid FROM home WHERE label=:label", {"label": home_label})
            if result is None:
                print(f"{home_label} not found")
                exit()

            first_result = result.fetchone()
            if first_result is None:
                print(f"{home_label} not found")
                exit()

            homeid, netatmoid = first_result
            if homeid is None or netatmoid is None:
                print(f"Result for {home_label} is invalid (homeid={homeid}, netatmoid={netatmoid})")
                exit()

            if input(f"Are you sure you want to delete {home_label} (homeid={homeid}, netatmoid={netatmoid})? (y/n): ") != "y":
                print(f"{home_label} was not deleted")
                exit()

            session.execute("DELETE FROM log WHERE homeid=:homeid", {"homeid": homeid})
            session.execute("DELETE FROM profile WHERE homeid=:homeid", {"homeid": homeid})
            session.execute("DELETE FROM schedule WHERE homeid=:homeid", {"homeid": homeid})
            session.execute("DELETE FROM setpointchange WHERE homeid=:homeid", {"homeid": homeid})
            session.execute("DELETE FROM home WHERE homeid=:homeid", {"homeid": homeid})

            session.execute("DELETE FROM netatmoreading WHERE netatmoid=:netatmoid", {"netatmoid": netatmoid})
            session.execute("DELETE FROM netatmodevice WHERE netatmoid=:netatmoid", {"netatmoid": netatmoid})

            session.commit()
            print(f"Deleted {home_label} (homeid={homeid}, netatmoid={netatmoid})")


@click.command()
@click.option("--config", default=None, help="The TOML configuration file.")
@click.option("--label", help="The label associated with the home.")
def cli(config, label):  # pylint: disable=invalid-name
    if config and not os.path.isfile(config):
        click.echo("The configuration file is not found. Please provide a valid file path.")
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
                        label
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
