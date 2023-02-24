#!/usr/bin/env python3

import pymongo
from diff.args import getArguments
from diff.get_data import getData
from diff.license import License

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
        sw_license_list = None

    # create an instance of getAssets class
    asset_obj = getData()
    create_lic_obj = License()

    asset_list = []
    # if no arguments provided get a list of all asset info
    if not arg_licenses and not arg_assets:
        asset_list = asset_obj.get_all_assets()

    # if license arguments provided, get list of assets
    # associated with those licenses
    if arg_licenses:
        asset_obj.get_lic_list(arg_licenses)
        sw_asset_list = asset_obj.asset_list_sw
        sw_license_list = asset_obj.arg_licenses

    # get list of dicts of asset info from asset arguments
    if arg_assets:
        asset_obj.get_asset_list(arg_assets)
        hw_asset_list = asset_obj.asset_list_hw
        hw_license_list = asset_obj.license_list

    # create new licenses and
    # update exisiting licenses with correct seat amount
    create_lic_obj.get_license_lists(sw_license_list)
    create_lic_obj.find_license_changes()
    create_lic_obj.create_license()
    create_lic_obj.update_license()


if __name__ == '__main__':
    args_obj = getArguments()
    args_obj.inv_args()
    args = args_obj.arguments
    run(args)
