from datetime import time, timezone, timedelta, datetime

from currenteventstokg.datetimeparser import DateTimeParser


class TestTimeParser:
    def test_date_parsing_01(self):
        date_str = u'January 1, 2021'

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2021, 1, 1)
        assert len(parsed_dates) == 1

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_parsing_02(self):
        date_str = u'January 1, 2021 - present'

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2021, 1, 1)
        assert parsed_dates.get('ongoing') == True
        assert len(parsed_dates) == 2

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_parsing_03(self):
        date_str = u'January 1 - 12, 2021'

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2021, 1, 1)
        assert parsed_dates.get('until') == datetime(2021, 1, 12)
        assert len(parsed_dates) == 2

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_parsing_04(self):
        date_str = u'January 1 - February 12, 2021'

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2021, 1, 1)
        assert parsed_dates.get('until') == datetime(2021, 2, 12)
        assert len(parsed_dates) == 2

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_parsing_05(self):
        date_str = u'January 1, 2021 - February 12, 2022'

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2021, 1, 1)
        assert parsed_dates.get('until') == datetime(2022, 2, 12)
        assert len(parsed_dates) == 2

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_parsing_06(self):
        date_str = u'1 January 2021'

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2021, 1, 1)
        assert len(parsed_dates) == 1

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_parsing_07(self):
        date_str = u'1 January 2021 - ongoing'

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2021, 1, 1)
        assert parsed_dates.get('ongoing') == True
        assert len(parsed_dates) == 2

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_parsing_08(self):
        date_str = u'1 - 2 January 2021'

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2021, 1, 1)
        assert parsed_dates.get('until') == datetime(2021, 1, 2)
        assert len(parsed_dates) == 2

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_parsing_09(self):
        date_str = u'1 January - 12 February 2022'

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2022, 1, 1)
        assert parsed_dates.get('until') == datetime(2022, 2, 12)
        assert len(parsed_dates) == 2

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_parsing_10(self):
        date_str = u'1 January 2021 - 12 February 2022'

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2021, 1, 1)
        assert parsed_dates.get('until') == datetime(2022, 2, 12)
        assert len(parsed_dates) == 2

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_time_parsing_01(self):
        date_time_str = u'''January 15, 2022 
        10:41 a.m. – 9:22 p.m. (CST)'''

        parsed_dates = DateTimeParser.parseDates(date_time_str)

        assert parsed_dates.get('date') == datetime(2022, 1, 15)
        assert len(parsed_dates) == 1

        parsed_times = DateTimeParser.parse_times(date_time_str)

        assert parsed_times.get('start') == time(10, 41)
        assert parsed_times.get('end') == time(21, 22)
        assert len(parsed_times) == 2

    def test_date_time_parsing_02(self):
        date_time_str = u'''17 January 2022 (4 months ago)
        14:29 - 14:50 (UTC+4:00)'''
        tz = timezone(timedelta(hours=4))

        parsed_dates = DateTimeParser.parseDates(date_time_str)

        assert parsed_dates.get('date') == datetime(2022, 1, 17)
        assert len(parsed_dates) == 1

        parsed_times = DateTimeParser.parse_times(date_time_str)

        assert parsed_times.get('start') == time(14, 29, tzinfo=tz)
        assert parsed_times.get('end') == time(14, 50, tzinfo=tz)
        assert len(parsed_times) == 2

    def test_date_time_parsing_03(self):
        date_time_str = u'''3 January 2020
        About 1:00 a.m. (local time, UTC+3)'''
        tz = timezone(timedelta(hours=3))

        parsed_dates = DateTimeParser.parseDates(date_time_str)

        assert parsed_dates.get('date') == datetime(2020, 1, 3)
        assert len(parsed_dates) == 1

        parsed_times = DateTimeParser.parse_times(date_time_str)

        assert parsed_times.get('start') == time(1, 0, tzinfo=tz)
        assert len(parsed_times) == 1

    def test_date_time_parsing_04(self):
        date_time_str = u'''Tanami Desert 
        27 June 2021 '''

        parsed_dates = DateTimeParser.parseDates(date_time_str)

        assert parsed_dates.get('date') == datetime(2021, 6, 27)
        assert len(parsed_dates) == 1

        parsed_times = DateTimeParser.parse_times(date_time_str)

        assert parsed_times == {}

    def test_date_time_parsing_05(self):
        date_time_str = u'''February 23, 2020 
        c. 1:15 p.m. '''

        parsed_dates = DateTimeParser.parseDates(date_time_str)

        assert parsed_dates.get('date') == datetime(2020, 2, 23)
        assert len(parsed_dates) == 1

        parsed_times = DateTimeParser.parse_times(date_time_str)

        assert parsed_times.get('start') == time(13, 15)
        assert len(parsed_times) == 1

    def test_date_parsing_11(self):
        date_str = u'''December 30, 2021-January 1, 2022 '''

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2021, 12, 30)
        assert parsed_dates.get('until') == datetime(2022, 1, 1)
        assert len(parsed_dates) == 2

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_date_parsing_12(self):
        date_str = u'''17 November 2019 - present
        (2 years and 6 months)'''

        parsed_dates = DateTimeParser.parseDates(date_str)

        assert parsed_dates.get('date') == datetime(2019, 11, 17)
        assert parsed_dates.get('ongoing') == True
        assert len(parsed_dates) == 2

        parsed_times = DateTimeParser.parse_times(date_str)

        assert parsed_times == {}

    def test_time_parsing_01(self):
        time_str = u'10:41 a.m. (UTC+3)'
        tz = timezone(timedelta(hours=3))

        parsed_dates = DateTimeParser.parseDates(time_str)

        assert parsed_dates == {}

        parsed_time = DateTimeParser.parse_times(time_str)

        assert parsed_time.get('start') == time(10, 41, tzinfo=tz)
        assert len(parsed_time) == 1

    def test_time_parsing_02(self):
        time_str = u'10:41 a.m. (UTC-3)'
        tz = timezone(timedelta(hours=-3))

        parsed_dates = DateTimeParser.parseDates(time_str)

        assert parsed_dates == {}

        parsed_time = DateTimeParser.parse_times(time_str)

        assert parsed_time.get('start') == time(10, 41, tzinfo=tz)
        assert len(parsed_time) == 1    

    def test_time_parsing_03(self):
        time_str = u'10:41 a.m. (UTC+3:30)'
        tz = timezone(timedelta(hours=3, minutes=30))

        parsed_dates = DateTimeParser.parseDates(time_str)

        assert parsed_dates == {}

        parsed_times = DateTimeParser.parse_times(time_str)

        assert parsed_times.get('start') == time(10, 41, tzinfo=tz)
        assert len(parsed_times)

    def test_time_parsing_04(self):
        time_str = u'10:41 a.m. (UTC-3:30)'
        tz = timezone(timedelta(hours=-3, minutes=30))

        parsed_dates = DateTimeParser.parseDates(time_str)

        assert parsed_dates == {}

        parsed_times = DateTimeParser.parse_times(time_str)

        assert parsed_times.get('start') == time(10, 41, tzinfo=tz)
        assert len(parsed_times) == 1

    def test_time_parsing_05(self):
        time_str = u'10:41 a.m. (UTC+13)'
        tz = timezone(timedelta(hours=13))

        parsed_dates = DateTimeParser.parseDates(time_str)

        assert parsed_dates == {}

        parsed_times = DateTimeParser.parse_times(time_str)

        assert parsed_times.get('start') == time(10, 41, tzinfo=tz)
        assert len(parsed_times) == 1

    def test_time_parsing_06(self):
        time_str = u'10:41 a.m. (UTC-13)'
        tz = timezone(timedelta(hours=-13))

        parsed_dates = DateTimeParser.parseDates(time_str)

        assert parsed_dates == {}

        parsed_times = DateTimeParser.parse_times(time_str)

        assert parsed_times.get('start') == time(10, 41, tzinfo=tz)
        assert len(parsed_times) == 1

    def test_time_parsing_07(self):
        time_str = u'10:41 a.m. (UTC+13:30)'
        tz = timezone(timedelta(hours=13, minutes=30))

        parsed_dates = DateTimeParser.parseDates(time_str)

        assert parsed_dates == {}

        parsed_times = DateTimeParser.parse_times(time_str)

        assert parsed_times.get('start') == time(10, 41, tzinfo=tz)
        assert len(parsed_times) == 1

    def test_timezone_parsing_08(self):
        time_str = u'10:41 a.m. (UTC-13:30)'
        tz = timezone(timedelta(hours=-13, minutes=30))

        parsed_dates = DateTimeParser.parseDates(time_str)

        assert parsed_dates == {}

        parsed_times = DateTimeParser.parse_times(time_str)

        assert parsed_times.get('start') == time(10, 41, tzinfo=tz)
        assert len(parsed_times) == 1
