
import datetime as dt
from collections import namedtuple
from pyproj.crs import CRS
from subset_geom import SubsetMultiPoint
from library.datasets.gsdataset import getCRSMetadata


# Date granularity constants.
NONE = 0
ANNUAL = 1
MONTHLY = 2
DAILY = 3

# Request type constants.
REQ_RASTER = 0
REQ_POINT = 1

# Define valid resampling/interpolation algorithms.
RESAMPLE_METHODS = (
    'nearest', 'bilinear', 'cubic', 'cubic-spline', 'lanczos', 'average',
    'mode'
)
POINT_METHODS = ('nearest', 'linear')

# Define supported strings for handling mixed date grains
GRAIN_METHODS = ('strict', 'skip', 'coarser', 'finer', 'any')

# Define supported strings for output formats
GRID_OUTPUT = ('geotiff','netcdf')
POINT_OUTPUT = ('csv','shapefile','netcdf')
FILE_EXT = {
    'geotiff': '.tif',
    'netcdf': '.nc',
    'csv': '.csv',
    'shapefile': '.shp'
    }

# A simple struct-like class for capturing data request date information.  We
# need this instead of the standard datetime.date class because the latter does
# not allow year- or month-only dates (i.e., where month or day are None).
RequestDate = namedtuple('RequestDate', ['year', 'month', 'day'])


class DataRequest:
    """
    Encapsulates and validates a single API data request.
    """
    def __init__(
        self, dataset_catalog, dsvars, date_start, date_end, years, 
        months, days, grain_method, subset_geom, target_crs, 
        target_resolution, ri_method, request_type, output_format,
        req_metadata
    ):
        """
        dataset_catalog: The DatasetCatalog associated with this request.
        dsvars: A dict of lists of variables to include for each dataset with
            dataset IDs as keys.
        date_start: Inclusive start date, specied as 'YYYY', 'YYYY-MM', or
            'YYYY-MM-DD'.
        date_end: Inclusive end date, specied as 'YYYY', 'YYYY-MM', or
            'YYYY-MM-DD'.
        years: Years to include in request.
        months: Months to include in request.
        days: Days to include in request.
        grain_method: 
        subset_geom: A SubsetGeom representing the clipping region or points to
            use or None.
        target_crs: A CRS instance.
        target_resolution: A float specifying the target spatial resolution in
            units of the target CRS.
        ri_method: The resampling/interpolation algorithm to use for
            reprojection or extracting point data.
        request_type: A constant specifying the output type.
        output_format: A constant specifying the output file format.
        req_metadata: A key/value mapping of metadata associated with the
            request.
        """
        self.dsc = dataset_catalog
        self.dsvars = dsvars
        self.date_start_raw = date_start
        self.date_end_raw = date_end
        self.dates, self.date_grain = self._parseDates(
            date_start, date_end, years, months, days
        )
        self.subset_geom = subset_geom
        self.target_crs = target_crs
        self.target_resolution = target_resolution

        if request_type not in (REQ_RASTER, REQ_POINT):
            raise ValueError('Invalid request type.')

        self.request_type = request_type

        if ri_method is None:
            ri_method = 'nearest'

        if (
            request_type == REQ_RASTER and
            ri_method not in RESAMPLE_METHODS
        ):
            raise ValueError(
                f'Invalid resampling method: "{ri_method}".'
            )

        if (
            request_type == REQ_POINT and
            ri_method not in POINT_METHODS
        ):
            raise ValueError(
                f'Invalid point interpolation method: "{ri_method}".'
            )

        if (
            request_type == REQ_POINT and
            not(isinstance(subset_geom, SubsetMultiPoint))
        ):
            raise ValueError('No points provided for output.')

        self.ri_method = ri_method
        self.metadata = self._getMetadata(req_metadata)

        if grain_method is None:
            grain_method = 'strict'

        if grain_method not in GRAIN_METHODS:
            raise ValueError(
                f'Invalid date grain matching method: "{grain_method}".'
            )

        self.grain_method = grain_method
        self._verifyGrains()

        if output_format is None:
            if request_type == REQ_RASTER:
                output_format = 'geotiff'
            else:
                output_format = 'csv'

        if (
            request_type == REQ_RASTER and
            output_format not in GRID_OUTPUT
        ):
            raise ValueError(
                f'Invalid output format: "{output_format}".'
            )

        if (
            request_type == REQ_POINT and
            output_format not in POINT_OUTPUT
        ):
            raise ValueError(
                f'Invalid output format: "{output_format}".'
            )

        self.file_extension = FILE_EXT[output_format]

    def _getMetadata(self, req_vals):
        req_md = {}
        req_md.update(req_vals)

        req_md['target_date_range'] = [self.date_start_raw, self.date_end_raw]
        req_md['target_crs'] = getCRSMetadata(self.target_crs)

        if self.request_type == REQ_RASTER:
            req_md['request_type'] = 'raster'
            req_md['target_resolution'] = self.target_resolution
            req_md['resample_method'] = self.ri_method
        elif self.request_type == REQ_POINT:
            req_md['request_type'] = 'points'
            req_md['interpolation_method'] = self.ri_method

        md = {'request': req_md}

        ds_md = []
        for dsid in self.dsvars:
            dsd = self.dsc[dsid].getMetadata()
            dsd['requested_vars'] = self.dsvars[dsid]
            ds_md.append(dsd)

        md['datasets'] = ds_md

        return md

    def _verifyGrains(self):
        # Check strict date granularity
        if self.grain_method == 'strict':
            for dsid in self.dsvars:
                if (
                    not(self.dsc[dsid].nontemporal) and 
                    self.date_grain not in self.dsc[dsid].supported_grains
                ):
                    raise ValueError('{0} does not have requested granularity'.format(dsid))


    def _parseSimpleDateRange(self, date_start, date_end):
        """
        Parses starting and ending date strings and returns a list of
        RequestDate instances that specifies all dates included in the request.
        """
        dates = []

        if date_start is None:
            date_start = ''
        if date_end is None:
            date_end = ''

        if date_start == '' or date_end == '':
            raise ValueError('Start and end dates must both be specified.')

        if len(date_start) == 4 and len(date_end) == 4:
            # Annual data request.
            date_grain = ANNUAL

            start = int(date_start)
            end = int(date_end) + 1
            if end <= start:
                raise ValueError('The end date cannot precede the start date.')
            
            # Generate the dates list.
            for year in range(start, end):
                dates.append(RequestDate(year, None, None))

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

            # Generate the dates list.
            cur_y = start_y
            cur_m = start_m
            m_cnt = start_m - 1
            while cur_y * 12 + cur_m <= end_y * 12 + end_m:
                dates.append(RequestDate(cur_y, cur_m, None))

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

            # Generate the dates list.
            while inc_date != end_date:
                dates.append(
                    RequestDate(inc_date.year, inc_date.month, inc_date.day)
                )

                inc_date += interval

        else:
            raise ValueError(
                'Mismatched starting and ending date granularity.'
            )

        return (dates, date_grain)

    def _parseRangeStr(self, rangestr, maxval):
        """
        Parses a range string of the format "STARTVAL-ENDVAL[+INCREMENT]".
        Returns the range as an ordered list of integers (smallest to largest),
        which includes the endpoints unless ENDVAL does not correspond with the
        increment size.  If ENDVAL == 'N', it is interpreted as maxval.

        rangestr: The range string to parse.
        maxval: The maximum value allowed for the range.
        """
        parts = rangestr.split('-')
        if len(parts) != 2:
            raise ValueError(f'Invalid range string: "{rangestr}".')

        startval = int(parts[0])

        if '+' in parts[1]:
            # Extract the increment size.
            end_parts = parts[1].split('+')
            if len(end_parts) != 2:
                raise ValueError(f'Invalid range string: "{rangestr}".')

            endval_str = end_parts[0]
            inc = int(end_parts[1])
        else:
            endval_str = parts[1]
            inc = 1

        # Determine the ending value of the range.
        if endval_str == 'N':
            if maxval is None:
                raise ValueError(
                    f'Cannot interpret range string "{rangestr}": no maximum '
                    'value was provided.'
                )
            endval = maxval
        else:
            endval = int(endval_str)

        # Check for a bunch of error conditions.
        if startval > endval:
            raise ValueError(
                f'Invalid range string: "{rangestr}". The starting value '
                'cannot exceed the ending value.'
            )
        
        if startval <= 0 or endval <= 0:
            raise ValueError(
                f'Invalid range string: "{rangestr}". The starting and '
                'and ending values must be greater than 0.'
            )

        if maxval is not None and endval > maxval:
            raise ValueError(
                f'Invalid range string: "{rangestr}". The ending value '
                f'cannot exceed {maxval}.'
            )

        return list(range(startval, endval + 1, inc))

    def _parseYMD(self, years, months, days):
        if years is not None:
            print('HERE')
            # Dates method 2
            y_range = self._parseDateRange(years)

            if months is None and days is None:
                date_grain = ANNUAL

                # Generate the dates data structure.
                for year in y_range:
                    dates.append(RequestDate(year, None, None))

            elif months is not None:
                date_grain = MONTHLY

                # Generate the dates data structure.
                m_range = self._parseDateRange(months)
                for year in y_range:
                    for month in m_range:
                        dates.append(RequestDate(year, month, None))
                
                
            elif days is not None:
                date_grain = DAILY

                # Generate the dates data structure.
                d_range = self._parseDateRange(days)
                for year in y_range:
                    for day in d_range:
                        date = dt.date.fromordinal(day + dt.date(year,1,1).toordinal() - 1) 
                        if day == 366 and date.year != year:
                            continue
                        dates.append(RequestDate(year, date.month, date.day))
                
        else: 
            # No dates
            date_grain = NONE

    def _parseDates(self, date_start, date_end, years, months, days):
        """
        Parses the starting and ending date strings and returns a list of
        RequestDate instances that specifies all dates included in the request.
        We represent request dates this way because it supports sparse date
        ranges.
        """
        dates = []

        if all(
            param is None or param == '' for param in
            (date_start, date_end, years, months, days)
        ):
            date_grain = NONE

            return (dates, date_grain)

        if date_start is not None or date_end is not None:
            dates, date_grain = self._parseSimpleDateRange(date_start, date_end)
        else:
            dates, date_graim = self._parseYMD(years, months, days)

        return (dates, date_grain)

