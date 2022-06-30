#!/usr/bin/env python3


import pymongo
import requests
from pprint import pprint
from json import decoder
from re import compile
import traceback
from time import time, sleep
from datetime import date
from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from argparse import ArgumentParser
from lib import config as cfg
from lib import upd_dbs


test_list = ['CMPC893', 'EEPC893-1', 'EEPC893-2', 'FMPC893', 'club893', '893D-8DD6', '893-1AAC']

logger = getLogger('inventory')
# TODO: set to ERROR later on after setup
logger.setLevel(DEBUG)

file_formatter = Formatter('{asctime} {name} {levelname}: {message}', style='{')
stream_formatter = Formatter('{message}', style='{')
today = date.today()

# logfile
file_handler = FileHandler('/opt/Software-Inventory/logs/software_inventory{}.log'
                           .format(today.strftime('%m%d%Y')))
file_handler.setLevel(DEBUG)
file_handler.setFormatter(file_formatter)

# console
stream_handler = StreamHandler()
stream_handler.setFormatter(stream_formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def main(asset_list):

    match_dbs(asset_list)
    # comp_nums()
    # create_lic()
    # api_call()
    print(asset_list)


def match_dbs(asset_list):
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
    # upd_dbs.upd_snipe_lic()
    # create_lic()

    not_added = []
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
        # get list of snipe hw devices to look up software for
        snipe_list = snipe_hw.find({}).sort('Asset Tag', pymongo.ASCENDING)
        snipe_list = list(snipe_list)

    try:
        start = time()
        ct = 0
        # list of assets that could not be updated during script
        not_added = []
        # for each asset in snipe_hw look up in mongodb big_fix_hw
        for count, item in enumerate(snipe_list):
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

            if bgfix_item and count >= 0:
                print(item['Asset Tag'])
                print(count)
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

                # look for software checked out to asset and if no longer in bigfix, check license in and update db
                for i in snipe_sw_list:
                    found_item = bigfix_sw.find_one({'comp_name': i['asset_name'], 'sw': i['license_name']},
                                                    {'sw': 1, 'comp_name': 1, '_id': 0})

                    if not found_item:
                        # check in seats by sending a '' string for the asset_id field
                        url = cfg.api_url_software_seat.format(i['license_id'], i['id'])
                        if ct == 110:
                            sleep(60)
                            ct = 0
                        item_str = str({'asset_id': ''})
                        payload = item_str.replace('\'', '\"')

                        print('PATCH REQUEST 1, remove seat for id {}, no asset found. '.format(i['id']))
                        response = requests.request("PATCH",
                                                    url=url,
                                                    data=payload,
                                                    headers=cfg.api_headers)
                        print(response.text)
                        status_code = response.status_code
                        ct += 1

                        if status_code == 200:
                            content = response.json()
                            status = str(content['status'])
                            if status == 'success':
                                print('updating mongo remove 1')
                                snipe_seats.update_one({'license_id': i['license_id'], 'id': i['id']},
                                                       {'$set': {'assigned_asset': None,
                                                                 'asset_name': None,
                                                                 'location': None}})

                                lic = snipe_lic.find_one({'License ID': i['license_id']})

                                snipe_lic.update_one({'License ID': i['license_id']},
                                                     {'$set': {'Free Seats': int(lic['Free Seats']) + 1}})

                                print('UPDATED FREE SEATS 1')
                                # updated instance of lic with updated free seat numbers if it was updated
                                print(snipe_lic.find_one({'License ID': i['license_id']}))

                                print(snipe_seats.find_one({'license_id': i['license_id'], 'id': i['id']}))
                                logger.debug('Removed license {} from asset id {}'.format(i['license_id'], asset_id))

                            elif status == 'error':
                                message = str(content['messages'])
                                if message == 'Target not found':
                                    logger.debug('Asset {} is not currently active, cannot update license'.format(asset_id))
                                    not_added.append(asset_id)
                                    continue

                            else:
                                logger.debug('error, license removal not successful')
                                continue

                        else:
                            logger.debug('There was something wrong removing license from asset {}'.format(asset_id))
                            continue

                # get list of license names in snipe
                sp_sw_list = [ln['license_name'] for ln in snipe_sw_list]

                # check if each software item in snipe is not in bigfix to see if it can be removed
                not_in_bigfix_sw = list(filter(lambda i: i not in bf_sw_list, sp_sw_list))

                print('NOT IN BF, IN SP')
                pprint(not_in_bigfix_sw)

                for itm in bgfix_sw_list:
                    software = itm['sw']
                    license = snipe_lic.find_one({'License Name': software},
                                                 {'License Name': 1, 'License ID': 1, 'Total Seats': 1, 'Free Seats': 1, '_id': 0})
                    if license:
                        found_seat = snipe_seats.find_one({'assigned_asset': asset_id, 'license_id': license['License ID']},
                                                          {'id': 1, 'assigned_asset': 1, 'name': 1, 'location': 1, '_id': 0})
                        if found_seat is None:
                            if int(license['Free Seats']) >= 1:
                                # ***issues with snipe it, waiting for them to resolve before assigning seats to licenses***
                                # issue will take a while to fix, seat names are not consistent with API, keep an eye on it

                                seat = snipe_seats.find_one({'assigned_asset': None, 'license_id': license['License ID']},
                                                            {'id': 1, 'assigned_asset': 1, 'name': 1, 'location': 1, '_id': 0})

                                print('*********************')
                                print('LICENSE', license)
                                print('SEAT', seat)
                                if license['License ID'] is not None and seat['id'] is not None:
                                    url = cfg.api_url_software_seat.format(license['License ID'], seat['id'])
                                else:
                                    # license ID and seat id
                                    print(license['License ID'], seat['id'])
                                    not_added.append(itm)
                                    continue
                                if ct == 110:
                                    sleep(60)
                                    ct = 0
                                # asset ID
                                item_str = str({'asset_id': asset_id})
                                payload = item_str.replace('\'', '\"')
                                print('PATCH REQUEST check out seat for asset {} '.format(item_str))
                                response = requests.request("PATCH",
                                                            url=url,
                                                            data=payload,
                                                            headers=cfg.api_headers)

                                status_code = response.status_code
                                print(status_code)
                                print(response.text)
                                ct += 1
                                if status_code == 200:
                                    content = response.json()
                                    print(content)
                                    status = str(content['status'])

                                    if status == 'success':
                                        print('updating mongo check out 2')
                                        snipe_seats.update_one({'license_id': license['License ID'], 'id': seat['id']},
                                                               {'$set': {'assigned_asset': asset_id,
                                                                         'asset_name': comp_name,
                                                                         'location': location}})

                                        free_seats = int(license['Free Seats']) - 1
                                        snipe_lic.update_one({'License ID': license['License ID']},
                                                             {'$set': {'Free Seats': free_seats}})
                                        print('UPDATED FREE SEATS 2')
                                        print(snipe_lic.find_one({'License ID': license['License ID']}))
                                        logger.debug('added license {} to asset id {}'.format(license['License ID'], asset_id))

                                    elif status == 'error':
                                        message = str(content['messages'])
                                        if message == 'Target not found':
                                            logger.debug('Asset {} is not currently active, cannot update license'.format(asset_id))
                                            not_added.append(asset_id)
                                            continue

                                    else:
                                        logger.debug('error, license addition not successful')
                                        continue
                                else:
                                    logger.debug('There was something wrong adding license to asset {}'.format(asset_id))
                                    continue
                            else:
                                print('There are no seats available for license id {} '.format(license['License ID']))
                                continue
                        else:
                            # print('Seat found for license id {} seat {} '.format(license['License ID'], license))
                            continue
                    else:
                        continue

                # if there are licenses no longer showing up in bigfix, remove license from snipe-it
                if not_in_bigfix_sw:
                    for sft in not_in_bigfix_sw:
                        lic = snipe_lic.find_one({'License Name': sft},
                                                 {'License Name': 1, 'License ID': 1, 'Total Seats': 1, 'Free Seats': 1, '_id': 0})

                        # if there are licenses checked out to assets, check them in to allow deletion of license
                        if lic['Total Seats'] != lic['Free Seats']:
                            out_seats = snipe_seats.find({'license id': lic['License ID']})
                            out_seats = list(out_seats)

                            # if seats are checked out, check them in and update snipe_db if check in was successful
                            if out_seats:
                                for seat in out_seats:
                                    print('________________________________')
                                    print('check in seat')

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
                                    print(response.text)
                                    status_code = response.status_code
                                    ct += 1
                                    status = ' '
                                    print('PATCH REQUEST 2, check in seats for deleting license for asset {} '.format(item_str))
                                    if status_code == 200:
                                        content = response.json()
                                        status = str(content['status'])
                                        if status == 'success':
                                            print('updating mongo remove 3')
                                            snipe_seats.update_one({'license_id': seat['License ID'], 'id': seat['id']},
                                                                   {'$set': {'assigned_asset': None,
                                                                             'asset_name': None,
                                                                             'location': None}})

                                            snipe_lic.update_one({'License ID': lic['License ID']},
                                                                 {'$set': {'Free Seats': int(lic['Free Seats']) + 1}})
                                            print(snipe_lic.find_one({'License ID': lic['License ID']}))
                                            logger.debug('Removed license {} from asset id {}'.format(lic['License ID'], seat['assigned_asset']))

                                            # updated instance of lic with updated free seat numbers if it was updated
                                            print('UPDATED FREE SEATS 3')
                                            print(snipe_lic.find_one({'License Name': sft}))

                                        elif status == 'error':
                                            message = str(content['messages'])
                                            if message == 'Target not found':
                                                logger.debug('Asset {} is not currently active, cannot update license'.format(asset_id))
                                                not_added.append(asset_id)
                                                continue

                                        else:
                                            logger.debug('error, license removal not successful')
                                            continue

                                    else:
                                        logger.debug('There was something wrong removing license to asset {}'.format(asset_id))
                                        continue

                        # check if license has any seat checked out and if not, delete license
                        if lic['Total Seats'] == lic['Free Seats']:
                            print(sft, lic['License ID'])
                            print('DELETE license________________________')
                            url = cfg.api_url_software_lic.format(lic['License ID'])
                            if ct == 110:
                                sleep(30)
                                ct = 0
                            response = requests.request("DELETE",
                                                        url=url,
                                                        headers=cfg.api_headers)
                            print(response.text)
                            status_code = response.status_code
                            ct += 1

                            print('DELETE REQUEST, delete license {}'.format(lic['License ID']))
                            if status_code == 200:
                                content = response.json()
                                status = str(content['status'])
                                if status == 'success':
                                    print('Deleted license no longer in use')
                                    # remove license from mongodb
                                    snipe_lic.delete_one({'License ID': lic['License ID']})
                                    print('None if DELETED LIC FROM MONGO')
                                    print(snipe_lic.find_one({'License ID': lic['License ID']}))
                                    logger.debug('Removed license {} from snipe-it'.format(lic['License ID']))

                                elif status == 'error':
                                    message = str(content['messages'])
                                    # I do not know if this message applies to license deletion as well. Check
                                    if message == 'Target not found':
                                        logger.debug('Could not delete license {}, license not found'.format(lic['License ID']))
                                        continue

                                else:
                                    logger.debug('error, license deletion not successful')
                                    continue

                            else:
                                logger.debug('There was something wrong deleting license {}'.format(lic['License ID']))
                                continue
        print(len(snipe_list))
        end = time()
        print(end - start)
        return not_added

    except(KeyError,
           decoder.JSONDecodeError):
        logger.error('There was an error updating the licenses to Snipe-it, check licenses for asset:\n{}'
                     .format(item), exc_info=True)
        traceback.print_exc()
        pprint(item)
        print('error')


def comp_nums():
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

    # print('FOUND DIFF IP BIGFIX')
    # pprint(found_mac)
    # print('______________________________________________________')
    # print('FOUND DIFF IP SNIPE')
    # pprint(snipe_fmac)
    # print('______________________________________________________')
    # print('FOUND DIFF IP DELETED BIGFIX')
    # pprint(found_deleted_mac)
    # print('______________________________________________________')
    # print('FOUND DIFF IP DELETED SNIPE')
    # pprint(found_del_snipe_mac)
    # print('______________________________________________________')
    # print('NOT FOUND')
    # pprint(not_found)
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
    # license ID and seat id
    url = cfg.api_url_software_seat.format('3', '1999')
    # asset ID
    item_str = str({'asset_id': '5702'})
    payload = item_str.replace('\'', '\"')
    response = requests.request("PATCH",
                                url=url,
                                data=payload,
                                headers=cfg.api_headers)

    print(response.text)


def create_lic():
    '''gets total list of unique licenses and adds them to snipe it if not already added'''

    snipe_lic_list = []

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

    # for each software name in bigfix - 'software' collection in mongodb 'sw', 'count'
    for item in software:

        # remove utf-8 character
        soft_str = item['sw']
        soft_str = soft_str.replace('Â', '')

        if soft_str not in snipe_lic_list:
            print('ADDING LICENSE ***************************************')
            # url for snipe-it licenses
            url = cfg.api_url_soft_all
            seat_amt = int(item['count']) + 10
            item_str = str({'name': item['sw'], 'seats': seat_amt, 'category_id': '11'})
            payload = item_str.replace('\'', '\"')
            response = requests.request("POST",
                                        url=url,
                                        data=payload,
                                        headers=cfg.api_headers)
            print(response.text)

        else:
            # license collection from snipe
            license = lic_col.find_one({'License Name': soft_str},
                                       {'_id': 0, 'License Name': 1, 'License ID': 1, 'Total Seats': 1})

            if int(item['count']) + 20 > int(license['Total Seats']) >= int(item['count']) + 10:
                continue

            elif int(license['Total Seats']) > int(item['count']) + 20:
                print('There are more seats than there should be for license {}.\n'
                      'There should be {} but there are {}. Review.'.format(license['License Name'],
                                                                            item['count'],
                                                                            license['Total Seats']))

            else:
                print('UPDATING LICENSE ##################################')
                url = cfg.api_url_software_lic.format(license['License ID'])
                print(url)
                seat_amt = int(item['count']) + 10
                item_str = str({'seats': seat_amt})
                payload = item_str.replace('\'', '\"')
                print(item['count'], payload)
                response2 = requests.request("PATCH",
                                             url=url,
                                             data=payload,
                                             headers=cfg.api_headers)
                print(response2.text)

                content = response2.json()
                status = str(content['status'])

                if status == 'success':
                    lic_col.update_one({'License ID': license['License ID']},
                                       {'$set': {'Total Seats': seat_amt}})
                    print('Updated license {} in MongoDB'.format(license['License ID']))


def inv_args(snipe_hw_list):
    assets = []

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
    inv_args = parser.parse_args()

    try:

        if inv_args.club:
            club_rgx = compile(r'((club)[\d]{3})')
            for item in inv_args.club:
                club_ = club_rgx.search(item)
                if club_:
                    club_ = str(club_.group(0))
                    if len(item) == len(club_):
                        assets.append(club_)
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
                        assets.append(asset_tag)
                    else:
                        logger.warning('{} is not in the right format, try again'.format(item))
                        continue
                else:
                    logger.warning('{} is not in the right format, try again'.format(item))
                    continue

        if inv_args.hostname:
            hostname_rgx = compile(r'[A-Z]{1,3}[PC]{1}\d{3}(-[\d]{1,2})*')
            for item in inv_args.hostname:
                hostname = hostname_rgx.search(item)
                if hostname:
                    hostname = str(hostname.group(0))
                    if len(item) == len(hostname):
                        assets.append(hostname)
                    else:
                        logger.warning('{} is not in the right format, try again'.format(item))
                        continue
                else:
                    logger.warning('{} is not in the right format, try again'.format(item))
                    continue

        if not inv_args.club and not inv_args.assetTag and not inv_args.hostname:
            assets = snipe_hw_list

        return assets

    except(OSError, AttributeError):
        logger.critical('There was a problem getting all assets, try again', exc_info=True)
        return None


if __name__ == '__main__':
    main(inv_args(test_list))
