# pylint: disable=line-too-long, missing-module-docstring


from __future__ import annotations

import os

import bjoern
import falcon

from chai_api.battery import BatteryResource
from chai_api.heating import HeatingResource
from chai_api.prices import PriceResource
from chai_api.electricity import CurrentResource
from chai_api.utilities import read_config, Configuration
from chai_persistence import Homes

SCRIPT_PATH: str = os.path.dirname(os.path.realpath(__file__))
config: Configuration = read_config(SCRIPT_PATH)

# start the Homes singleton
homes = Homes()

# instantiate a callable WSGI app
app = falcon.App()

# create routes to resource instances
app.add_route("/heating/mode/", HeatingResource())
app.add_route("/battery/mode/", BatteryResource())
app.add_route("/electricity/prices/", PriceResource())
app.add_route("/electricity/current/", CurrentResource())

print(f"backend server running at {config.host}:{config.port}")
bjoern.run(app, config.host, config.port, reuse_port=False)
