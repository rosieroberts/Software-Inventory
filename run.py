#!/usr/bin/env python3
from diff import args
import pymongo
from diff.get_assets import getAssets

client = pymongo.MongoClient("mongodb://localhost:27017/")
software_db = client['software_inventory']
# Snipe Seats collection
snipe_seats = software_db['snipe_seat']


def run(arguments):

    assets = []
    licenses = []
    for item in args:
        if item['func_type'] == 'asset':
            assets.append(item['argument'])

        if item['func_type'] == 'license':
            licenses.append(item['argument'])

    if len(assets) > 0:
        asset_dicts = getAssets.get_asset_list(assets)
    if len(licenses) > 0:
        asset_dicts_lic  = getAssets.get_lic_list(licenses)
    


if __name__ == '__main__':
    arguments = args.getArguments
    args = arguments.inv_args()
    run(args)
