#!/usr/bin/env python3

import pymongo
from time import sleep
import sys
from diff.arguments import Arguments
from diff.get_data import getData
from diff.licenses import Licenses
from diff.seats import Seats

client = pymongo.MongoClient("mongodb://localhost:27017/")
software_db = client['software_inventory']
# Snipe Seats collection
snipe_seats = software_db['snipe_seat']
snipe_lic_col = software_db['snipe_lic']


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

    # displays the differences for one license
    # if provided in args
    if len(arg_diff) != 0:
        lic_obj.get_license_lists(arg_diff)
        get_data_obj.get_lic_list(arg_diff)
        lic_args = get_data_obj.arg_licenses
        lic_obj.get_lic_seats_update(lic_args[0])
        sys.exit()

    # if no arguments provided get a list of all asset info
    if not arg_licenses and not arg_assets:
        get_data_obj.get_all_assets()

    # if license arguments provided, get list of assets
    # associated with those licenses
    if arg_licenses:
        get_data_obj.get_lic_list(arg_licenses)
        lic_args = get_data_obj.arg_licenses

    # get lists of dicts of asset info from asset arguments
    if arg_assets:
        get_data_obj.get_asset_list(arg_assets)

    # get lists of licenses from bigfix and snipe
    # argument passed if license argument is provided
    lic_obj.get_license_lists(lic_args)
    # find new licenses
    lic_obj.get_licenses_new(lic_obj.lic_arguments)
    seat_obj = Seats()
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

    if arg_licenses:
        # find licenses that need to be checked-in our checked-out to assets
        lic_obj.get_licenses_update(lic_obj.lic_arguments)
        if len(lic_obj.lic_arguments) > 0:
            for item in lic_obj.lic_arguments:
                lic_obj.get_lic_seats_update(item['sw'])
                seat_obj.check_out(lic_obj.seats_add)
                seat_obj.check_in(lic_obj.seats_rem)

    upd_lic_ct = 0
    for license in lic_obj.bigfix_licenses:
        # add sleep to prevent API errors
        if upd_lic_ct == 118:
            sleep(60)
            upd_lic_ct = 0
        # get licenses that had any changes in seat numers
        lic_obj.get_licenses_update()
        lic_obj.update_license(license)
        upd_lic_ct += 1
        # for the updated licenses, get seats to check-in or check-out
        lic_obj.get_lic_seats_update(license)
        seat_obj.check_out(lic_obj.seats_add)
        seat_obj.check_in(lic_obj.seats_rem)

    # find licenses that need to be deleted
    lic_obj.get_licenses_delete(lic_obj.lic_arguments)
    del_lic_ct = 0
    for license in lic_obj.del_licenses:
        lic_obj.get_lic_seats_del(license)
        seat_obj.check_in(lic_obj.seats_rem)
        print(lic_obj.del_license)
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
