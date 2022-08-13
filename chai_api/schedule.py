# pylint: disable=line-too-long, missing-module-docstring
# pylint: disable=no-member, c-extension-no-member, too-few-public-methods
# pylint: disable=missing-class-docstring, missing-function-docstring
# pylint: disable=singleton-comparison

import math

import falcon
import pendulum
import ujson as json
from dacite import from_dict, DaciteError, Config
from falcon import Request, Response
from sqlalchemy import and_
from sqlalchemy.orm import aliased

from chai_api.db_definitions import get_home, Schedule
from chai_api.expected import ScheduleGet
from chai_api.responses import ScheduleEntry


class ScheduleResource:
    def on_get(self, req: Request, resp: Response):  # noqa
        try:
            request: ScheduleGet = from_dict(ScheduleGet, req.params, config=Config(cast=[int]))
            db_session = req.context.session

            if request.daymask <= 0 or request.daymask > 127:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "daymask must be a value in the range [1, 127]"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            home = get_home(request.label, db_session)

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            schedule_alias = aliased(Schedule)
            schedules = db_session.query(
                Schedule
            ).outerjoin(
                schedule_alias, and_(
                    Schedule.home_id == schedule_alias.home_id,
                    Schedule.revision < schedule_alias.revision,
                    Schedule.day == schedule_alias.day)
            ).filter(
                schedule_alias.revision == None  # noqa: E711
            ).filter(
                Schedule.home_id == home.id
            ).filter(
                Schedule.day.op('&')(request.daymask) != 0
            ).all()

            response = []

            for day in [1, 2, 4, 8, 16, 32, 64]:
                if day & request.daymask == day:
                    match = next(filter(lambda schedule: schedule.day == day, schedules), None)  # pylint: disable=W0640
                    if match:
                        response.append(ScheduleEntry(day, match.schedule))

            resp.content_type = falcon.MEDIA_JSON
            resp.text = json.dumps([entry.to_dict() for entry in response])
            resp.status = falcon.HTTP_OK
        except DaciteError as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"

    def on_put(self, req: Request, resp: Response):  # noqa
        try:
            request: ScheduleGet = from_dict(ScheduleGet, req.params, config=Config(cast=[int]))
            db_session = req.context.session

            if request.daymask <= 0 or request.daymask > 127:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "daymask must be a value in the range [1, 127]"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            home = get_home(request.label, db_session)

            if home is None:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "unknown home label"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            # verify that the schedule in the body is valid
            schedule = req.media

            if not isinstance(schedule, list) or len(schedule) < 1:
                resp.content_type = falcon.MEDIA_TEXT
                resp.text = "the schedule should be given as a list of entries, with at least one entry"
                resp.status = falcon.HTTP_BAD_REQUEST
                return

            for entry in schedule:
                if not isinstance(entry, dict):
                    resp.content_type = falcon.MEDIA_TEXT
                    resp.text = "an entry should be given as a dictionary of the format '{slot: profile}'"
                    resp.status = falcon.HTTP_BAD_REQUEST
                    return

                if len(entry) != 1:
                    resp.content_type = falcon.MEDIA_TEXT
                    resp.text = "an entry should be given as a dictionary of the format '{slot: profile}'"
                    resp.status = falcon.HTTP_BAD_REQUEST
                    return

                for (key, value) in entry.items():
                    try:
                        key_as_int = int(key)
                        if not 0 <= key_as_int <= 93:
                            resp.content_type = falcon.MEDIA_TEXT
                            resp.text = f" the entry '{{{key}, {value}}}' has an invalid time slot value of {key}"
                            resp.status = falcon.HTTP_BAD_REQUEST
                            return
                        value_as_int = int(value)
                        if not 1 <= value_as_int <= 5:
                            resp.content_type = falcon.MEDIA_TEXT
                            resp.text = f" the entry '{{{key}, {value}}}' has an invalid profile value of {value}"
                            resp.status = falcon.HTTP_BAD_REQUEST
                            return
                    except ValueError:
                        resp.content_type = falcon.MEDIA_TEXT
                        resp.text = "the key and value of each dictionary should be integers or equivalent to integers"
                        resp.status = falcon.HTTP_BAD_REQUEST
                        return

            # everything is checked
            # convert it into a more suitable shape for our needs
            cleaned_schedule = []
            for entry in schedule:
                for (key, value) in entry.items():
                    cleaned_schedule.append((int(key), int(value)))

            # sort these entries based on the time slot
            cleaned_schedule.sort(key=lambda x: x[0])

            # every slot in the database must guarantee that a daily schedule has a first entry for time slot 0
            # this can come from a previous entry, either from the database or from the schedule that was PUT

            # fetch the current schedule from the DB so we can enrich the newly PUT schedule
            schedule_alias = aliased(Schedule)
            existing_schedules = db_session.query(
                Schedule
            ).outerjoin(
                schedule_alias, and_(
                    Schedule.home_id == schedule_alias.home_id,
                    Schedule.revision < schedule_alias.revision,
                    Schedule.day == schedule_alias.day)
            ).filter(
                schedule_alias.revision == None  # noqa: E711
            ).filter(
                Schedule.home_id == home.id
            ).all()

            # prepare all the existing schedules in a nice looping structure
            day_schedules = [None] * 8
            for schedule in existing_schedules:
                print(schedule.day, math.log2(schedule.day))
                day_schedules[int(math.log2(schedule.day)) + 1] = schedule.schedule
                if schedule.day == 64:  # add the Sunday entry to the start of the list
                    day_schedules[0] = schedule.schedule

            # we want these to be in the same format as the cleaned entries
            cleaned_day_schedules = []
            for entry in day_schedules:
                cleaned = []
                for (key, value) in entry.items():
                    cleaned.append((int(key), int(value)))
                cleaned_day_schedules.append(sorted(cleaned, key=lambda x: x[0]))
            # we now have a list of lists,
            #   where each list contains a sequence of sorted tuples
            #   and each tuple represents a (timeslot, profile)
            # furthermore, indices 1 through 7 are for Monday to Sunday, with indice 0 for the Sunday loop

            # now we can merge the two schedules
            updating_indices = []
            for (index, day) in enumerate([1, 2, 4, 8, 16, 32, 64]):
                if day & request.daymask == day:
                    updating_indices.append(index + 1)
                    # the PUT request is the desired new schedule for this day
                    cleaned_day_schedules[index + 1] = cleaned_schedule.copy()  # DON'T FORGET THE COPY!!

            # almost there!
            # to ensure that the new schedule for a given day contains a (0, profile) element we (may) need to look back
            # since the database always has a (0, profile) entry, and we demand at least one entry for a PUT,
            # this element is guaranteed to exist on a single pass
            for index in updating_indices:
                schedule = cleaned_day_schedules[index]
                first_entry = schedule[0]
                if first_entry[0] != 0:
                    # we need to add a (0, profile) entry to the start of the schedule
                    # the profile we want is the last one of the previous day
                    previous_schedules = cleaned_day_schedules[index - 1]
                    last_entry = previous_schedules[-1]
                    print(last_entry)
                    schedule.insert(0, (0, last_entry[1]))

            # now cleaned_day_schedules has the schedule we want to store, and updating_indices has the days
            revision = pendulum.now("Europe/London")
            for index in updating_indices:
                schedule = cleaned_day_schedules[index]
                # convert the schedule into a dictionary
                schedule_dict = {}
                for (key, value) in schedule:
                    schedule_dict[f"{key}"] = f"{value}"
                # store the schedule in the database
                db_session.add(Schedule(home=home, revision=revision, day=2 ** (index - 1), schedule=schedule_dict))
            db_session.commit()
        except (DaciteError, ValueError) as err:
            resp.content_type = falcon.MEDIA_TEXT
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.text = f"one or more of the parameters was not understood\n{err}"
