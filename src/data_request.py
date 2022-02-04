
import datetime as dt
from pyproj.crs import CRS


# Date granularity constants.
ANNUAL = 0
MONTHLY = 1
DAILY = 2


class DataRequest:
    """
    Encapsulates a single API data request.
    """
    def __init__(
        self, dsvars, date_start, date_end, clip_poly, target_crs
    ):
        """
        dsc: The DatasetCatalog to use.
        dsvars: A dict of lists of variables to include for each dataset with
            dataset IDs as keys.
        date_start: Inclusive start date, specied as 'YYYY', 'YYYY-MM', or
            'YYYY-MM-DD'.
        date_end: Inclusive end date, specied as 'YYYY', 'YYYY-MM', or
            'YYYY-MM-DD'.
        clip_poly: A ClipPolygon representing the clipping region to use or
            None.
        target_crs: A string specifying the target CRS.
        """
        self.dsvars = dsvars
        self.dates, self.date_grain = self._parse_dates(date_start, date_end)
        self.clip_poly = clip_poly
        self.target_crs = CRS(target_crs)

    def _parse_dates(self, date_start, date_end):
        """
        Parses the starting and ending date strings and returns a tree-like
        data structure that specifies all dates included in the request, with
        year and month as keys.  We represent request dates this way because it
        supports sparse date ranges.
        """
        # Note: We assume here that this is running under at least Python 3.7,
        # which is the point at which dict insertion order preservation became
        # an official feature.
        dates = {}

        if len(date_start) == 4 and len(date_end) == 4:
            # Annual data request.
            date_grain = ANNUAL

            start = int(date_start)
            end = int(date_end) + 1
            if end <= start:
                raise ValueError('The end date cannot precede the start date.')
            
            # Generate the dates data structure.
            for year in range(start, end):
                dates[year] = {}

        elif len(date_start) == 7 and len(date_end) == 7:
            # Monthly data request.
            date_grain = MONTHLY

            start_y, start_m = [int(val) for val in date_start.split('-')]
            end_y, end_m = [int(val) for val in date_end.split('-')]

            if start_m < 1 or start_m > 12:
                raise ValueError(f'Invalid month value: {start_m}.')
            if end_m < 1 or end_m > 12:
                raise ValueError(f'Invalid month value: {end_m}.')

            if end_y * 12 + end_m < start_y * 12 + start_m:
                raise ValueError('The end date cannot precede the start date.')

            # Generate the dates data structure.
            cur_y = start_y
            cur_m = start_m
            m_cnt = start_m - 1
            while cur_y * 12 + cur_m <= end_y * 12 + end_m:
                if cur_y not in dates:
                    dates[cur_y] = {}

                dates[cur_y][cur_m] = []

                m_cnt += 1
                cur_y = start_y + m_cnt // 12
                cur_m = (m_cnt % 12) + 1

        elif len(date_start) == 10 and len(date_end) == 10:
            # Daily data request.
            date_grain = DAILY

            start_y, start_m, start_d = [
                int(val) for val in date_start.split('-')
            ]
            end_y, end_m, end_d = [int(val) for val in date_end.split('-')]

            inc_date = dt.date(start_y, start_m, start_d)
            end_date = dt.date(end_y, end_m, end_d)

            if end_date < inc_date:
                raise ValueError('The end date cannot precede the start date.')

            interval = dt.timedelta(days=1)
            end_date += interval

            # Generate the dates data structure.
            while inc_date != end_date:
                if inc_date.year not in dates:
                    dates[inc_date.year] = {}

                if inc_date.month not in dates[inc_date.year]:
                    dates[inc_date.year][inc_date.month] = []

                dates[inc_date.year][inc_date.month].append(inc_date.day)

                inc_date += interval

        else:
            raise ValueError(
                'Mismatched starting and ending date granularity.'
            )

        return (dates, date_grain)

