
import random
import zipfile
import json
import api_core.data_request as dr
from pathlib import Path
import xarray as xr


# Characters for generating random file names.
fname_chars = 'abcdefghijklmnopqrstuvwxyz0123456789'

class DataRequestOutput:
    """
    Manages data request output.
    """
    def __init__(self):
        pass

    def requestDateAsString(self, grain, rdate):
        if grain == NONE or rdate is None:
            dstr = ''
        elif grain == ANNUAL:
            dstr = '{0}'.format(
                rdate.year
            )
        elif grain == MONTHLY:
            dstr = '{0}-{1:02}'.format(
                rdate.year, rdate.month
            )
        elif grain == DAILY:
            dstr = '{0}-{1:02}-{2:02}'.format(
                rdate.year, rdate.month, rdate.day
            )
        else:
            raise ValueError('Invalid date granularity specification.')

        return dstr

    def _getSingleLayerOutputFileName(self, dsid, varname, grain, rdate):

        date_str = self._requestDateAsString(grain, rdate)
        if date_str == '':
           fname = '{0}_{1}'.format(
                    dsid, varname
                ) 
        else:
            fname = '{0}_{1}_{2}'.format(
                    dsid, varname, date_str
                )

        return fname


    def _writeCSV(self, data_gdf, fout_path):
        # Modify geometry to list coordinates in x,y columns
        data_gdf['x'] = data_gdf.geometry.x
        data_gdf['y'] = data_gdf.geometry.y
        data_gdf = data_gdf.drop(columns=['geometry'])
        # Write to CSV
        data_gdf.to_csv(fout_path, index=False)

    def _writeShapefile(self, data_gdf, fout_path):
        data_gdf.to_file(fout_path, index=False)

    def _writeNetCDF(self, data_gdf, subset_geom, fout_path):
        
        # Modify geometry to list coordinates in x,y columns
        data_gdf['x'] = data_gdf.geometry.x
        data_gdf['y'] = data_gdf.geometry.y
        data_gdf = data_gdf.drop(columns=['geometry'])
        data_gdf = data_gdf.set_index(['x', 'y', 'time'])
        # Pivot wider
        data_gdf['dsvar'] = data_gdf['dataset'] + '_' + data_gdf['variable']
        data_gdf = data_gdf.pivot(
            #index = ['x','y','time'],
            columns = 'dsvar',
            values = 'value'
        )
        # Convert to xarray DataArray
        data_xr = data_gdf.to_xarray()
        data_xr.rio.write_crs(subset_geom.crs, inplace=True)
        print(data_xr)
        # Write to netCDF
        data_xr.to_netcdf(fout_path)

    def _writeGeoTIFF(self, data_xrds, fout_path):
        pass

    def _writePointFiles(self, ds_output_dict, request, output_dir):
        
        fname = '_'.join(request.dsvars.keys())
        fout_path = output_dir / (fname + request.file_extension)

        # Merge list of geodataframes into one geodataframe
        # Assuming long format for now:
        print(ds_output_dict)
        ds_output_list = [gdf for gdf in ds_output_dict.values()]
        final_gdf = ds_output_list[0]
        for gdf in ds_output_list[1:]:
            final_gdf = final_gdf.append(gdf)

        print(final_gdf)
        if request.file_extension == ".csv":
            self._writeCSV(final_gdf, fout_path)
            fout_paths = [fout_path]
        elif request.file_extension == ".shp":
            self._writeShapefile(final_gdf, fout_path)
            # Return all shapefile's auxillary files
            p = Path(output_dir).glob(fname+'.*')
            fout_paths = [file for file in p]
        elif request.file_extension == ".nc":
            self._writeNetCDF(final_gdf, request.subset_geom, fout_path)
            fout_paths = [fout_path]
        else:
            raise ValueError('Unsupported point output format.')

        return fout_paths


    def _writeRasterFiles(self, ds_output_dict, request, output_dir):
        fout_paths = []
        if request.file_extension == ".tif":
            for dsid in ds_output_dict:
                ds = ds_output_dict[dsid]
                for varname in list(ds.data_vars):
                    dsvar = ds[varname]
                    for t in dsvar.coords['time'].values:
                        fname = self._getSingleLayerOutputFileName(dsid, varname, grain, t)
                        fout_path = output_dir / (fname + request.file_extension)
                        dsvar.sel(time = t).rio.to_raster(fout_path)
                        fout_paths.append(fout_path)
        elif request.file_extension == ".nc":
            # Write a netcdf per dataset. 
            for dsid in ds_output_dict:
                fname = dsid
                fout_path = output_dir / (fname + request.file_extension)
                ds_dataset = ds_output_dict[dsid]
                ds_dataset.to_netcdf(fout_path)
                fout_paths.append(fout_path)
        else:
            raise ValueError('Unsupported raster output format.')

        return fout_paths

    def _writeMetadataFile(self, req_md, output_dir):
        # Write the metadata file.
        md_path = output_dir / (
            ''.join(random.choices(fname_chars, k=16)) + '.json'
        )
        with open(md_path, 'w') as fout:
            json.dump(req_md, fout, indent=4)

        return md_path


    def writeRequestedData(self, request, req_data, output_dir):
        """
        Writes requested data in requested output format
        """

        # Create random id for this request
        req_id = random.choices(fname_chars, k=8)

        # Create temporary output folder for request
        tmp_fname = (
            'geocdl_subset_' + ''.join(req_id)
        )
        tmp_path = output_dir / tmp_fname
        tmp_path.mkdir()

        # Write requested data
        if request.request_type == dr.REQ_RASTER:
            fout_paths = self._writeRasterFiles(req_data, request, tmp_path)
        elif request.request_type == dr.REQ_POINT:
            fout_paths = self._writePointFiles(req_data, request, tmp_path)

        md_path = self._writeMetadataFile(request.metadata, tmp_path)
        

        # Generate the output ZIP archive.
        zfname = (
            'geocdl_subset_' + ''.join(random.choices(fname_chars, k=8)) +
            '.zip'
        )
        zfpath = output_dir / zfname
        zfile = zipfile.ZipFile(
            zfpath, mode='w', compression=zipfile.ZIP_DEFLATED
        )

        zfile.write(md_path, arcname='metadata.json')

        for fout_path in fout_paths:
            zfile.write(fout_path, arcname=fout_path.name)

        zfile.close()

        return zfpath

