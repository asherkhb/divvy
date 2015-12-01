import os
import csv
import json
from os import path, system

import astropy.io.fits as fits

__author__ = "Daniel Kapellusch, Asher Baltzell"


# Hopefully this will be gone soon
def set_config_vals(**optional_args):
    global max_processes, file_shifts, darkmaster, darksub, fitscent

    max_processes = optional_args["max_processes"]  # assign globals
    file_shifts = optional_args["file_shifts"]
    darkmaster = optional_args["darkmaster"]
    darksub = optional_args["darksub"]
    fitscent = optional_args["fitscent"]


def get_metadata_and_sort(image):
    with fits.open(image) as hdulist:
        header = hdulist[0].header  # get all the metadata from the fits file hdulist
    header["FILENAME"] = path.basename(image)
    return {key: value for key, value in header.items()  # remove comment field
            if key is not "COMMENT"}


def make_tsv(header, items, outputfname):
    with open(outputfname + ".tsv", "wb") as csvfile:  # create a file called metadata.tsv for the output
        # set up the writer, header fields, and delimiter
        writer = csv.DictWriter(csvfile, fieldnames=items, delimiter="\t")
        writer.writeheader()  # write the headers to the file
        [writer.writerow({k: str(image[k]) for k in items}) for image in header]


def build_json(total_dic, outputfname):
    with open(outputfname + ".json", 'w') as jsonfile:  # builds json file of metadata not sorted by VIMTYPE
        json.dump(total_dic, jsonfile, separators=(',', ':'), indent=4)


def sort_dic(total_dic):
    # sort total_dic into dictionary by VIMTYPE
    sorted_dic = {"SCIENCE": [], "DARK": []}
    [sorted_dic["SCIENCE"].append(total_dic[i]["FILENAME"]) if total_dic[i]["VIMTYPE"] == "SCIENCE"
     else sorted_dic["DARK"].append(total_dic[i]["FILENAME"]) for i in total_dic]
    return sorted_dic


def clean_dic(sorted_dic, total_dic):
    cleaned_dic = {'SCIENCE': [], "DARK": sorted_dic["DARK"]}
    for image in sorted_dic["SCIENCE"]:  # Search dictionary built by my other script
        if total_dic[image]["AOLOOPST"] == "CLOSED":
            cleaned_dic["SCIENCE"].append(image)  # store names of good files
    return cleaned_dic  # return those names


def writeListCfg(lst, cfgname):
    """
    Write out a config file from a list.
    - Entries: 'listItem\n'
    :param lst: List to be written as a config file.
    :param cfgname: Filename or path/to/filename for config file.
    :return: Config filename or path/to/filename
    """
    cfg_out = open(cfgname, 'w')
    for e in lst:
        cfg_out.write(str(e) + '\n')
    cfg_out.close()
    return cfgname


def writeDictCfg(dct, cfgname):
    """
    Write out a config file from a dictionary.
    - Entries: 'key=value\n'
    :param dct: Dictionary to be written as a config file.
    :param cfgname: Filename or path/to/filename for config file.
    :return: Config filename or path/to/filename
    """
    cfg_out = open(cfgname, 'w')
    for k, v in dct.iteritems():
        cfg_out.write('%s=%s\n' % (str(k), str(v)))
    cfg_out.close()
    return cfgname


def runDarkmaster(image_path, image_dict, darklist_filename, masterdark_filename, norm_filename,
                  bot_xo=None, bot_xf=None, bot_yo=None, bot_yf=None,
                  top_xo=None, top_xf=None, top_yo=None, top_yf=None,
                  width=None, height=None,
                  config=None, medianNorm=False, medianDark=False):
    print("Running DarkMaster")

    global darkmaster

    # Write dark images to config file.
    darks = [image_path + '/' + image for image in image_dict['DARK']]
    writeListCfg(darks, darklist_filename)
    # Fill out required parameters
    options = '--fileListFile=%s --darkFileName=%s --normFileName=%s' % (darklist_filename,
                                                                         masterdark_filename,
                                                                         norm_filename)
    # Fill out bottom/top normalization coordinates, if present.
    if bot_xo and bot_xf and bot_yo and bot_yf and top_xo and top_xf and top_yo and top_yf:
        options += ' --bot_xo=%s --bot_xf=%s --bot_yo=%s --bot_yf=%s' % (str(bot_xo), str(bot_xf),
                                                                         str(bot_yo), str(bot_yf))
        options += ' --top_xo=%s --top_xf=%s --top_yo=%s --top_yf=%s' % (str(top_xo), str(top_xf),
                                                                         str(top_yo), str(top_yf))
    # Fill out height/width of centered normalization region (overrides normalization coordinates), if present.
    if width and height:
        options += ' --width=%s --height=%s' % (str(width), str(height))
    # Add median options, if present
    if medianNorm:
        options += ' --medianNorm'
    if medianDark:
        options += ' --medianDark'
    # Build & call darkmaster command.
    cmd = darkmaster + ' ' + options
    print cmd
    system(cmd)
    return 1


def prependToFilename(filename, prepending):
    """
    Prepend Text to Filename.
    :param filename: Filename or path/to/filename to be modified.
    :param prepending: String to prepend to filename.
    :return: Modified filename or path/to/filename.
    """
    b = os.path.basename(filename)
    n = prepending + b
    return filename.replace(b, n)


def spawnDsubCmd(science_img, dark_img, norm_bot=None, norm_top=None):
    """
    Spawn a darksub command.
    :param science_img: Science image filename or path/to/filename.
    :param dark_img: Master dark filename or path/to/filename.
    :param norm_bot: Multiplicative scaling to apply to the bottom amplifier (optional).
    :param norm_top: Multiplicative scaling to apply to the top amplifier (optional).
    :return: darksub_command, subtracted_fiilename
    """
    dsub_out = prependToFilename(science_img, 'dsub_')
    dsub_opts = '--inputFile=%s --darkFile=%s --outputFile=%s' % (science_img, dark_img, dsub_out)
    if norm_bot:
        dsub_opts += ' --norm_bot=%s' % str(norm_bot)
    if norm_top:
        dsub_opts += ' --norm_top=%s' % str(norm_top)
    dsub_cmd = darksub + ' ' + dsub_opts
    return dsub_cmd, dsub_out


def spawnCentCmd(subtracted_img, xshift, yshift):
    """
    Spawn a fitscent command.
    :param subtracted_img: Dark subtracted science image.
    :param xshift: X shift to apply to image.
    :param yshift: Y shift to apply to image.
    :return: fitscent_command, centered_filename
    """
    cent_out = prependToFilename(subtracted_img, 'cent_')
    cent_opts = '--input=%s --x=%s --y=%s --output=%s' % (subtracted_img, str(xshift), str(yshift), cent_out)
    cent_cmd = fitscent + ' ' + cent_opts
    return cent_cmd, cent_out


def loadShifts(shifts_file):
    shifts = {}
    with open(shifts_file, 'r') as s:
        for l in s:
            c = l.split()
            shifts[c[0]] = {'x': c[1], 'y': c[2]}
    return shifts


def getNorms(img):  # TODO
    """

    :param img: Image to obtain normalization s for.
    :return:
    """
    top = ''
    bot = ''
    return top, bot


def getShifts(img, fileshifts):  # TODOr
    """

    :param img: image to get shift values
    :return: xshift, yshift
    """
    try:
        xs = fileshifts[img]['x']
        ys = fileshifts[img]['y']
        return xs, ys
    except KeyError:
        print "Warning (getShifts): %s not found in fileshifts" % str(img)
        return 0, 0


def runProcess(call):
    print call
    os.system(call)
    return 1


def subtractAndCenter(image_path, image_dict, masterdark, shifts_file):
    global max_processes
    print("Subtracting and Centering")
    # Build list of science images to process.
    sciences = [image_path + '/' + image for image in image_dict['SCIENCE']]
    # Load shift values from file to memory.
    fileshifts = loadShifts(shifts_file)
    # Define necessary variables.
    scmds = []
    souts = []
    ccmds = []
    couts = []

    failures = 0
    # Build up commands for each science image.
    for img in sciences:
        # Get norm and shift values.
        tnorm, bnorm = getNorms(img)
        xshift, yshift = getShifts(os.path.basename(img), fileshifts)
        if xshift == 0 and yshift == 0:
            failures += 1

        # Build subtraction task.
        ds_cmd, ds_out = spawnDsubCmd(img, masterdark, norm_bot=bnorm, norm_top=tnorm)
        # subtractions[img] = {'cmd': ds_cmd, 'out': ds_out}
        scmds.append(ds_cmd)
        souts.append(ds_out)

        # Build centering task.
        cn_cmd, cn_out = spawnCentCmd(ds_out, xshift=xshift, yshift=yshift)
        # centerings[img] = {'cmd': cn_cmd, 'out': cn_out}
        ccmds.append(cn_cmd)
        couts.append(cn_out)
    print len(sciences)
    print failures
    # Execute subtraction tasks (parallel).
    # sub_pool = mp.Pool(processes=max_processes)
    # print max_processes
    # sub_pool.map(runProcess, scmds)

    # Execute subtraction tasks (serial).
    for c in scmds:
        runProcess(c)

    # Execute centering tasks (parallel).
    # cent_pool = mp.Pool(processes=max_processes)
    # cent_pool.map(runProcess, ccmds)

    for c in ccmds:
        runProcess(c)

    # Return list of final filenames.
    return couts
