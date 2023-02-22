#!/usr/bin/env python3

from diff import args
import pymongo
from diff.get_assets import getAssets

client = pymongo.MongoClient("mongodb://localhost:27017/")
software_db = client['software_inventory']
# Snipe Seats collection
snipe_seats = software_db['snipe_seat']


def run(args):

    assets = []
    licenses = []
    for item in args:
        if item['func_type'] == 'asset':
            assets.append(item['argument'])

        if item['func_type'] == 'license':
            licenses.append(item['argument'])

    if len(assets) > 0:
        # get list of assets from asset arguments
        # get list of licenses associated with assets
        asset_hw = getAssets.get_asset_list(assets)
        assets_assets = asset_hw.asset_list_hw
        licenses = asset_hw.license_list
    if len(licenses) > 0:
        # get list of assets from license arguments
        asset_sw = getAssets.get_lic_list(licenses)
        assets_licenses = asset_sw.asset_list_sw

    # add all assets to one list to find differences
    assets = assets_assets.extend(assets_licenses)


if __name__ == '__main__':
    arguments = args.getArguments
    args = arguments.inv_args()
    run(args)
