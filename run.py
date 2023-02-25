#!/usr/bin/env python3

import pymongo
from diff.arguments import Arguments
from diff.get_data import getData
from diff.licenses import Licenses

client = pymongo.MongoClient("mongodb://localhost:27017/")
software_db = client['software_inventory']
# Snipe Seats collection
snipe_seats = software_db['snipe_seat']


def run(args):

    arg_assets = []
    arg_licenses = []
    if args:
        for item in args:
            if item['func_type'] == 'asset':
                arg_assets.append(item['argument'])
            if item['func_type'] == 'license':
                arg_licenses.append(item['argument'])

    if len(arg_assets) == 0:
        arg_assets = None
    if len(arg_licenses) == 0:
        arg_licenses = None
        lic_args = None

    get_data_obj = getData()
    lic_obj = Licenses()

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
    lic_obj.get_licenses_create()
    # find licenses that need to be checked-in our checked-out to assets
    lic_obj.get_licenses_update()
    # find licenses that need to be deleted
    lic_obj.get_licenses_delete()
    # push changes to SnipeIT API and update MongoDB
    lic_obj.create_license()
    # get all seat information for new licenses
    lic_obj.get_lic_seats_new()
    
    lic_obj.update_license()
    lic_obj.delete_license()


if __name__ == '__main__':
    args_obj = Arguments()
    args_obj.inv_args()
    args = args_obj.arguments
    run(args)
