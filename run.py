#!/usr/bin/env python3

from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from datetime import date
import pymongo
from time import sleep
import sys
from diff.arguments import Arguments
from diff.get_data import getData
from diff.licenses import Licenses
from diff.seats import Seats
from update_dbs import config as cfg


# get today's date
today = date.today()
today_date = today.strftime('%m-%d-%Y')

logger = getLogger('run')
# TODO: set to ERROR later on after setup
logger.setLevel(DEBUG)

file_formatter = Formatter('{asctime} {name} {levelname}: {message}', style='{')
stream_formatter = Formatter('{message}', style='{')
today = date.today()

# logfile
file_handler = FileHandler('/opt/Software_Inventory/logs/software_inventory{}.log'
                           .format(today.strftime('%m%d%Y')))
file_handler.setLevel(DEBUG)
file_handler.setFormatter(file_formatter)

# console
stream_handler = StreamHandler()
stream_handler.setFormatter(stream_formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

client = pymongo.MongoClient("mongodb://localhost:27017/")
software_db = client['software_inventory']
# Snipe Seats collection
snipe_seats = software_db['snipe_seat']
snipe_lic_col = software_db['snipe_lic']
lic_w_ct_col = software_db['licenses_w_count']


def run(args):

    arg_assets = []
    arg_licenses = []
    arg_diff = []
    if args:
        for item in args:
            if item['func_type'] == 'asset':
                arg_assets.append(item['argument'])
            if item['func_type'] == 'license':
                arg_licenses.append(item['argument'])
            if item['func_type'] == 'diff':
                arg_diff.append(item['argument'])

    if len(arg_assets) == 0:
        arg_assets = None
    if len(arg_licenses) == 0:
        arg_licenses = None
        lic_args = None

    get_data_obj = getData()
    lic_obj = Licenses()
    seat_obj = Seats()

    # if no arguments provided get a list of all asset info
    if not arg_licenses and not arg_assets:
        get_data_obj.get_all_assets()


    # get lists of dicts of asset info from asset arguments
    if arg_assets:
        get_data_obj.get_asset_list(arg_assets)

    # INFORMATION RETURNED PER LICENSE IF DIFF ARGS
    # displays the differences for one license
    # if provided in args
    if len(arg_diff) != 0:
        lic_obj.get_license_lists(arg_diff)
        lic_obj.seat_duplicates()
        get_data_obj.get_lic_list(arg_diff)
        for item in get_data_obj.arg_licenses:
            license_args = lic_w_ct_col.find_one(
                {'sw': item})
            lic_obj.get_lic_seats_rem(license_args)
            lic_obj.get_lic_seats_add(license_args)
        sys.exit()

    # UPDATE WITH LICENSE ARGS
    if arg_licenses:
        get_data_obj.get_lic_list(arg_licenses)
        lic_obj.get_license_lists(get_data_obj.arg_licenses)
        lic_obj.seat_duplicates()
        seat_obj.check_in(lic_obj.seat_dups)
        # find licenses that need to be checked-in our checked-out to assets
        lic_obj.get_licenses_update(lic_obj.lic_arguments)
        lic_obj.get_licenses_delete(lic_obj.lic_arguments)
        if len(lic_obj.upd_licenses) > 0:
            for upd_lic in lic_obj.upd_licenses:
                # updating licenses with the right numbers
                lic_obj.update_license(upd_lic)
        if len(lic_obj.lic_arguments) > 0:
            for license in lic_obj.lic_arguments:
                logger.debug('\n\n---------------------{}----------------------'
                     .format(license['sw']))
                lic_obj.get_lic_seats_rem(license)
                seat_obj.check_in(lic_obj.seats_rem)
                lic_obj.get_lic_seats_add(license)
                seat_obj.check_out(lic_obj.seats_add)

                lic_obj.get_lic_seats_del(license)
                if license in lic_obj.del_licenses:
                    lic_obj.get_lic_seats_del(del_lic)
                    seat_obj.check_in(lic_obj.seats_rem)
                    # lic_obj.delete_license(license)
        sys.exit()

    # NEW LICENSES CREATE
    # get lists of licenses from bigfix and snipe
    # argument passed if license argument is provided
    lic_obj.get_license_lists(lic_args)
    # find new licenses
    lic_obj.get_licenses_new(lic_obj.lic_arguments)
    new_lic_ct = 0
    for license in lic_obj.new_licenses:
        # push changes to SnipeIT API and update MongoDB
        if new_lic_ct == 118:
            sleep(60)
            new_lic_ct = 0
        lic_obj.create_license(license)
        new_lic_ct += 1
        # get all seat information for new licenses
        lic_obj.get_lic_seats_new(license)
        seat_obj.check_out(lic_obj.seats_add)

    # UPDATE
    upd_lic_ct = 0
    lic_obj.seat_duplicates()
    seat_obj.check_in(lic_obj.seat_dups)
    lic_obj.get_license_lists()
    # get licenses that had any changes in seat numers
    lic_obj.get_licenses_update()
    for upd_lic in lic_obj.upd_licenses:
        # add sleep to prevent API errors
        if upd_lic_ct == 118:
            sleep(60)
            upd_lic_ct = 0
        # updating licenses with the right numbers
        lic_obj.update_license(upd_lic)
        upd_lic_ct += 1
    for license in lic_obj.bigfix_licenses:
        logger.debug('\n\n---------------------{}----------------------'
                     .format(license['sw']))
        lic_obj.get_lic_seats_rem(license)
        seat_obj.check_in(lic_obj.seats_rem)
        lic_obj.get_lic_seats_add(license)
        seat_obj.check_out(lic_obj.seats_add)

    # DELETE
    lic_obj.get_licenses_delete(lic_obj.lic_arguments)
    del_lic_ct = 0
    for license in lic_obj.del_licenses:
        lic_obj.get_lic_seats_del(license)
        seat_obj.check_in(lic_obj.seats_rem)
        if del_lic_ct == 118:
            sleep(60)
            del_lic_ct = 0
        # lic_obj.delete_license(license)
        del_lic_ct += 1


if __name__ == '__main__':
    args_obj = Arguments()
    args_obj.inv_args()
    args = args_obj.arguments
    run(args)
