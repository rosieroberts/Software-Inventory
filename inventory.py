#!/usr/bin/env python3

import pymongo
import requests
import sys
from pprint import pprint, pformat
from json import decoder
from re import compile
import traceback
from time import time, sleep
from datetime import date, timedelta
from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from argparse import ArgumentParser
from update_dbs import config as cfg
from lib import upd_dbs

# get today's date
today = date.today()
today_date = today.strftime('%m-%d-%Y')

# pass test_list in inv_args if wanting to use for testing
test_list = ['CMPC893', 'EEPC893-1', 'EEPC893-2', 'FMPC893', 'club963', '960C-9125', '954C-37F1']

logger = getLogger('inventory')
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


def main(args):
    if args:

        client = pymongo.MongoClient("mongodb://localhost:27017/")
        software_db = client['software_inventory']
        # Snipe Seats collection
        snipe_seats = software_db['snipe_seat']

        assets = []
        licenses = []
        for item in args:

            if item['func_type'] == 'asset':
                assets.append(item['argument'])

            if item['func_type'] == 'license':
                licenses.append(item['argument'])

        # Update databases first
        #upd_dbs.upd_snipe_hw()
        #upd_dbs.upd_bx_hw()
        #upd_dbs.upd_bx_sw()

        # create licenses
        create_lic()

        if len(assets) > 0:
            lic_list = []
            asset_list = get_asset_list(assets)
            for item in asset_list:
                # getting licenseID associated with each assetID
                lic = snipe_seats.find({'assigned_asset': item['ID']},
                                       {'_id': 0, 'license_id': 1})
                if lic:
                    lic = list(lic)
                    print(lic)
                    logger.debug('asset_tag {}/asset ID {} has {} licenses'.format(item['Asset Tag'],
                                                                                   item['ID'],
                                                                                   len(lic)))
                    for licen in lic:
                        lic_list.append(licen['license_id'])
                else:
                    logger.debug('License seats are not found for {} '.format(item['Asset Tag']))
                    sys.exit()
            print(lic_list)
            print(len(lic_list))

            # remove duplicate licenses
            if len(lic_list) > 1: 
                lic_list = set(lic_list)
                print(len(lic_list))
            print(lic_list)

            # update seat information in mongo for all licenses associated with
            # assets in arguments
            upd_dbs.upd_lic(*lic_list)           
            match_dbs(asset_list)

        if len(licenses) > 0:
            upd_dbs.upd_lic(*licenses)
            asset_lists = get_lic_list(licenses)
            asset_list = asset_lists[0]
            assets_not_found = asset_lists[1]
            match_dbs(asset_list, *assets_not_found)

    else:
        # Update databases first
        upd_dbs.upd_snipe_hw()
        # upd_dbs.upd_bx_hw()
        # upd_dbs.upd_bx_sw()

        # create licenses
        create_lic()
        upd_dbs.upd_lic()
        match_dbs(get_asset_list(inv_args()))


def get_asset_list(asset_list):
    # takes in list of asset hostnames, club, asset_tag, and returns list
    # of dictionaries from snipe_hw db
    # if no arguments, returns full list of all hosts that have software sorted

    logger.debug('FUNCTION get_asset_list')

    client = pymongo.MongoClient("mongodb://localhost:27017/")
    software_db = client['software_inventory']
    asset_db = client['inventory']

    # BigFix HW collection
    # bigfix_hw = software_db['bigfix_hw']

    # BigFix SW collection
    # bigfix_sw = software_db['bigfix_sw']

    # Snipe HW collection
    snipe_hw = software_db['snipe_hw']

    # Snipe Licenses collection
    # snipe_lic = software_db['snipe_lic']

    # Snipe Seats  collection
    # snipe_seats = software_db['snipe_seat']

    # deleted assets collection
    deleted = asset_db['deleted']

    # unique software collection
    # soft_col = software_db['all_software']

    club_rgx = compile(r'((club)[\d]{3})')
    asset_tag_rgx = compile(r'([0-9]{3}[A-Z]{1}-[A-Za-z0-9]{4})')
    hostname_rgx = compile(r'[A-Z]{1,3}[PC]{1}\d{3}(-[\d]{1,2})*')

    if asset_list:
        snipe_list = []
        for item in asset_list:
            club = club_rgx.search(item)
            asset_tag = asset_tag_rgx.search(item)
            hostname = hostname_rgx.search(item)
            if club:
                snipe_item = snipe_hw.find({'Location': item})
            elif asset_tag:
                snipe_item = snipe_hw.find({'Asset Tag': item})
            elif hostname:
                snipe_item = snipe_hw.find({'Hostname': item})
            else:
                continue

            snipe_item = list(snipe_item)
            if snipe_item:
                for asset in snipe_item:
                    snipe_list.append(asset)
            else:
                if asset_tag:
                    del_asset = deleted.find_one({'asset_tag': item})
                    asset_id = del_asset['id']
                    snipe_item = {'ID': asset_id}
                    snipe_list.append(snipe_item)
                else:
                    continue

    else:
        # get list of snipe hw devices to look up software for
        snipe_list = snipe_hw.find({}).sort('Asset Tag', pymongo.ASCENDING)
        snipe_list = list(snipe_list)

    return snipe_list


def get_lic_list(lic_list):
    ''' Only runs when a list of licenses in provided in arguments
        take list of licenses and return list of assets that are associated with that license
        this function only runs when -l <licenseID> is added as an argument '''

    client = pymongo.MongoClient("mongodb://localhost:27017/")
    software_db = client['software_inventory']
    asset_db = client['inventory']

    # BigFix HW collection
    # bigfix_hw = software_db['bigfix_hw']

    # BigFix SW collection
    # bigfix_sw = software_db['bigfix_sw']

    # Snipe HW collection
    snipe_hw = software_db['snipe_hw']

    # Snipe Licenses collection
    # snipe_lic = software_db['snipe_lic']

    # Snipe Seats  collection
    snipe_seats = software_db['snipe_seat']

    # deleted assets collection
    deleted = asset_db['deleted']

    # unique software collection
    # soft_col = software_db['all_software']

    lic_rgx = compile(r'([\d]{1,3})')

    logger.debug('FUNCTION get_lic_list')
    if lic_list:
        snipe_list = []
        asset_not_found = []
        d_ct = 0
        ct = 0
        f_ct = 0
        for item in lic_list:
            # for each license in list of licenses provided in command line
            lic = lic_rgx.search(item)
            if lic:
                # make sure the input matches the license number regex and looks only for license with active assets
                # seats with no assets associated with them will have a None in asset_name in the snipe_seats collection
                lic_item = snipe_seats.find({'license_id': int(item), 'asset_name': {'$ne': None}})
                lic_item = list(lic_item)
            else:
                continue
            if lic_item:
                for seat in lic_item:
                    snipe_item = snipe_hw.find_one({'Location': seat['location'], 'Hostname': seat['asset_name']})
                    if snipe_item:
                        # if there is a record of a an asset associated with this license, append the asset info to list
                        snipe_list.append(snipe_item)
                        f_ct += 1
                    else:
                        # if an asset has been deleted the asset info will be in the deleted collection in the 'inventory' mongodb
                        # if there is a case where the asset was deleted but the seat is still checked out, this will return the asset info
                        if seat['asset_name']:
                            del_asset = deleted.find_one({'_snipeit_hostname_8': seat['asset_name']})
                            if del_asset:
                                d_ct += 1
                                snipe_item = {'ID': del_asset['id'],
                                              'Asset Tag': del_asset['asset_tag'],
                                              'IP': del_asset['_snipeit_ip_6'],
                                              'Mac Address': del_asset['_snipeit_mac_address_7'],
                                              'Location': del_asset['Location'],
                                              'Hostname': del_asset['_snipeit_hostname_8']}
                                snipe_list.append(snipe_item)
                            else:
                                ct += 1
                                asset_not_found.append(seat)
                                logger.debug('error, there is a seat associated to an asset not found. Review lic {} seat {}'
                                             .format(item, seat['id']))
                                continue
                        else:
                            continue
    logger.debug('found {} assets, assets not found {}, found in deleted {} assets'.format(f_ct, ct, d_ct))
    return snipe_list, asset_not_found


def match_dbs(snipe_list, *asset_not_found):
    ''' Combine all information from all databases
        Snipe HW
        Snipe License
        Big Fix HW
        Big Fix SW

        to get snipe license seat information and create a new combined database
        and update snipe-it licenses

        db.snipe_hw.findOne({})
{
        "_id" :
        "ID" : 12815,
        "Asset Tag" : "",
        "IP" : "",
        "Mac Address" : "",
        "Location" : "",
        "Hostname" : ""
}
> db.snipe_lic.findOne({})
{
        "_id" : ,
        "License ID" : 3,
        "License Name" : "",
        "Total Seats" : 10,
        "Manufacturer" : "",
        "Manufacturer ID" : ,
        "Free Seats" : 8
}
> db.snipe_seat.findOne()
{
        "_id" : ObjectId("6288040562e2ed2894a9eb13"),
        "id" : 439580,
        "license_id" : 442,
        "assigned_asset" : null,
        "location" : null,
        "seat_name" : "Seat 1",
        "asset_name" : null,
        "license_name" : "Microsoft Edge | 100.0.1185.36"
}
> db.bigfix_hw.findOne({})
{
        "_id" : ,
        "comp_name" : "",
        "IP" : "",
        "mac_addr" : ""
}
> db.bigfix_sw.findOne({})
{
        "_id" : "),
        "comp_name" : "",
        "sw" : ""

'''
    # create_lic()
    # list of assets that could not be updated due to asset not active in snipe-it
    not_added = []

    # list of license and asset_ids that could not be added due to no available seats in snipe
    no_free_seat_list = []

    client = pymongo.MongoClient("mongodb://localhost:27017/")
    software_db = client['software_inventory']

    # BigFix HW collection
    bigfix_hw = software_db['bigfix_hw']

    # BigFix SW collection
    bigfix_sw = software_db['bigfix_sw']

    # Snipe HW collection
    snipe_hw = software_db['snipe_hw']

    # Snipe Licenses collection
    snipe_lic = software_db['snipe_lic']

    # Snipe Seats  collection
    snipe_seats = software_db['snipe_seat']

    # unique software collection
    # soft_col = software_db['all_software']

    logger.debug('FUNCTION match_dbs')

    try:
        # sleep in case
        sleep(60)
        start = time()
        ct = 0
        if len(snipe_list) == 0:
            logger.debug('There are no assets in snipe_it list')

        api_calls = []
        mongo_updates = []

        asset_list = snipe_list
        # assets associated with a license, but have been deleted from snipeIT
        # seats associated with these assets need to be checked in
        if asset_not_found:
            deleted_asset_list = asset_not_found
            logger.debug('list of deleted assets\n', deleted_asset_list)

        # for each asset in snipe_hw look up in mongodb big_fix_hw
        for count, item in enumerate(asset_list):
            asset_id = item['ID']
            location = item['Location']
            comp_name = item['Hostname']
            bgfix_item = bigfix_hw.find_one({'comp_name': comp_name,
                                             'IP': item['IP'],
                                             'mac_addr': item['Mac Address']},
                                            {'comp_name': 1, 'IP': 1,
                                             'mac_addr': 1, '_id': 0})

            # figure out what to do when item is not found in the hardware list, only in software list
            # if not bgfix_item:
            #   bgfix_sw_list = bigfix_sw.find({'comp_name': item['Hostname']},
            #                                  {'sw': 1, 'comp_name': 1, '_id': 0})

            # if asset is in bigfix_hw collection, not sure why I am checking the count here
            if bgfix_item and count >= 0:
                # print(count, item['Asset Tag'])
                # find all software with comp_name in bigfix_sw db
                bgfix_sw_list = bigfix_sw.find({'comp_name': item['Hostname']},
                                               {'sw': 1, 'comp_name': 1, '_id': 0})
                bgfix_sw_list = list(bgfix_sw_list)

                bf_sw_list = []

                bf_sw_list = [line['sw'] for line in bgfix_sw_list]

                # list of software for each asset already in snipe
                snipe_sw_list = snipe_seats.find({'assigned_asset': asset_id},
                                                 {'license_name': 1,
                                                  'asset_name': 1,
                                                  'license_id': 1,
                                                  'assigned_asset': 1,
                                                  'id': 1, '_id': 0})

                snipe_sw_list = list(snipe_sw_list)

                # look for software checked out to asset and if no longer in active in bigfix, check license in and update db
                for i in snipe_sw_list:
                    found_item = bigfix_sw.find_one({'comp_name': i['asset_name'], 'sw': i['license_name']},
                                                    {'sw': 1, 'comp_name': 1, '_id': 0})

                    if not found_item:
                        # check in seats by sending a '' string for the asset_id field
                        logger.debug('asset {} no longer has license {}'.format(i['asset_name'],
                                                                                i['license_name']))
                        url = cfg.api_url_software_seat.format(i['license_id'], i['id'])
                        if ct == 110:
                            sleep(60)
                            ct = 0
                        item_str = str({'asset_id': ''})
                        payload = item_str.replace('\'', '\"')

                        logger.debug('PATCH REQUEST 1, remove seat')
                        response = requests.request("PATCH",
                                                    url=url,
                                                    data=payload,
                                                    headers=cfg.api_headers)
                        logger.debug(pformat(response.text))
                        status_code = response.status_code
                        ct += 1

                        if status_code == 200:
                            content = response.json()
                            status = str(content['status'])
                            if status == 'success':
                                logger.debug('updating mongo, REMOVE 1')
                                # api call dict for testing
                                api_call_1 = {'license_id': i['license_id'],
                                              'seat_id': i['id'],
                                              'asset_id': '',
                                              'asset_tag': '',
                                              'asset_name': '',
                                              'type': 'remove seat',
                                              'status': 'success'}
                                api_calls.append(api_call_1)

                                snipe_seats.update_one({'license_id': i['license_id'], 'id': i['id']},
                                                       {'$set': {'assigned_asset': None,
                                                                 'asset_name': None,
                                                                 'location': None,
                                                                 'asset_tag': None,
                                                                 'date': today_date}})
                                free_seats = snipe_lic.find_one({'License ID': i['license_id']}, {'_id': 0, 'Free Seats': 1})
                                snipe_lic.update_one({'License ID': i['license_id']},
                                                     {'$set': {'Free Seats': int(free_seats) + 1}})

                                logger.debug('UPDATED FREE SEATS IN MONGO 1')
                                # updated instance of lic with updated free seat numbers if it was updated
                                mongo_upd_lic_1 = snipe_lic.find_one({'License ID': i['License ID']})
                                mongo_upd_seat_1 = snipe_seats.find_one({'license_id': i['license_id'], 'id': i['id']})
                                logger.debug('Removed license {} from asset id {}'.format(i['license_id'], asset_id))

                                try:
                                    mongo_test_dict_1 = {'license_id': mongo_upd_lic_1['License ID'],
                                                         'license_id_name': mongo_upd_lic_1['License Name'],
                                                         'total_seats': mongo_upd_lic_1['Total Seats'],
                                                         'free_seats': mongo_upd_lic_1['Free Seats'],
                                                         'seat_license_id': mongo_upd_seat_1['license_id'],
                                                         'seat_id': mongo_upd_seat_1['id'],
                                                         'seat_lic_name': mongo_upd_seat_1['license_name'],
                                                         'assigned_asset': mongo_upd_seat_1['assigned_asset'],
                                                         'asset_tag': mongo_upd_seat_1['asset_tag'],
                                                         'asset_name': mongo_upd_seat_1['asset_name'],
                                                         'date': mongo_upd_seat_1['date']}

                                    mongo_updates.append(mongo_test_dict_1)

                                except KeyError:
                                    logger.debug('KeyError getting all info from mongo for testing')

                            elif status == 'error':
                                # api call dict for testing
                                api_call_1 = {'license_id': i['license_id'],
                                              'seat_id': i['id'],
                                              'asset_id': '',
                                              'asset_tag': '',
                                              'type': 'remove seat',
                                              'status': 'error'}
                                api_calls.append(api_call_1)

                                message = str(content['messages'])
                                if message == 'Target not found':
                                    logger.debug('error, asset {} is not currently active, cannot update license'.format(asset_id))
                                    not_added.append(asset_id)
                                    continue

                            else:
                                logger.debug('error, license {} removal not successful for asset {}'.format(i['license_id'], asset_id))
                                continue

                        else:
                            logger.debug('error, there was something wrong removing '
                                         'license {} from asset {}'.format(i['license_name'],
                                                                           i['asset_name']))
                            continue

                    else:
                        pass
                        # no change, currently asset has software associated with it and it is checked out in snipe-it
                        # logger.debug('software {} still checked out to asset {} no update required'.format(i['license_name'],
                        #                                                                                    i['asset_name']))

                # get list of license names in snipe
                sp_sw_list = [ln['license_name'] for ln in snipe_sw_list]

                # check if each software item in snipe is not in bigfix to see if it can be removed
                not_in_bigfix_sw = list(filter(lambda i: i not in bf_sw_list, sp_sw_list))

                if not_in_bigfix_sw:
                    logger.debug('amount of licenses not in BigFix, but active in Snipe - {}'.format(len(not_in_bigfix_sw)))

                for itm in bgfix_sw_list:
                    software = itm['sw']
                    license = snipe_lic.find_one({'License Name': software},
                                                 {'License Name': 1, 'License ID': 1, 'Total Seats': 1, 'Free Seats': 1, '_id': 0})
                    # if bigfix license is found in snipeIT
                    if license:
                        found_seat = snipe_seats.find_one({'assigned_asset': asset_id, 'license_id': license['License ID']},
                                                          {'id': 1, 'assigned_asset': 1, 'name': 1, 'location': 1, '_id': 0})
                        # if seat was not found
                        if found_seat is None:
                            if int(license['Free Seats']) >= 1:
                                # ***issues with snipe it, waiting for them to resolve before assigning seats to licenses***
                                # issue will take a while to fix, seat names are not consistent with API, keep an eye on it

                                # find an unassigned seat to check out asset
                                seat = snipe_seats.find_one({'assigned_asset': None, 'license_id': license['License ID']},
                                                            {'id': 1, 'assigned_asset': 1, 'name': 1, 'location': 1, '_id': 0})

                                print('LICENSE', license)
                                print('SEAT', seat)
                                if license['License ID'] is not None and seat['id'] is not None:
                                    url = cfg.api_url_software_seat.format(license['License ID'], seat['id'])
                                else:
                                    # license ID and seat id
                                    logger.debug('Could not check out seat for asset {} and license {}, no empty seats available'
                                                 .format(asset_id, license['License ID']))
                                    no_free_seat_dict = {'asset_id': asset_id,
                                                         'license_id': license['License ID']}
                                    no_free_seat_list.append(no_free_seat_dict)
                                    continue
                                if ct == 110:
                                    sleep(60)
                                    ct = 0
                                # asset ID
                                item_str = str({'asset_id': asset_id})
                                payload = item_str.replace('\'', '\"')
                                logger.debug('PATCH REQUEST check out seat for asset {} '.format(item_str))
                                response = requests.request("PATCH",
                                                            url=url,
                                                            data=payload,
                                                            headers=cfg.api_headers)

                                status_code = response.status_code
                                logger.debug(status_code)
                                logger.debug(pformat(response.text))
                                ct += 1
                                if status_code == 200:
                                    content = response.json()
                                    logger.debug(pformat(content))
                                    status = str(content['status'])
                                    asset_info = snipe_hw.find_one({'ID': asset_id})
                                    asset_tag = asset_info['Asset Tag']

                                    if status == 'success':
                                        logger.debug('updating mongo check out 2')

                                        # api call dict for testing
                                        api_call_2 = {'license_id': license['License ID'],
                                                      'seat_id': seat['id'],
                                                      'asset_id': asset_id,
                                                      'asset_tag': asset_tag,
                                                      'type': 'checkout seat',
                                                      'status': 'success'}

                                        api_calls.append(api_call_2)

                                        snipe_seats.update_one({'license_id': license['License ID'], 'id': seat['id']},
                                                               {'$set': {'assigned_asset': asset_id,
                                                                         'asset_name': comp_name,
                                                                         'location': location,
                                                                         'asset_tag': item['Asset Tag']}})

                                        free_seats = int(license['Free Seats']) - 1
                                        snipe_lic.update_one({'License ID': license['License ID']},
                                                             {'$set': {'Free Seats': free_seats}})
                                        logger.debug('UPDATED FREE SEATS 2')
                                        mongo_upd_lic_2 = snipe_lic.find_one({'License ID': license['License ID']})
                                        mongo_upd_seat_2 = snipe_seats.find_one({'license_id': license['License ID'], 'id': seat['id']})
                                        logger.debug('added license {} to asset id {}'.format(license['License ID'], asset_id))

                                        try:
                                            mongo_test_dict_2 = {'license_id': mongo_upd_lic_2['License ID'],
                                                                 'license_id_name': mongo_upd_lic_2['License Name'],
                                                                 'total_seats': mongo_upd_lic_2['Total Seats'],
                                                                 'free_seats': mongo_upd_lic_2['Free Seats'],
                                                                 'seat_license_id': mongo_upd_seat_2['license_id'],
                                                                 'seat_id': mongo_upd_seat_2['id'],
                                                                 'seat_lic_name': mongo_upd_seat_2['license_name'],
                                                                 'assigned_asset': mongo_upd_seat_2['assigned_asset'],
                                                                 'asset_tag': mongo_upd_seat_2['asset_tag'],
                                                                 'date': mongo_upd_seat_2['date']}

                                            mongo_updates.append(mongo_test_dict_2)

                                        except KeyError:
                                            logger.debug('KeyError getting all info from mongo for testing')

                                    elif status == 'error':
                                        # api call dict for testing
                                        api_call_2 = {'license_id': license['License ID'],
                                                      'seat_id': seat['id'],
                                                      'asset_id': asset_id,
                                                      'asset_tag': asset_tag,
                                                      'type': 'checkout seat',
                                                      'status': 'error'}

                                        api_calls.append(api_call_2)

                                        message = str(content['messages'])
                                        if message == 'Target not found':
                                            logger.debug('Asset {} is not currently active, cannot update license'.format(asset_id))
                                            not_added.append(asset_id)
                                            continue
                                        else:
                                            continue

                                    else:
                                        logger.debug('error, license addition not successful')
                                        continue
                                else:
                                    logger.debug('There was something wrong adding license to asset {}'.format(asset_id))
                                    continue
                            else:
                                logger.debug('There are no seats available for license id {} '.format(license['License ID']))
                                continue
                        else:
                            continue
                    else:
                        # make sure to remove comment below once snipe is populated
                        # logger.debug('License {} not found in snipe'.format(software))
                        continue

                # if there are licenses no longer showing up in bigfix, remove license from snipe-it
                if not_in_bigfix_sw:
                    for sft in not_in_bigfix_sw:
                        lic = snipe_lic.find_one({'License Name': sft},
                                                 {'License Name': 1, 'License ID': 1, 'Total Seats': 1, 'Free Seats': 1, '_id': 0})

                        if not lic:
                            continue
                        # if there are licenses checked out to assets, check them in to allow deletion of license
                        if lic['Total Seats'] != lic['Free Seats']:
                            out_seats = snipe_seats.find({'license id': lic['License ID']})
                            out_seats = list(out_seats)

                            # if seats are checked out, check them in and update snipe_db if check in was successful
                            if out_seats:
                                for seat in out_seats:
                                    logger.debug('________________________________')
                                    logger.debug('check in seat')

                                    # check in seats by sending a '' string for the asset_id field
                                    url = cfg.api_url_software_seat.format(seat['license_id'], seat['id'])
                                    if ct == 110:
                                        sleep(60)
                                        ct = 0
                                    item_str = str({'asset_id': ''})
                                    payload = item_str.replace('\'', '\"')

                                    response = requests.request("PATCH",
                                                                url=url,
                                                                data=payload,
                                                                headers=cfg.api_headers)
                                    logger.debug(pformat(response.text))
                                    status_code = response.status_code
                                    ct += 1
                                    status = ' '
                                    logger.debug('PATCH REQUEST 2, check in seats for deleting license for asset {} '.format(item_str))
                                    if status_code == 200:
                                        content = response.json()
                                        status = str(content['status'])
                                        if status == 'success':
                                            logger.debug('updating mongo remove 3')

                                            # api call dict for testing
                                            api_call_3 = {'license_id': lic['License ID'],
                                                          'seat_id': seat['id'],
                                                          'asset_id': '',
                                                          'asset_tag': '',
                                                          'type': 'remove seat',
                                                          'status': 'success'}

                                            api_calls.append(api_call_3)

                                            snipe_seats.update_one({'license_id': seat['License ID'], 'id': seat['id']},
                                                                   {'$set': {'assigned_asset': None,
                                                                             'asset_name': None,
                                                                             'location': None,
                                                                             'asset_tag': None}})

                                            snipe_lic.update_one({'License ID': lic['License ID']},
                                                                 {'$set': {'Free Seats': int(lic['Free Seats']) + 1}})
                                            logger.debug('UPDATED/REMOVED LICENSE FROM ASSET IN MONGO ')
                                            print(snipe_lic.find_one({'License ID': lic['License ID']}))
                                            logger.debug('Removed license {} from asset id {}'.format(lic['License ID'], seat['assigned_asset']))

                                            logger.debug('UPDATED FREE SEATS 3')

                                            # updated instance of lic with updated free seat numbers if it was updated
                                            mongo_upd_lic_3 = snipe_lic.find_one({'License ID': lic['license_id']})
                                            mongo_upd_seat_3 = snipe_seats.find_one({'license_id': seat['license_id'], 'id': seat['id']})
                                            logger.debug('Removed license {} from asset id {}'.format(seat['license_id'], asset_id))

                                            try:
                                                mongo_test_dict_3 = {'license_id': mongo_upd_lic_3['License ID'],
                                                                     'license_id_name': mongo_upd_lic_3['License Name'],
                                                                     'total_seats': mongo_upd_lic_3['Total Seats'],
                                                                     'free_seats': mongo_upd_lic_3['Free Seats'],
                                                                     'seat_license_id': mongo_upd_seat_3['license_id'],
                                                                     'seat_id': mongo_upd_seat_3['id'],
                                                                     'seat_lic_name': mongo_upd_seat_3['license_name'],
                                                                     'assigned_asset': mongo_upd_seat_3['assigned_asset'],
                                                                     'asset_tag': mongo_upd_seat_3['asset_tag'],
                                                                     'date': mongo_upd_seat_3['date']}

                                                mongo_updates.append(mongo_test_dict_3)

                                            except KeyError:
                                                logger.debug('KeyError getting all info from mongo for testing')

                                        elif status == 'error':
                                            # api call dict for testing
                                            api_call_3 = {'license_id': lic['License ID'],
                                                          'seat_id': seat['id'],
                                                          'asset_id': '',
                                                          'asset_tag': '',
                                                          'type': 'remove seat',
                                                          'status': 'error'}

                                            api_calls.append(api_call_3)

                                            message = str(content['messages'])
                                            if message == 'Target not found':
                                                logger.debug('error, asset {} is not currently active, cannot update license'.format(asset_id))
                                                not_added.append(asset_id)
                                                continue
                                            else:
                                                logger.debug('unspecified error removing seat for asset {} from license {}'.format(asset_id, lic['License ID']))

                                        else:
                                            logger.debug('error, license removal not successful')
                                            continue

                                    else:
                                        logger.debug('error, there was something wrong removing license to asset {}'.format(asset_id))
                                        continue

                        # check if license has any seat checked out and if not, delete license
                        if lic['Total Seats'] == lic['Free Seats']:
                            print(sft, lic['License ID'])
                            logger.debug('DELETE license________________________')
                            url = cfg.api_url_software_lic.format(lic['License ID'])
                            if ct == 110:
                                sleep(30)
                                ct = 0
                            response = requests.request("DELETE",
                                                        url=url,
                                                        headers=cfg.api_headers)
                            logger.debug(pformat(response.text))
                            status_code = response.status_code
                            ct += 1

                            logger.debug('DELETE REQUEST, delete license {}'.format(lic['License ID']))
                            if status_code == 200:
                                content = response.json()
                                status = str(content['status'])
                                if status == 'success':
                                    logger.debug('Removed license {} from snipe-it'.format(lic['License ID']))
                                    # api call dict for testing
                                    api_call_4 = {'license_id': lic['license_id'],
                                                  'seat_id': '',
                                                  'asset_id': '',
                                                  'asset_tag': '',
                                                  'type': 'remove license',
                                                  'status': 'success'}

                                    api_calls.append(api_call_4)

                                    # remove license from mongodb, returns true if deletion success
                                    delete_lic = snipe_lic.delete_one({'License ID': lic['License ID']})
                                    delete_lic_seats = snipe_seats.delete_many({'license_id': lic['License ID']})

                                    logger.debug('TRUE if license deleted from mongo snipe_lic {}, snipe_seats {} '
                                                 .format(delete_lic, delete_lic_seats))
                                    # updated instance of lic, should return none if successfully deleted
                                    # after running decide if it is best to use the delete variable returned to make sure it is deleted
                                    # or look for the item again to see if it returns None and use that
                                    # currently using the latter.
                                    mongo_upd_lic_4 = snipe_lic.find_one({'License ID': lic['License ID']})
                                    mongo_upd_seat_4 = snipe_seats.find_one({'license_id': seat['license_id']})

                                    try:
                                        if mongo_upd_lic_4 is None and mongo_upd_seat_4 is None:
                                            logger.debug('Removed license {} from mongo'.format(lic['License ID']))
                                            mongo_test_dict_4 = {'license_id': lic['License ID'],
                                                                 'license_id_name': lic['License Name'],
                                                                 'total_seats': None,
                                                                 'free_seats': None,
                                                                 'seat_license_id': None,
                                                                 'seat_id': None,
                                                                 'seat_lic_name': None,
                                                                 'assigned_asset': None,
                                                                 'asset_tag': None,
                                                                 'date': today_date}

                                            mongo_updates.append(mongo_test_dict_4)
                                        else:
                                            logger.debug('Could not remove license {} from mongo'.format(lic['License ID']))

                                    except KeyError:
                                        logger.debug('Could not add license info to mongo_test_dict 4')

                                elif status == 'error':
                                    # api call dict for testing
                                    api_call_4 = {'license_id': lic['license_id'],
                                                  'seat_id': '',
                                                  'asset_id': '',
                                                  'asset_tag': '',
                                                  'type': 'remove license',
                                                  'status': 'error'}

                                    api_calls.append(api_call_4)

                                    message = str(content['messages'])
                                    # I do not know if this message applies to license deletion as well. Check
                                    if message == 'Target not found':
                                        logger.debug('error, could not delete license {}, license not found'.format(lic['License ID']))
                                        not_added.append(asset_id)
                                        continue

                                else:
                                    logger.debug('error, license deletion not successful')
                                    continue

                            else:
                                logger.debug('error, there was something wrong deleting license {}'.format(lic['License ID']))
                                continue
        logger.debug('number of items in snipe {}'.format(len(asset_list)))
        end = time()
        logger.debug('runtime {}'.format(str(timedelta(seconds=(end - start)))))
        return api_calls, mongo_updates, not_added, no_free_seat_list

    except(KeyError,
           decoder.JSONDecodeError):
        logger.error('There was an error updating the licenses to Snipe-it, check licenses for asset', exc_info=True)
        traceback.print_exc()


def comp_nums():
    # get final amounts of licenses/seats for verification

    logger.debug('FUNCTION comp_nums')
    client = pymongo.MongoClient("mongodb://localhost:27017/")

    software_db = client['software_inventory']
    inventory_db = client['inventory']
    snipe_hw_col = software_db['snipe_hw']
    snipe_del = inventory_db['deleted']
    bigfix_hw_col = software_db['bigfix_hw']
    bigfix_sw_col = software_db['bigfix_sw']

    comp_list = upd_dbs.upd_bx_hw()
    snipe_list = upd_dbs.upd_snipe_hw()

    not_found = []
    not_found2 = []
    found = []
    found2 = []
    found_deleted = []
    found_deleted_mac = []
    found_del_snipe_mac = []
    found_mac = []
    found_mac2 = []
    snipe_fmac = []
    bigfix_fmac = []
    found_host = []
    found_host_sw = []
    # amount of assets in bigfix found in snipe
    for item in comp_list:
        snipe_hw_ip = snipe_hw_col.find({'IP': item['IP'], 'Mac Address': item['mac_addr']},
                                        {'IP': 1, 'Mac Address': 1, '_id': 0})
        snipe_hw_ip = list(snipe_hw_ip)

        if snipe_hw_ip:
            found.append(item)

        else:
            deleted = snipe_del.find({'_snipeit_ip_6': item['IP'], '_snipeit_mac_address_7': item['mac_addr']},
                                     {'_snipeit_ip_6': 1, '_snipeit_mac_address_7': 1, '_id': 0})
            deleted = list(deleted)
            if deleted:
                found_deleted.append(item)
            else:
                snipe_mac = snipe_hw_col.find({'Mac Address': item['mac_addr']},
                                              {'IP': 1, 'Mac Address': 1, 'Hostname': 1, '_id': 0})
                snipe_mac = list(snipe_mac)

                if snipe_mac:
                    found_mac.append(item)
                    snipe_fmac.append(snipe_mac[0])

                else:
                    deleted_mac = snipe_del.find({'_snipeit_mac_address_7': item['mac_addr']},
                                                 {'_snipeit_ip_6': 1, '_snipeit_mac_address_7': 1, '_id': 0})
                    deleted_mac = list(deleted_mac)
                    if deleted_mac:
                        found_deleted_mac.append(item)
                        found_del_snipe_mac.append(deleted_mac[0])
                    else:
                        not_found.append(item)

    # amount of assets from snipe found in bigfix hw
    for item2 in snipe_list:
        bigfix_hw_ip = bigfix_hw_col.find({'IP': item2['IP'], 'mac_addr': item2['Mac Address']},
                                          {'IP': 1, 'mac_addr': 1, '_id': 0})
        bigfix_hw_ip = list(bigfix_hw_ip)

        if bigfix_hw_ip:
            found2.append(item2)

        else:
            bigfix_hw_mac = bigfix_hw_col.find({'mac_addr': item2['Mac Address']},
                                               {'IP': 1, 'mac_addr': 1, 'comp_name': 1, '_id': 0})
            bigfix_hw_mac = list(bigfix_hw_mac)

            if bigfix_hw_mac:
                found_mac2.append(item2)
                bigfix_fmac.append(bigfix_hw_mac[0])

            else:
                bigfix_hw_host = bigfix_hw_col.find({'comp_name': item2['Hostname']},
                                                    {'IP': 1, 'mac_addr': 1, 'comp_name': 1, '_id': 0})
                bigfix_hw_host = list(bigfix_hw_host)

                if bigfix_hw_host:
                    found_host.append(item2)

                else:
                    bigfix_sw_host = bigfix_sw_col.find({'comp_name': item2['Hostname']},
                                                        {'comp_name': 1, '_id': 0})
                    bigfix_sw_host = list(bigfix_sw_host)

                    if bigfix_sw_host:
                        found_host_sw.append(item2)
                        print(bigfix_sw_host[0])
                    else:
                        not_found2.append(item2)

    print('______________________________________________________')
    print('HOST FOUND')
    pprint(found_host_sw)
    print('______________________________________________________')
    print('NOT FOUND')
    pprint(not_found2)
    print(len(snipe_list), 'all snipe devices')
    print(len(found2), 'found in bigfix hw devices')
    print(len(found_mac2), 'found with diff ip in bigfix')
    print(len(found_host), 'found only computer name in bigfix hw')
    print(len(found_host_sw), 'found only computer name in bigfix sw')
    # print(len(found_deleted), 'found in deleted')
    # print(len(found_deleted_mac), 'found in deleted_mac')
    print(len(not_found2), 'not found')


def api_call():
    # for testing
    # license ID and seat id
    url = cfg.api_url_software_seat.format('3', '1999')
    # asset ID
    item_str = str({'asset_id': '5702'})
    payload = item_str.replace('\'', '\"')
    response = requests.request("PATCH",
                                url=url,
                                data=payload,
                                headers=cfg.api_headers)
    logger.debug(pformat(response.text))


def check_in(snipe_list):
    # check in seats for each asset in list of snipe assets
    # use this when deleting an item from snipe it.
    # might add this to the inventory script

    logger.debug('FUNCTION check_in')
    id_list = []

    if snipe_list is None:
        return None

    for item in snipe_list:
        # get asset ids for each asset and append to id_list
        asset_id = item['ID']
        id_list.append(asset_id)

    client = pymongo.MongoClient("mongodb://localhost:27017/")
    software_db = client['software_inventory']
    # asset_db = client['inventory']

    # Snipe Seats collection
    snipe_seats = software_db['snipe_seat']

    # deleted assets collection
    # deleted = asset_db['deleted']

    for id_ in id_list:
        # for each asset in list
        seats = snipe_seats.find({'assigned_asset': id_},
                                 {'id': 1, 'license_id': 1, '_id': 0})

        seats = list(seats)
        logger.debug('check in seats {}'.format(seats))
        for seat in seats:
            # for each seat checked out to asset
            license_id = seat['license_id']
            seat_id = seat['id']
            print(license_id, seat_id)

            # license ID and seat id
            url = cfg.api_url_software_seat.format(license_id, seat_id)

            item_str = str({'asset_id': ''})
            payload = item_str.replace('\'', '\"')
            response = requests.request("PATCH",
                                        url=url,
                                        data=payload,
                                        headers=cfg.api_headers)
            logger.debug(pformat(response.text))


def create_lic():
    '''gets total list of unique licenses and adds them to snipe it
       if not already added'''

    snipe_lic_list = []

    logger.debug('FUNCTION create_lic')

    client = pymongo.MongoClient("mongodb://localhost:27017/")
    software_db = client['software_inventory']

    # current software from bigfix with seat amounts ('sw', 'count') collection
    software_col = software_db['software']
    software = software_col.find()

    # current license collection from snipe-it
    lic_col = software_db['snipe_lic']
    all_licenses = lic_col.find()

    software = list(software)
    all_licenses = list(all_licenses)

    for item in all_licenses:
        # create list of all license names in snipe-it
        snipe_lic_list.append(item['License Name'])

    ct = 0
    count = 0
    # for each software name in bigfix - 'software' collection in mongodb 'sw', 'count'
    for item in software:
        count += 1
        # sometimes characters not supported appear in software names from bigfix
        soft_str = item['sw']
        soft_str = soft_str.replace('Â', '')
        soft_str = soft_str.replace('™', '')
        soft_str = soft_str.replace('®', '')

        if ct == 110:
            sleep(60)
            ct = 0

        # testing without pushing to API
        if soft_str not in snipe_lic_list:
            logger.debug('test ADDING LICENSE ******* {}, count {}'.format(item['sw'], item['count'] + 500))
            seat_amt = int(item['count']) + 500
            item_str = str({'name': soft_str,
                            'seats': seat_amt,
                            'category_id': '11'})
            logger.debug(item_str)
        else:
            # license collection from snipe
            license = lic_col.find_one({'License Name': soft_str},
                                       {'_id': 0,
                                        'License Name': 1,
                                        'License ID': 1,
                                        'Total Seats': 1})

            if int(item['count']) + 500 >= int(license['Total Seats']) >= int(item['count']) + 100:
                pass
                # logger.debug('check: AMOUNT SEATS IS CORRECT for license ID {} bg count {}, mongo ct {} '
                #              .format(license['License ID'],
                #                      int(item['count']) + 500,
                #                      license['Total Seats']))
                # continue
            else:
                logger.debug('check: AMOUNT SEATS IS NOT CORRECT for license ID {} bg count {}, mongo ct {} '
                             .format(license['License ID'],
                                     int(item['count']) + 500,
                                     license['Total Seats']))
                # continue

        # continue

        # purposely avoiding the lines below during testing,
        # not wanting to push to snipe API yet
        try:

            if soft_str not in snipe_lic_list:
                logger.debug('ADDING LICENSE ******* {}, count {}'.format(item['sw'], item['count'] + 500))
                print(count)
                # url for snipe-it licenses
                url = cfg.api_url_soft_all
                seat_amt = int(item['count']) + 500
                item_str = str({'name': soft_str,
                                'seats': seat_amt,
                                'category_id': '11'})
                payload = item_str.replace('\'', '\"')
                response = requests.request("POST",
                                            url=url,
                                            data=payload,
                                            headers=cfg.api_headers)
                # logger.debug(pformat(response.text))

                content = response.json()
                # logger.debug(pformat(content))
                status = str(content['status'])
                ct += 1
                if status == 'success':
                    print(soft_str, seat_amt, content['payload']['id'])
                    ins = lic_col.insert_one({'License Name': soft_str,
                                              'Total Seats': seat_amt,
                                              'Free Seats': seat_amt,
                                              'License ID': content['payload']['id'],
                                              'Date': today_date})
                    print(ins)
                    logger.debug('Added License {} with count {} to MongoDB'.format(soft_str, seat_amt))

            else:
                # license collection from snipe
                license = lic_col.find_one({'License Name': soft_str},
                                           {'_id': 0,
                                            'License Name': 1,
                                            'License ID': 1,
                                            'Total Seats': 1})

                if int(item['count']) + 500 >= int(license['Total Seats']) >= int(item['count']) + 100:
                    # logger.debug('CORRECT SEAT AMOUNT! license ID {} bg count {}, mongo ct {} '
                    #              .format(license['License ID'], int(item['count']) + 500, license['Total Seats']))
                    continue

                else:
                    logger.debug('INCORRECT SEAT AMOUNT! license ID {} bg count {}, mongo ct {} '
                                 .format(license['License ID'], int(item['count']) + 500, license['Total Seats']))
                    logger.debug('UPDATING LICENSE ####### {} with amount {}'.format(item['sw'], item['count'] + 500))
                    url = cfg.api_url_software_lic.format(license['License ID'])
                    print(url)
                    seat_amt = int(item['count']) + 500
                    item_str = str({'seats': seat_amt})
                    payload = item_str.replace('\'', '\"')
                    print(item['count'], payload)
                    response2 = requests.request("PATCH",
                                                 url=url,
                                                 data=payload,
                                                 headers=cfg.api_headers)
                    # logger.debug(pformat(response2.text))

                    content2 = response2.json()
                    # logger.debug(pformat(content2))
                    status = str(content2['status'])
                    ct += 1
                    if status == 'success':
                        lic_col.update_one({'License ID': license['License ID']},
                                           {'$set': {'Total Seats': seat_amt}})
                        logger.debug('Updated license {} with count {} in MongoDB'.format(license['License ID'], seat_amt))

                    else:
                        logger.debug('Could not update license {} with right seat amount'.format(item['sw']))

        except UnicodeEncodeError:
            sleep(120)
            logger.exception('Decode error with software item {}'.format(soft_str))
            logger.critical('create_lic exception', exc_info=True)
            print(count)


def inv_args():
    list_iter = []

    parser = ArgumentParser(description='Software Inventory Script')
    parser.add_argument(
        '-club', '-c',
        nargs='*',
        help='Club Number in "club000" format')
    parser.add_argument(
        '-assetTag', '-a',
        nargs='*',
        help='Asset tag of the computer to get list of software')
    parser.add_argument(
        '-hostname', '-n',
        nargs='*',
        help='Hostname of the computer to get list of software')
    parser.add_argument(
        '-license', '-l',
        nargs='*',
        help='License ID of the license to update, limit 10 licenses.')
    inv_args = parser.parse_args()

    try:

        if inv_args.club:
            club_rgx = compile(r'((club)[\d]{3})')
            for item in inv_args.club:
                club_ = club_rgx.search(item)
                if club_:
                    club_ = str(club_.group(0))
                    if len(item) == len(club_):
                        arg = {'argument': club_,
                               'func_type': 'asset'}
                        list_iter.append(arg)
                    else:
                        logger.warning('{} is not in the right format, try again'.format(item))
                        continue
                else:
                    logger.warning('{} is not in the right format, try again'.format(item))
                    continue

        if inv_args.assetTag:
            asset_tag_rgx = compile(r'([0-9]{3}[A-Z]{1}-[A-Za-z0-9]{4})')
            for item in inv_args.assetTag:
                asset_tag = asset_tag_rgx.search(item)
                if asset_tag:
                    asset_tag = str(asset_tag.group(0))
                    if len(item) == len(asset_tag):
                        arg = {'argument': asset_tag,
                               'func_type': 'asset'}
                        list_iter.append(arg)
                    else:
                        logger.warning('{} is not in the right format, try again'.format(item))
                        continue
                else:
                    logger.warning('{} is not in the right format, try again'.format(item))
                    continue

        if inv_args.hostname:
            hostname_rgx = compile(r'[A-Z]{1,3}[PC]{1}\d{3}(-[\d]{1,2})*')
            if len(inv_args.hostname) > 10:
                logger.warning('error, entered more than 10 license arguments, try again')
                sys.exit()
            for item in inv_args.hostname:
                hostname = hostname_rgx.search(item)
                if hostname:
                    hostname = str(hostname.group(0))
                    if len(item) == len(hostname):
                        arg = {'argument': hostname,
                               'func_type': 'asset'}
                        list_iter.append(arg)
                    else:
                        logger.warning('{} is not in the right format, try again'.format(item))
                        continue
                else:
                    logger.warning('{} is not in the right format, try again'.format(item))
                    continue

        if inv_args.license:
            # as of now licenseIDs are not more than 3 digits, after a while licenseIDs will probably increase
            # to 4 digits, if so, change the regex to r'([\d]{1,4})' and the len to 4 or less
            license_rgx = compile(r'([\d]{1,3})')
            for count, item in enumerate(inv_args.license):
                # limit arguments to 10, otherwise upd_dbs.upd_seats() will not work properly
                if len(item) <= 3 and count < 10:
                    license = license_rgx.search(item)
                    if license:
                        license = str(license.group(0))
                        if len(item) == len(license):
                            arg = {'argument': license,
                                   'func_type': 'license'}
                            list_iter.append(arg)
                        else:
                            logger.warning('{} is not in the right format, try again'.format(item))
                            continue
                    else:
                        logger.warning('{} is not in the right format, try again'.format(item))
                        continue
                else:
                    if count >= 10:
                        logger.warning('Too many license arguments, try again')
                    else:
                        logger.warning('{} license ID has too many digits, try again'.format(item))
                    continue

        if not inv_args.club and not inv_args.assetTag and not inv_args.hostname and not inv_args.license:
            return None
        else:
            if len(list_iter) > 0:
                return list_iter
            else:
                logger.warning('error, the argument is not in the right format, exiting')
                sys.exit()

    except(OSError, AttributeError):
        logger.critical('There was a problem getting all assets, try again', exc_info=True)
        return None


if __name__ == '__main__':

    try:
        main(inv_args())

    except(KeyError):
        logger.critical('There was a problem getting all assets, try again', exc_info=True)
