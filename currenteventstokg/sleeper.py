# Copyright: (c) 2022, Lars Michaelis, Patrick Westphal
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import time

class Sleeper:

    def __init__(self):
        self.last_request_timestamp: float = .0

    def sleep_until_new_request_allowed(self, min_seconds_between_queries: float):

        # get the time lapsed since the last call
        now: float = time.time()
        time_lapsed_since_last_call: float = now - self.last_request_timestamp

        sleep_time: float = min_seconds_between_queries - time_lapsed_since_last_call

        # check if we already waited longer
        if sleep_time > .0:
            time.sleep(sleep_time)

        self.last_request_timestamp = time.time()
