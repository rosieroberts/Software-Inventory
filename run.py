#!/usr/bin/env python3

from diff import args
import pymongo
from diff.args import getArguments
from diff.get_assets import getAssets

client = pymongo.MongoClient("mongodb://localhost:27017/")
software_db = client['software_inventory']
# Snipe Seats collection
snipe_seats = software_db['snipe_seat']


def run(args):

    arg_assets = []
    arg_licenses = []
    print(args)
    if args:
        for item in args:
            if item['func_type'] == 'asset':
                arg_assets.append(item['argument'])

            if item['func_type'] == 'license':
                arg_licenses.append(item['argument'])

    # create an instance of getAssets class
    asset_obj = getAssets()

    asset_list = []
    #if no arguments provided get a list of all asset info
    if len(arg_assets) == 0 and len(arg_licenses) == 0:
        asset_list = asset_obj.get_all_assets()

    # if license arguments provided, get list of assets
    # associated with those licenses
    if len(arg_licenses) > 0:
        asset_obj.get_lic_list(arg_licenses)
        sw_asset_list = asset_obj.asset_list_sw

    # get list of dicts of asset info from asset arguments
    if len(arg_assets) > 0:
        asset_obj.get_asset_list(arg_assets)
        hw_asset_list = asset_obj.asset_list_hw
        hw_license_list = asset_obj.license_list


     

if __name__ == '__main__':
    args_obj = getArguments()
    args_obj.inv_args()
    args = args_obj.arguments
    run(args)
