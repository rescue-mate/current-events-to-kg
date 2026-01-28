# Copyright: (c) 2022, Lars Michaelis
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

import re 
from datetime import datetime, time, timezone, timedelta
from typing import Dict, Union, List


class DateTimeParser:
    date_regexes = None

    @staticmethod
    def __convert_12_to_24_format(hour: int, is_pm: bool) -> int:
        if is_pm:
            if hour != 12:
                return hour + 12
        else:
            if hour == 12:
                return 0
        return hour
    
    @classmethod
    def parse_times(cls, time_str: str) -> Dict[str, time]:
        offset_match = re.search(r'UTC(?P<h>[\+-]\d\d?)(?::(?P<m>\d\d))?', time_str)

        if offset_match:
            offset_groups = offset_match.groupdict()
            offset_hours = offset_groups['h']
            offset_minutes = offset_groups['m']
            if offset_hours:
                offset_hours = int(offset_hours)
                if offset_minutes:
                    offset_minutes = int(offset_minutes)
                else:
                    offset_minutes = 0
            else:
                offset_hours, offset_minutes = 0, 0
            
            tz = timezone(timedelta(hours=offset_hours, minutes=offset_minutes))

        else:  # no offset information found
            tz = None

        # random samples that should match the following regex:
        # 8:05
        # 08:05
        # 8:05 am
        # 8:05 a.m.
        # 8:05 A.M
        # 08:05 Pm
        # 12:40 p.m.
        # 0:09 AM
        # 9:59 aM.
        # 23:15
        #
        # 7:03-9:47
        # 7:03 - 9:47
        # 07:03-09:47
        # 7:03 to 9:47
        # 7:03 and 9:47
        # 7:03 am-9:47 pm
        # 7:03 a.m. - 9:47 p.m.
        # 07:03 AM to 09:47 PM
        # 12:00 pm - 1:05 pm
        # 0:00 a.m. to 00:30 a.m.
        # 9:08 P.M.-11:59 P.M.
        # 23:10 - 00:05
        #
        # There are eight groups: hs, ms, ams, pms, he, me, ame, pme
        match = re.search(
            r'(?P<hs>\d\d?):(?P<ms>\d\d)\s*((?P<ams>[aA].?[mM].?)|(?P<pms>[pP].?[mM].?))?' +
            r'(\s*(-|–|and|to)\s*' +
            r'(?P<he>\d\d?):(?P<me>\d\d)\s*((?P<ame>[aA].?[mM].?)|(?P<pme>[pP].?[mM].?))?' +
            r')?',
            time_str
        )

        if match:
            time_dict = {}

            groups = match.groupdict()

            for boundary in ['start', 'end']:
                s_or_e = boundary[0]
                hours, minutes = groups['h'+s_or_e], groups['m'+s_or_e]

                if hours and minutes:
                    hours, minutes = int(hours), int(minutes)

                    am, pm = groups['am'+s_or_e], groups['pm'+s_or_e]

                    if pm or am:
                        hours = cls.__convert_12_to_24_format(hours, bool(pm))

                    time_dict[boundary] = time(hour=hours, minute=minutes, tzinfo=tz)
            
            assert 'start' in time_dict

            return time_dict

        return {}
    
    @classmethod
    def parse_dates(cls, date_time_str: str) -> Dict[str, Union[datetime,bool]]:

        months = [
            'january',
            'february',
            'march',
            'april',
            'may',
            'june',
            'july',
            'august',
            'september',
            'october',
            'november',
            'december'
        ]

        if cls.date_regexes is None:
            cls.date_regexes = cls.__compile_regexes()
        
        date_dict = {}
        for re_x in cls.date_regexes:
            m = re_x.search(date_time_str)
            if m:
                group_dict = m.groupdict()

                try:
                    year = int(group_dict['year'])
                    mon = months.index(group_dict['mon'].lower()) + 1
                    day = int(group_dict['day'])

                    date_dict['date'] = datetime(
                        year,
                        mon,
                        day
                    )

                    if 'day2' in group_dict:  # -> there are two date-time mentions: start - end
                        if 'mon2' in group_dict:
                            try:
                                mon2 = months.index(group_dict['mon2'].lower()) + 1

                            except ValueError:
                                continue

                        else:  # no separate end month
                            mon2 = mon
                        
                        if 'year2' in group_dict:
                            year2 = int(group_dict['year2'])
                        else:
                            year2 = year

                        day2 = int(group_dict['day2'])

                        # year2, month2 and day2 become the 'until' date:
                        date_dict['until'] = datetime(year2, mon2, day2)

                    elif 'on' in group_dict and group_dict['on']:
                        date_dict['ongoing'] = True

                except ValueError:
                    continue
                    
                break

        return date_dict
    
    @staticmethod
    def __compile_regexes() -> List[re.Pattern]:
        to = r'\s*(?:-|–|until|to)\s*'
        ongoing = r'(?P<on>([Pp]resent|[Oo]ngoing))'

        day = r'(?P<day>\d\d?)'
        day2 = r'(?P<day2>\d\d?)'
        month = r'(?P<mon>\w{3,9})'
        month2 = r'(?P<mon2>\w{3,9})'
        year = r'(?P<year>\d{2,4})'
        year2 = r'(?P<year2>\d{2,4})'

        dm = day + r'\s+' + month
        dmy = dm + r'\s+' + year
        dmy_on = dm + r'\s+' + year + to + ongoing
        ddmy = day + to + day2 + r'\s+' + month + r'\s+' + year
        dmdmy = dm + to + day2 + r'\s+' + month2 + r'\s+' + year
        dmydmy = dmy + to + day2 + r'\s+' + month2 + r'\s+' + year2
        re_dmy = re.compile(dmy)
        re_dmy_on = re.compile(dmy_on)
        re_ddmy = re.compile(ddmy)
        re_dmdmy = re.compile(dmdmy)
        re_dmydmy = re.compile(dmydmy)

        md = month + r'\s*(?:/|\s)\s*' + day
        mdy = md + r'\s*[/,]\s*' + year
        mdy_on = md + r'\s*[/,]\s*' + year + to + ongoing
        mddy = md + to + day2 + r'\s*[/,]\s*' + year
        mdmdy = md + to + month2 + r'\s*' + day2 + r'\s*[/,]\s*' + year
        mdymdy = mdy + to + month2 + r'\s*(?:/|\s)\s*' + day2 + r'\s*[/,]\s*' + year2
        re_mdy = re.compile(mdy)
        re_mdy_on = re.compile(mdy_on)
        re_mddy = re.compile(mddy)
        re_mdmdy = re.compile(mdmdy)
        re_mdymdy = re.compile(mdymdy)

        return [
            re_mdymdy,
            re_dmydmy,
            re_mdmdy,
            re_dmdmy,
            re_mddy,
            re_ddmy,
            re_mdy_on,
            re_dmy_on,
            re_mdy,
            re_dmy
        ]
