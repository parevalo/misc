#!/usr/bin/env python
from __future__ import division, print_function

from collections import OrderedDict
import inspect
import logging
import sys

import click
import numexpr as ne
import numpy as np
from osgeo import gdal, gdal_array
import six

__version__ = '0.3.0'

CHANGELOG = OrderedDict((
    ('0.1.0', '- Initial script'),
    ('0.1.1', '- Use correct coefficients for BGW calculation'),
    ('0.2.0', '- Include option to mask NODATA in output'),
    ('0.3.0', '''
             - Clarify input and output scaling factors
             - Calculate transform indices in order specified''')
))

FORMAT = '%(asctime)s:%(levelname)s:%(module)s.%(funcName)s:%(message)s'
logging.basicConfig(format=FORMAT, level=logging.INFO, datefmt='%H:%M:%S')
logger = logging.getLogger('transforms')

gdal.UseExceptions()
gdal.AllRegister()

_np_dtypes = ['uint8', 'uint16', 'int16', 'uint32', 'int32',
              'float32', 'float64']
_transforms = ['evi', 'ndvi', 'ndmi', 'nbr',
               'brightness', 'greenness', 'wetness']

# Crist 1985
# "A TM Tasseled Cap Equivalent Transformation for Reflectance Factor Data"
bgw_coef = [
    np.array([0.2043, 0.4158, 0.5524, 0.5741, 0.3124, 0.2330]),
    np.array([-0.1603, -0.2189, -0.4934, 0.7940, -0.0002, -0.1446]),
    np.array([0.0315, 0.2021, 0.3102, 0.1954, -0.6806, -0.6109])
]


def transform(transform_name, required_bands):
    """ Decorator that adds name and requirement info to a transform function

    Args:
      transform_name (str): name of transform
      required_bands (list): list of bands used in the transform

    """
    def decorator(func):
        func.transform_name = transform_name
        func.required_bands = required_bands
        return func
    return decorator


@transform('EVI', ['red', 'nir', 'blue'])
def _evi(red, nir, blue, input_scaling=1.0, output_scaling=1.0, **kwargs):
    """ Return the Enhanced Vegetation Index (EVI)

    EVI is calculated as:

    .. math::
        EVI = 2.5 * \\frac{(NIR - RED)}{(NIR + C_1 * RED - C_2 * BLUE + L)}

    where:
        - :math:`RED` is the red band
        - :math:`NIR` is the near infrared band
        - :math:`BLUE` is the blue band
        - :math:`C_1 = 6`
        - :math:`C_2 = 7.5`
        - :math:`L = 1`

    Args:
      red (np.ndarray): red band
      nir (np.ndarray): NIR band
      blue (np.ndarray): blue band
      input_scaling (float): scaling factor for red, nir, and blue reflectance
        to convert into [0, 1] range (default: 1.0)
      output_scaling (float): scaling factor for output EVI (default: 1.0)

    Returns:
      np.ndarray: EVI

    """
    dtype = red.dtype
    expr = '2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + input_scaling)'
    evi = ne.evaluate(expr)

    if output_scaling != 1.0:
        evi *= output_scaling
    return evi.astype(dtype)


@transform('NDVI', ['red', 'nir'])
def _ndvi(red, nir, output_scaling=1.0, **kwargs):
    """ Return the Normalized Difference Vegetation Index (NDVI)

    NDVI is calculated as:

    .. math::
        NDVI = \\frac{(NIR - RED)}{(NIR + RED)}

    where:
        - :math:`RED` is the red band
        - :math:`NIR` is the near infrared band

    Args:
      red (np.ndarray): red band
      nir (np.ndarray): NIR band
      output_scaling (float): scaling factor for output NDVI (default: 1.0)

    Returns:
      np.ndarray: NDVI

    """
    expr = '(nir - red) / (nir + red)'
    if output_scaling == 1.0:
        return ne.evaluate(expr)
    else:
        return ne.evaluate(expr) * output_scaling


@transform('NDMI', ['swir1', 'nir'])
def _ndmi(swir1, nir, output_scaling=1.0, **kwargs):
    """ Return the Normalized Difference Moisture Index (NDMI)

    NDMI is calculated as:

    .. math::
        NDMI = \\frac{(NIR - SWIR1)}{(NIR + SWIR1)}

    where:
        - :math:`SWIR1` is the shortwave infrared band
        - :math:`NIR` is the near infrared band

    Args:
      swir1 (np.ndarray): SWIR1 band
      nir (np.ndarray): NIR band
      output_scaling (float): scaling factor for output NDVI (default: 1.0)

    Returns:
      np.ndarray: NDMI

    """
    expr = '(nir - swir1) / (nir + swir1)'
    if output_scaling == 1.0:
        return ne.evaluate(expr)
    else:
        return ne.evaluate(expr) * output_scaling


@transform('NBR', ['swir2', 'nir'])
def _nbr(swir2, nir, output_scaling=1.0, **kwargs):
    """ Return the Normalized Burn Ratio (NBR)

    NBR is calculated as:

    .. math::
        NBR = \\frac{(NIR - SWIR2)}{(NIR + SWIR2)}

    where:
        - :math:`SWIR2` is the shortwave infrared band
        - :math:`NIR` is the near infrared band

    Args:
      swir2 (np.ndarray): SWIR2 band
      nir (np.ndarray): NIR band
      output_scaling (float): scaling factor for output NDVI (default: 1.0)

    Returns:
      np.ndarray: NBR

    """
    expr = '(nir - swir2) / (nir + swir2)'
    if output_scaling == 1.0:
        return ne.evaluate(expr)
    else:
        return ne.evaluate(expr) * output_scaling


@transform('Brightness', ['blue', 'green', 'red', 'nir', 'swir1', 'swir2'])
def _brightness(blue, green, red, nir, swir1, swir2,
                input_scaling=1.0, output_scaling=1.0, **kwargs):
    c1, c2, c3, c4, c5, c6 = bgw_coef[0]

    expr = ('blue * c1 + green * c2 + red * c3'
            ' + nir * c4 + swir1 * c5 + swir2 * c6')

    if input_scaling == output_scaling:
        return ne.evaluate(expr)
    else:
        return output_scaling / input_scaling * ne.evaluate(expr)


@transform('Greenness', ['blue', 'green', 'red', 'nir', 'swir1', 'swir2'])
def _greenness(blue, green, red, nir, swir1, swir2,
               input_scaling=1.0, output_scaling=1.0, **kwargs):
    c1, c2, c3, c4, c5, c6 = bgw_coef[1]

    expr = ('blue * c1 + green * c2 + red * c3'
            ' + nir * c4 + swir1 * c5 + swir2 * c6')

    if input_scaling == output_scaling:
        return ne.evaluate(expr)
    else:
        return output_scaling / input_scaling * ne.evaluate(expr)


@transform('Wetness', ['blue', 'green', 'red', 'nir', 'swir1', 'swir2'])
def _wetness(blue, green, red, nir, swir1, swir2,
             input_scaling=1.0, output_scaling=1.0, **kwargs):
    c1, c2, c3, c4, c5, c6 = bgw_coef[2]

    expr = ('blue * c1 + green * c2 + red * c3'
            ' + nir * c4 + swir1 * c5 + swir2 * c6')

    if input_scaling == output_scaling:
        return ne.evaluate(expr)
    else:
        return output_scaling / input_scaling * ne.evaluate(expr)


# Main script
def changelog_option(*param_decls, **attrs):
    def decorator(f):
        def callback(ctx, param, value):
            if not value:
                return
            click.echo('Current version: %s' % __version__)
            for version in CHANGELOG:
                click.echo('Version history: %s' % version)
                for item in CHANGELOG[version].split('\n'):
                    if not item:
                        continue
                    click.echo(click.wrap_text(
                        item.lstrip(),
                        initial_indent='    ',
                        subsequent_indent='        '))
            ctx.exit()

        attrs.setdefault('is_flag', True)
        attrs.setdefault('expose_value', False)
        attrs.setdefault('help', 'Show a changelog and exit.')
        attrs.setdefault('is_eager', True)
        attrs['callback'] = callback

        return click.option(*(param_decls or ('--changelog',)), **attrs)(f)
    return decorator


def _valid_band(ctx, param, value):
    try:
        band = int(value)
        assert band >= 1
    except:
        raise click.BadParameter('Band must be integer above 1')
    return band

_context = dict(
    token_normalize_func=lambda x: x.lower(),
    help_option_names=['--help', '-h']
)


@click.command(context_settings=_context)
@click.option('-f', '--format', default='GTiff', metavar='<str>',
              show_default=True,
              help='Output file format')
@click.option('-ot', '--dtype',
              type=click.Choice(_np_dtypes),
              default=None, metavar='<dtype>', show_default=True,
              help='Output data type')
@click.option('--input_scaling', default=10000, type=float,
              metavar='<factor>',
              show_default=True,
              help='Scaling factor for input reflectance data')
@click.option('--output_scaling', default=10000, type=float,
              metavar='<factor>',
              show_default=True,
              help='Scaling factor for output spectral indices/transforms')
@click.option('--nodata', default=-9999, type=int, metavar='<NoDataValue>',
              show_default=True,
              help='Output image NoDataValue')
@click.option('--blue', callback=_valid_band, default=1, metavar='<int>',
              show_default=True,
              help='Band number for blue band in <src>')
@click.option('--green', callback=_valid_band, default=2, metavar='<int>',
              show_default=True,
              help='Band number for green band in <src>')
@click.option('--red', callback=_valid_band, default=3, metavar='<int>',
              show_default=True,
              help='Band number for red band in <src>')
@click.option('--nir', callback=_valid_band, default=4, metavar='<int>',
              show_default=True,
              help='Band number for near IR band in <src>')
@click.option('--swir1', callback=_valid_band, default=5, metavar='<int>',
              show_default=True,
              help='Band number for first SWIR band in <src>')
@click.option('--swir2', callback=_valid_band, default=6, metavar='<int>',
              show_default=True,
              help='Band number for second SWIR band in <src>')
@click.option('-v', '--verbose', is_flag=True,
              help='Show verbose messages')
@click.version_option(__version__)
@changelog_option()
@click.argument('src', nargs=1,
                type=click.Path(exists=True, readable=True,
                                dir_okay=False, resolve_path=True),
                metavar='<src>')
@click.argument('dst', nargs=1,
                type=click.Path(writable=True, dir_okay=False,
                                resolve_path=True),
                metavar='<dst>')
@click.argument('transforms', nargs=-1,
                type=click.Choice(_transforms),
                metavar='<transform>')
def create_transform(src, dst, transforms,
                     format, dtype, input_scaling, output_scaling, nodata,
                     blue, green, red, nir, swir1, swir2,
                     verbose):
    """ Create one or more reflectance data transformations or spectral indices

    Pay attention to the ``--input_scaling`` and ``--output_scaling`` optional
    arguments to ensure all calculations are done correctly and the output
    data are scaled appropriately given the output datatype.

    The ``--input_scaling`` optional argument is a property of the input data
    while the ``--output_scaling`` should be chosen by the user to fit the
    range of values of a given transformation within the minimums and maximums
    of the desired output datatype.
    """
    if not transforms:
        raise click.BadParameter(
            'No transforms specified', param_hint='<transform>...')

    if verbose:
        logger.setLevel(logging.DEBUG)

    # Pair transforms requested with functions that calculate each transform
    transform_funcs = [obj for name, obj in
                       inspect.getmembers(sys.modules[__name__],
                                          inspect.isfunction)
                       if hasattr(obj, 'transform_name')]

    # Read input image
    try:
        ds = gdal.Open(src, gdal.GA_ReadOnly)
    except:
        logger.error("Could not open source dataset {0}".format(src))
        raise
    driver = gdal.GetDriverByName(str(format))

    # If no output dtype selected, default to input image dtype
    if not dtype:
        dtype = gdal_array.GDALTypeCodeToNumericTypeCode(
            ds.GetRasterBand(1).DataType)
    dtype = np.dtype(dtype)
    gdal_dtype = gdal_array.NumericTypeCodeToGDALTypeCode(dtype)

    # Only read in the bands that are required for the transforms
    required_bands = set()
    for t in transform_funcs:
        required_bands.update(t.required_bands)

    func_args = inspect.getargvalues(inspect.currentframe())[-1]
    transform_args = dict.fromkeys(required_bands)
    mask = np.zeros((ds.RasterYSize, ds.RasterXSize), dtype=np.bool)
    for b in transform_args.keys():
        idx = func_args[b]
        transform_args[b] = ds.GetRasterBand(idx).ReadAsArray()
        _nodata = ds.GetRasterBand(idx).GetNoDataValue() or nodata
        mask[transform_args[b] == _nodata] = 1
    logger.debug('Read input file')

    transform_args['input_scaling'] = input_scaling
    transform_args['output_scaling'] = output_scaling

    # Create transforms
    _transforms = OrderedDict()
    for t in transforms:
        func = [tf for tf in transform_funcs if
                tf.transform_name.lower() == t][0]
        _transforms[func.transform_name] = func(**transform_args)
    transforms = _transforms
    logger.debug('Calculated transforms')

    # Write output
    nbands = len(transforms.keys())
    out_ds = driver.Create(dst, ds.RasterXSize, ds.RasterYSize, nbands,
                           gdal_dtype)
    metadata = {}
    for i_b, (name, array) in enumerate(six.iteritems(transforms)):
        r_band = out_ds.GetRasterBand(i_b + 1)
        array[mask] = nodata
        r_band.WriteArray(array)
        r_band.SetDescription(name)
        r_band.SetNoDataValue(nodata)
        metadata['Band_' + str(i_b + 1)] = name

    out_ds.SetMetadata(metadata)
    out_ds.SetProjection(ds.GetProjection())
    out_ds.SetGeoTransform(ds.GetGeoTransform())
    logger.debug('Complete')

if __name__ == '__main__':
    create_transform()
