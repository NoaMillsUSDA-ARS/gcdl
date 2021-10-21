
from catalog.catalog import DatasetCatalog
from catalog.datasets import PRISM, DAYMET
from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
import tempfile
import zipfile
import random
from pathlib import Path


dsc = DatasetCatalog('local_data')
dsc.addDatasetsByClass(PRISM, DAYMET)

# Characters for generating random file names.
fname_chars = 'abcdefghijklmnopqrstuvwxyz0123456789'

# Directory for serving output files.
output_dir = Path('output')

def check_dsid(dsid, ds_catalog):
    """
    Raises an exception if a given dataset ID is invalid.
    """
    if dsid not in ds_catalog:
        raise HTTPException(
            status_code=404, detail=f'Invalid dataset ID: {dsid}'
        )


app = FastAPI(
    title='Geospatial Common Data Library REST API',
    description='Welcome to the interactive documentation for USDA-ARS\'s '
    'Geospatial Common Data Library (GeoCDL) REST API! Here, you can see all '
    'available API endpoints and directly experiment with GeoCDL API calls. '
    'Note that most users will find it easier to access the GeoCDL via one of '
    'our higher-level interfaces, including a web GUI interface and packages '
    'for Python and R.'
)

@app.get(
    '/list_datasets',
    summary='Returns a list with the ID and name of each dataset in the '
    'library.'
)
async def list_datasets():
    return dsc.getCatalogEntries()


@app.get(
    '/ds_info',
    summary='Returns metadata for the geospatial dataset with the provided ID.'
)
async def ds_info(
    dsid: str = Query(
        ..., alias='id', title='Dataset ID', description='The ID of a dataset.'
    )
):
    check_dsid(dsid, dsc)

    return dsc[dsid].getMetadata()


def parse_varslist(
    ds_vars: str = Query(
        ..., alias='vars', title='Variables', description='The dataset '
        'variables to include, specified as a comma-separated list.'
    )
):
    """
    Parses a comma-separated list of dataset variables.
    """
    return ds_vars.split(',')

def parse_rect_bounds(
    bbox: str = Query(
        None, title='Bounding box', description='The upper left and lower '
        'right corners of the bounding box for subsetting the data, specifed '
        'as a comma-separated list of the form '
        '"UPPER_LEFT_Y_COORD,UPPER_LEFT_X_COORD,'
        'LOWER_RIGHT_Y_COORD,LOWER_RIGHT_X_COORD." If no bounding box is '
        'specified, the full spatial extent will be returned.'
    )
):
    """
    Parses comma-separated rectangular bounding box coordinates.
    """
    if bbox is None:
        return None

    parts = bbox.split(',')
    if len(parts) != 4:
        raise HTTPException(
            status_code=400, detail='Incorrect bounding box specification.'
        )

    try:
        parts = [float(part) for part in parts]
    except:
        raise HTTPException(
            status_code=400, detail='Incorrect bounding box specification.'
        )

    coords = [[parts[0], parts[1]], [parts[2], parts[3]]]

    return coords

@app.get(
    '/subset',
    summary='Requests a geographic subset (which can be the full dataset) of '
    'one or more variables from a geospatial dataset.'
)
async def subset(
    dsid: str = Query(
        ..., alias='id', title='Dataset ID', description='The ID of a dataset.'
    ),
    date_start: str = Query(
        ..., title='Start date (inclusive)', description='The starting date '
        'for which to request data. Dates must be specified as strings, where '
        '"YYYY" means extract annual data, "YYYY-MM" is for monthly data, and '
        '"YYYY-MM-DD" is for daily data.'
    ),
    date_end: str = Query(
        ..., title='End date (inclusive)', description='The ending date '
        'for which to request data. Dates must be specified as strings, where '
        '"YYYY" means extract annual data, "YYYY-MM" is for monthly data, and '
        '"YYYY-MM-DD" is for daily data.'
    ),
    ds_vars: list = Depends(parse_varslist),
    bbox: list = Depends(parse_rect_bounds)
):
    check_dsid(dsid, dsc)

    ds = dsc[dsid]
    out_paths = ds.getSubset(output_dir, date_start, date_end, ds_vars, bbox)

    zfname = (
        'geocdl_subset_' + ''.join(random.choices(fname_chars, k=8)) +
        '.zip'
    )
    zfpath = output_dir / zfname
    zfile = zipfile.ZipFile(
        zfpath, mode='w', compression=zipfile.ZIP_DEFLATED
    )

    for out_path in out_paths:
        zfile.write(out_path, arcname=out_path.name)

    zfile.close()

    return FileResponse(zfpath, filename=zfpath.name)
