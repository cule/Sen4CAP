#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
_____________________________________________________________________________

   Program:      Sen2Agri-Processors
   Language:     Python
   Copyright:    2015-2016, CS Romania, office@c-s.ro
   See COPYRIGHT file for details.

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
_____________________________________________________________________________

"""
from __future__ import print_function
import argparse
import re
import glob
import gdal
import osr
import lxml.etree
from lxml.builder import E
import math
import os
from os.path import isdir, join
import sys
from signal import signal, SIGINT, SIG_IGN
from multiprocessing import Pool, TimeoutError
from sen2agri_common_db import GetExtent, ReprojectCoords, create_recursive_dirs, run_command


def resample_dataset(src_file_name, dst_file_name, dst_spacing_x, dst_spacing_y):
    print("{}|{}|{}|{}".format(src_file_name, dst_file_name, dst_spacing_x, dst_spacing_y))
    dataset = gdal.Open(src_file_name, gdal.gdalconst.GA_ReadOnly)

    src_x_size = dataset.RasterXSize
    src_y_size = dataset.RasterYSize

    print("Source dataset {} of size {}x{}".format(src_file_name, src_x_size, src_y_size))

    src_geo_transform = dataset.GetGeoTransform()
    (ulx, uly) = (src_geo_transform[0], src_geo_transform[3])
    (lrx, lry) = (src_geo_transform[0] + src_geo_transform[1] * src_x_size,
                  src_geo_transform[3] + src_geo_transform[5] * src_y_size)

    print("Source coordinates ({}, {})-({},{})".format(ulx, uly, lrx, lry))

    dst_x_size = int(round((lrx - ulx) / dst_spacing_x))
    dst_y_size = int(round((lry - uly) / dst_spacing_y))

    print("Destination dataset {} of size {}x{}".format(dst_file_name, dst_x_size, dst_y_size))

    dst_geo_transform = (ulx, dst_spacing_x, src_geo_transform[2],
                         uly, src_geo_transform[4], dst_spacing_y)

    (ulx, uly) = (dst_geo_transform[0], dst_geo_transform[3])
    (lrx, lry) = (dst_geo_transform[0] + dst_geo_transform[1] * dst_x_size,
                  dst_geo_transform[3] + dst_geo_transform[5] * dst_y_size)
    print("Destination coordinates ({}, {})-({},{})".format(ulx, uly, lrx, lry))

    drv = gdal.GetDriverByName('GTiff')
    dest = drv.Create(dst_file_name, dst_x_size, dst_y_size, 1, gdal.GDT_Float32)
    dest.SetGeoTransform(dst_geo_transform)
    dest.SetProjection(dataset.GetProjection())
    gdal.ReprojectImage(dataset, dest, dataset.GetProjection(), dest.GetProjection(),
                        gdal.GRA_Bilinear)


def get_dtm_tiles(points):
    """
    Returns a list of dtm tiles covering the given extent
    """
    a_x, a_y, b_x, b_y = points

    if a_x < b_x and a_y > b_y:
        a_bb_x = int(math.floor(a_x / 5) * 5)
        a_bb_y = int(math.floor((a_y + 5) / 5) * 5)
        b_bb_x = int(math.floor((b_x + 5) / 5) * 5)
        b_bb_y = int(math.floor(b_y / 5) * 5)

        print("bounding box {} {} {} {}".format(
            a_bb_x, a_bb_y, b_bb_x, b_bb_y))

        x_numbers_list = [(x + 180) / 5 + 1
                          for x in range(min(a_bb_x, b_bb_x), max(a_bb_x, b_bb_x), 5)]
        x_numbers_list_format = ["%02d" % (x,) for x in x_numbers_list]

        y_numbers_list = [(60 - x) / 5
                          for x in range(min(a_bb_y, b_bb_y), max(a_bb_y, b_bb_y), 5)]
        y_numbers_list_format = ["%02d" % (x,) for x in y_numbers_list]

        srtm_zips = ["srtm_" + str(x) + "_" + str(y) + ".tif"
                     for x in x_numbers_list_format
                     for y in y_numbers_list_format]

        return srtm_zips


#def run_command(args):
#    print(" ".join(map(pipes.quote, args)))
#    subprocess.call(args)


def get_landsat_tile_id(image):
    m = re.match("[A-Z][A-Z]\d(\d{6})\d{4}\d{3}[A-Z]{3}\d{2}_B\d{1,2}\.TIF", image)
    return m and ('L8', m.group(1))


def get_sentinel2_tile_id(image):
    m = re.match("\w+_T(\w{5})_B\d{2}\.\w{3}|T(\w{5})_\d{8}T\d{6}_B\d{2}.\w{3}", image)
    return m and ('S2', m.group(1) or m.group(2))


def get_tile_id(image):
    name = os.path.basename(image)
    return get_landsat_tile_id(name) or get_sentinel2_tile_id(name)


def get_landsat_dir_info(name):
    m = re.match("[A-Z][A-Z]\d\d{6}(\d{4}\d{3})[A-Z]{3}\d{2}", name)
    return m and ('L8', m.group(1))


def get_sentinel2_dir_info(name):
    m = re.match("S2A\w+_(\d{8}T\d{6})\w+.SAFE", name)

    return m and ('S2', m.group(1))


def get_dir_info(dir_name):
    name = os.path.basename(dir_name)
    return get_sentinel2_dir_info(name) or get_landsat_dir_info(name)


class Context(object):

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def format_filename(mode, output_directory, tile_id, suffix):
    filename_template = "{0}_TEST_AUX_REFDE2_{1}_0001_{2}.TIF"

    return filename_template.format(mode, tile_id, suffix)


def create_context(args):
    dir_base = args.input
    if not os.path.exists(dir_base) or not os.path.isdir(dir_base):
        print("The path does not exist ! {}".format(dir_base))
        return []
    log_path = dir_base
    if dir_base.rfind('/') + 1 == len(dir_base):
        dir_base = dir_base[0:len(dir_base)-1]
    mode, date = get_dir_info(dir_base)
    context_array = []
    #if mode == None:
        #print("Error in reading directory, is not in S2 neither L8 format")
        #return context_array

    images = []
    tiles_to_process = []
    if args.tiles_list is not None:
        tiles_to_process = args.tiles_list
    if mode == 'L8':
        images.append("{}/{}_B1.TIF".format(dir_base, os.path.basename(dir_base)))
    elif mode == 'S2':
        dir_base += "/GRANULE/"
        if not os.path.exists(dir_base) or not os.path.isdir(dir_base):
            log(log_path, "The path for Sentinel 2 (with GRANULE) does not exist ! {}".format(dir_base), "dem.log")
            return []
        tile_dirs = ["{}{}".format(dir_base, f) for f in os.listdir(dir_base) if isdir(join(dir_base, f))]
        for tile_dir in tile_dirs:
            tile_dir += "/IMG_DATA/"
            image_band2 = glob.glob("{}*_B02.jp2".format(tile_dir))
            if len(image_band2) == 1:
                if len(tiles_to_process) > 0:
                    mode_f, tile_id = get_tile_id(image_band2[0])
                    if tile_id in tiles_to_process:
                        images.append(image_band2[0])
                else:
                    images.append(image_band2[0])
    else:
        return context_array
    for image_filename in images:
        mode, tile_id = get_tile_id(image_filename)

        dataset = gdal.Open(image_filename, gdal.gdalconst.GA_ReadOnly)

        size_x = dataset.RasterXSize
        size_y = dataset.RasterYSize

        geo_transform = dataset.GetGeoTransform()

        spacing_x = geo_transform[1]
        spacing_y = geo_transform[5]

        extent = GetExtent(geo_transform, size_x, size_y)

        source_srs = osr.SpatialReference()
        source_srs.ImportFromWkt(dataset.GetProjection())
        epsg_code = source_srs.GetAttrValue("AUTHORITY", 1)
        target_srs = osr.SpatialReference()
        target_srs.ImportFromEPSG(4326)

        wgs84_extent = ReprojectCoords(extent, source_srs, target_srs)

        directory_template = "{0}_TEST_AUX_REFDE2_{1}_{2}_0001.DBL.DIR"
        if not create_recursive_dirs(args.output):
            return context_array
        image_directory = os.path.join(args.output, directory_template.format(mode, tile_id, date))
        if not create_recursive_dirs(args.working_dir):
            return context_array
        temp_directory = os.path.join(args.working_dir, directory_template.format(mode, tile_id, date))

        metadata_template = "{0}_TEST_AUX_REFDE2_{1}_{2}_0001.HDR"

        d = dict(image=image_filename,
                 mode=mode,
                 srtm_directory=args.srtm,
                 swbd_directory=args.swbd,
                 working_directory=args.working_dir,
                 temp_directory=temp_directory,
                 output=args.output,
                 image_directory=image_directory,
                 metadata_file=os.path.join(args.output, metadata_template.format(mode, tile_id, date)),
                 swbd_list=os.path.join(temp_directory, "swbd.txt"),
                 tile_id=tile_id,
                 dem_vrt=os.path.join(temp_directory, "dem.vrt"),
                 dem_nodata=os.path.join(temp_directory, "dem.tif"),
                 dem_coarse=os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                     "ALC")),
                 slope_degrees=os.path.join(temp_directory, "slope_degrees.tif"),
                 aspect_degrees=os.path.join(temp_directory, "aspect_degrees.tif"),
                 slope_coarse=os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                     "SLC")),
                 aspect_coarse=os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                     "ASC")),
                 wb=os.path.join(temp_directory, "wb.shp"),
                 wb_reprojected=os.path.join(
                     temp_directory, "wb_reprojected.shp"),
                 water_mask=os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                     "MSK")),
                 size_x=size_x, size_y=size_y,
                 spacing_x=spacing_x, spacing_y=spacing_y,
                 extent=extent, wgs84_extent=wgs84_extent,
                 epsg_code=epsg_code)

        if mode == 'L8':
            d['dem_r1'] = os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                "ALT"))
            d['slope_r1'] = os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                "SLP"))
            d['aspect_r1'] = os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                "ASP"))

            d['dem_r2'] = None
            d['slope_r2'] = None
            d['aspect_r2'] = None
        else:
            d['dem_r1'] = os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                "ALT_R1"))
            d['dem_r2'] = os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                "ALT_R2"))
            d['slope_r1'] = os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                "SLP_R1"))
            d['slope_r2'] = os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                "SLP_R2"))
            d['aspect_r1'] = os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                "ASP_R1"))
            d['aspect_r2'] = os.path.join(image_directory, format_filename(mode, image_directory, tile_id,
                "ASP_R2"))

        context_array.append(Context(**d))
    return context_array


def create_metadata(context):
    file_names = [context.dem_r1, context.dem_r2, context.dem_coarse,
                  context.slope_r1, context.slope_r2, context.slope_coarse,
                  context.aspect_r1, context.aspect_r2, context.aspect_coarse,
                  context.water_mask]

    files = []
    index = 1
    for f in file_names:
        if f is not None:
            files.append(
                    E.Packaged_DBL_File(
                        E.Relative_File_Path(os.path.relpath(f, context.output)),
                        sn=str(index)))
            index = index + 1
    mission = "LANDSAT_8"
    if context.mode == 'S2':
        mission = "SENTINEL-2_"

    return E.Earth_Explorer_Header(
            E.Fixed_Header(
                E.Mission(mission),
                E.File_Type('AUX_REFDE2')),
            E.Variable_Header(
                E.Specific_Product_Header(
                    E.DBL_Organization(
                        E.List_of_Packaged_DBL_Files(
                            *files,
                            count=str(len(files)))))))

def process_DTM(context):
    if abs(context.spacing_x) > abs(context.spacing_y):
        grid_spacing = abs(context.spacing_x)
    else:
        grid_spacing = abs(context.spacing_y)

    dtm_tiles = get_dtm_tiles([context.wgs84_extent[0][0],
                               context.wgs84_extent[0][1],
                               context.wgs84_extent[2][0],
                               context.wgs84_extent[2][1]])

    dtm_tiles = [os.path.join(context.srtm_directory, tile)
                 for tile in dtm_tiles]

    missing_tiles = []
    for tile in dtm_tiles:
        if not os.path.exists(tile):
            missing_tiles.append(tile)

    if missing_tiles:
        print("The following SRTM tiles are missing: {}. Please provide them in the SRTM directory ({}). Will try to continue, but unreliable results".format(
            [os.path.basename(tile) for tile in missing_tiles], context.srtm_directory))
#        return False

    run_command(["gdalbuildvrt", "-q",
                 context.dem_vrt] + dtm_tiles)
    run_command(["otbcli_BandMath",
                 "-il", context.dem_vrt,
                 "-out", context.dem_nodata,
                 "-exp", "im1b1 == -32768 ? 0 : im1b1",
                 "-progress", "false"])
    run_command(["gdalwarp", "-q", "-overwrite", "-multi",
                 "-r", "cubic",
                 "-t_srs", "EPSG:" + str(context.epsg_code),
                 "-tr", str(context.spacing_x), str(context.spacing_y),
                 "-te", str(context.extent[1][0]), str(context.extent[1][1]), str(context.extent[3][0]), str(context.extent[3][1]),
                 context.dem_nodata, context.dem_r1])

    if context.dem_r2:
        # run_command(["gdal_translate",
        #              "-outsize", str(int(round(context.size_x / 2.0))), str(int(round(context.size_y
        #                                                                               / 2.0))),
        #              context.dem_r1,
        #              context.dem_r2])
        resample_dataset(context.dem_r1, context.dem_r2, 20, -20)
        # run_command(["otbcli_RigidTransformResample",
        #              "-in", context.dem_r1,
        #              "-out", context.dem_r2,
        #              "-transform.type.id.scalex", "0.5",
        #              "-transform.type.id.scaley", "0.5"])

    if context.mode == 'L8':
        scale = 1.0 / 8
        inv_scale = 8.0
    else:
        # scale = 1.0 / 23.9737991266  # almost 1/24
        scale = 1.0 / 24
        inv_scale = 24.0

    # run_command(["gdal_translate",
    #              "-outsize", str(int(round(context.size_x / inv_scale))), str(int(round(context.size_y /
    #                                                                                     inv_scale))),
    #              context.dem_r1,
    #              context.dem_coarse])
    resample_dataset(context.dem_r1, context.dem_coarse, 240, -240)
    # run_command(["otbcli_RigidTransformResample",
    #              "-in", context.dem_r1,
    #              "-out", context.dem_coarse,
    #              "-transform.type.id.scalex", str(scale),
    #              "-transform.type.id.scaley", str(scale)])

    run_command(["gdaldem", "slope", "-q",
                 # "-s", "111120",
                 "-compute_edges",
                 context.dem_r1,
                 context.slope_degrees])
    run_command(["gdaldem", "aspect", "-q",
                 # "-s", "111120",
                 "-compute_edges",
                 context.dem_r1,
                 context.aspect_degrees])

    run_command(["gdal_translate", "-q",
                 "-ot", "Int16",
                 "-scale", "0", "90", "0", "157",
                 context.slope_degrees,
                 context.slope_r1])
    run_command(["gdal_translate", "-q",
                 "-ot", "Int16",
                 "-scale", "0", "368", "0", "628",
                 context.aspect_degrees,
                 context.aspect_r1])

    if context.slope_r2:
        run_command(["gdalwarp", "-q",
                     "-r", "cubic",
                     "-tr", "20", "20",
                     context.slope_r1, context.slope_r2])

    if context.aspect_r2:
        run_command(["gdalwarp", "-q",
                     "-r", "cubic",
                     "-tr", "20", "20",
                     context.aspect_r1, context.aspect_r2])

    run_command(["gdalwarp", "-q",
                 "-r", "cubic",
                 "-tr", "240", "240",
                 context.slope_r1, context.slope_coarse])

    run_command(["gdalwarp", "-q",
                 "-r", "cubic",
                 "-tr", "240", "240",
                 context.aspect_r1, context.aspect_coarse])

    return True

def process_WB(context):
    run_command(["otbcli",
                 "DownloadSWBDTiles",
                 "-il", context.dem_r1,
                 "-mode", "list",
                 "-mode.list.indir", context.swbd_directory,
                 "-mode.list.outlist", context.swbd_list,
                 "-progress", "false"])

    with open(context.swbd_list) as f:
        swbd_tiles = f.read().splitlines()

    if len(swbd_tiles) == 0:
        empty_shp = os.path.join(context.swbd_directory, "empty.shp")
        run_command(["ogr2ogr", context.wb, empty_shp])
    elif len(swbd_tiles) == 1:
        run_command(["ogr2ogr", context.wb, swbd_tiles[0]])
    else:
        run_command(["otbcli_ConcatenateVectorData",
                     "-progress", "false",
                     "-out", context.wb,
                     "-vd"] + swbd_tiles)

    run_command(["ogr2ogr",
                 "-s_srs", "EPSG:4326",
                 "-t_srs", "EPSG:" + context.epsg_code,
                 context.wb_reprojected,
                 context.wb])

    run_command(["otbcli_Rasterization",
                 "-in", context.wb_reprojected,
                 "-out", context.water_mask, "uint8",
                 "-im", context.dem_coarse,
                 "-mode.binary.foreground", "1",
                 "-progress", "false"])


def change_extension(file, new_extension):
    return os.path.splitext(file)[0] + new_extension


def process_context(context):
    try:
        os.makedirs(context.image_directory)
    except:
        pass
    try:
        os.makedirs(context.temp_directory)
    except:
        pass
    metadata = create_metadata(context)
    with open(context.metadata_file, 'w') as f:
        lxml.etree.ElementTree(metadata).write(f, pretty_print=True)

    if process_DTM(context) == False:
        return
    process_WB(context)

    files = [context.swbd_list, context.dem_vrt, context.dem_nodata, context.slope_degrees,
            context.aspect_degrees, context.wb, context.wb_reprojected]

    for file in [context.wb, context.wb_reprojected]:
        for extension in [".shx", ".prj", ".dbf"]:
            files.append(change_extension(file, extension))

    for file in files:
        try:
            os.remove(file)
        except:
            pass

    try:
        os.rmdir(context.temp_directory)
    except:
        print("Couldn't remove the temp dir {}".format(context.temp_directory))


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Creates DEM and WB data for MACCS")
    parser.add_argument('input', help="input L1C directory")
    parser.add_argument('--srtm', required=True, help="SRTM dataset path")
    parser.add_argument('--swbd', required=True, help="SWBD dataset path")
    parser.add_argument('-l', '--tiles-list', required=False, nargs='+', help="If set, only these tiles will be processed")
    parser.add_argument('-w', '--working-dir', required=True,
                        help="working directory")
    parser.add_argument('-p', '--processes-number', required=False,
                        help="number of processed to run", default="3")
    parser.add_argument('output', help="output location")

    args = parser.parse_args()

    return int(args.processes_number), create_context(args)

proc_number, contexts = parse_arguments()

if len(contexts) == 0:
    print("No context could be created")
    sys.exit(-1)

try:
    p = Pool(int(proc_number), lambda: signal(SIGINT, SIG_IGN))
    res = p.map_async(process_context, contexts)
    while True:
        try:
            res.get(1)
            break
        except TimeoutError:
            pass
    p.close()
except KeyboardInterrupt:
    p.terminate()
    p.join()
