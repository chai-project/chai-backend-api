# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring

import shelve

import falcon
import pendulum
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response

from chai_api.energy_loop import PriceAttack
from chai_api.expected import AttackPut


class AttackResource:
    shelve_db: str = ""

    def __init__(self, shelve_location):
        self.shelve_db = shelve_location

    def on_put(self, req: Request, resp: Response):  # noqa
        try:
            options = req.params
            options.update(req.get_media(default_when_empty=[]))  # noqa
            request: AttackPut = from_dict(AttackPut, options, config=Config(cast=[int, float]))

            if request.duration <= 0:
                resp.content_type = falcon.MEDIA_TEXT
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.text = "the duration should be strictly positive"
                return

            if request.duration % 30 != 0:
                resp.content_type = falcon.MEDIA_TEXT
                resp.status = falcon.HTTP_BAD_REQUEST
                resp.text = "the duration should be a multiple of 30"
                return

            now = pendulum.now().set(second=0, microsecond=0)
            next_slot_start = now.add(minutes=30 - now.minute % 30)
            attack_end = next_slot_start.add(minutes=request.duration)

            with shelve.open(self.shelve_db) as db:
                db["attack"] = PriceAttack(request.modifier, next_slot_start, attack_end)
                print(db["attack"])

            resp.status = falcon.HTTP_CREATED
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
