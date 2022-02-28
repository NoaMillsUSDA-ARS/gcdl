
from .gsdataset import GSDataSet
from pyproj.crs import CRS
import datetime
import rioxarray
import xarray as xr
from pydap.client import open_url
import data_request as dr
from subset_geom import SubsetPolygon, SubsetMultiPoint


class MODIS_NDVI(GSDataSet):
    def __init__(self, store_path):
        """
        store_path (Path): The location of remote dataset storage.
        """
        super().__init__('https://thredds.daac.ornl.gov/thredds/dodsC/ornldaac', '1299')

        # Basic dataset information.
        self.id = 'MODIS_NDVI'
        self.name = 'MODIS NDVI Data, Smoothed and Gap-filled, for the Conterminous US: 2000-2015'
        self.url = 'https://doi.org/10.3334/ORNLDAAC/1299'

        # CRS information.
        self.crs = CRS.from_epsg(2163)

        # The grid size
        self.grid_size = 250
        self.grid_unit = 'meters'

        # The variables/layers/bands in the dataset.
        self.vars = {
            'NDVI': 'Normalized Difference Vegetation Index'
        }

        # Temporal coverage of the dataset.
        #self.date_ranges['year'] = [
        #    datetime.date(1980, 1, 1), datetime.date(2020, 1, 1)
        #]
        #self.date_ranges['month'] = [
        #    datetime.date(2000, 1, 1), datetime.date(2015, 12, 1)
        #]
        self.date_ranges['day'] = [
            datetime.date(2000, 1, 1), datetime.date(2015, 12, 31)
        ]

        # File name patterns for each variable.
        self.fpatterns = {
            'NDVI': 'MCD13.A{0}.unaccum.nc4'
        }

    def getData(
        self, varname, date_grain, request_date, ri_method, subset_geom=None
    ):
        """
        varname: The variable to return.
        date_grain: The date granularity to return, specified as a constant in
            data_request.
        request_date: A data_request.RequestDate instance.
        ri_method: The resample/interpolation method to use, if needed.
        subset_geom: An instance of SubsetGeom.  If the CRS does not match the
            dataset, an exception is raised.
        """

        # Get the path to the required data file.
        if date_grain == dr.ANNUAL:
            raise NotImplementedError()
        elif date_grain == dr.MONTHLY:
            raise NotImplementedError()
        elif date_grain == dr.DAILY:
            fname = self.fpatterns[varname].format(request_date.year)
        else:
            raise ValueError('Invalid date grain specification.')

        #fpath = self.ds_path + fname
        fpath = 'https://thredds.daac.ornl.gov/thredds/dodsC/ornldaac/1299/' + fname

        data_store = open_url(fpath) 
        data = xr.open_dataset(xr.backends.PydapDataStore(data_store), decode_coords="all")


        if subset_geom is not None and not(self.crs.equals(subset_geom.crs)):
            raise ValueError(
                'Subset geometry CRS does not match dataset CRS.'
            )

        # Limit download to bbox around user geom
        sg_bounds = subset_geom.geom.bounds
        request_date = '{0}-{1:02d}-{2:02d}'.format(request_date.year,request_date.month,request_date.day)
        data = data[varname].sel(
            x = slice(sg_bounds.minx[0],sg_bounds.maxx[0]), 
            y = slice(sg_bounds.miny[0],sg_bounds.maxy[0]),
            time = slice(request_date,request_date)
        )

        if isinstance(subset_geom, SubsetPolygon):
            data = data.rio.clip([subset_geom.json])
        elif isinstance(subset_geom, SubsetMultiPoint):
            # Interpolate all (x,y) points in the subset geometry.  For more
            # information about how/why this works, see
            # https://xarray.pydata.org/en/stable/user-guide/interpolation.html#advanced-interpolation.
            res = data.interp(
                x=('z', subset_geom.geom.x), y=('z', subset_geom.geom.y),
                method=ri_method
            )
            data = res.values[0]

        return data

