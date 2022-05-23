#!/usr/bin/env python3


import pymongo
import requests
from pprint import pprint
import traceback
from time import time, sleep
from lib import config as cfg
from lib import upd_dbs


def match_dbs():
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

    # get list of snipe hw devices to look up software for
    snipe_list = snipe_hw.find({}).sort('Asset Tag', pymongo.ASCENDING)
    snipe_list = list(snipe_list)
    licenses_to_remove = []
    not_added = []

    try:
        start = time()
        ct = 0
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

            if bgfix_item and 900 <= count <= 1000:
                print(item['Asset Tag'])
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
                        content = response.json()
                        ct += 1
                        status = str(content['status'])
                        status = ' '
                        if status == 'success':
                            print('updating mongo remove 1')
                            snipe_seats.update_one({'license_id': i['license_id'], 'id': i['id']},
                                                   {'$set': {'assigned_asset': None,
                                                             'asset_name': None,
                                                             'location': None}})

                            lic = snipe_lic.find_one({'License ID': i['license_id']})

                            snipe_lic.update_one({'License ID': i['license_id']},
                                                 {'$set': {'Free Seats': int(lic['Free Seats']) + 1}})

                            # updated instance of lic with updated free seat numbers if it was updated
                            lic = snipe_lic.find_one({'License ID': i['license_id']},
                                                     {'License Name': 1, 'License ID': 1, 'Total Seats': 1, 'Free Seats': 1, '_id': 0})
                            seat = snipe_seats.find_one({'license_id': i['license_id'], 'id': i['id']})

                # get list of license names in snipe
                sp_sw_list = [ln['license_name'] for ln in snipe_sw_list]

                # check if each software item in snipe is not in bigfix to see if it can be removed
                not_in_bigfix_sw = list(filter(lambda i: i not in bf_sw_list, sp_sw_list))

                # print('NOT IN BF, IN SP')
                # pprint(not_in_bigfix_sw)
                licenses_to_remove.append(not_in_bigfix_sw)

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
                                print(response.text)
                                content = response.json()
                                ct += 1
                                status = str(content['status'])
                                if status == 'success':
                                    print('updating mongo check out 2')
                                    snipe_seats.update_one({'license_id': license['License ID'], 'id': seat['id']},
                                                           {'$set': {'assigned_asset': asset_id,
                                                                     'asset_name': comp_name,
                                                                     'location': location}})

                                    # Test this line when snipe works
                                    # update license database with updated free seats (the script will update these values automatically
                                    # when the script runs again). Still thinking about this

                                    free_seats = int(license['Free Seats']) - 1
                                    snipe_lic.update_one({'License ID': license['License ID']},
                                                         {'$set': {'Free Seats': free_seats}})
                                    print('UPDATED FREE SEATS')
                                    print(snipe_lic.find_one({'License ID': license['License ID']}))

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
                                    content = response.json()
                                    ct += 1
                                    status = str(content['status'])
                                    status = ' '
                                    print('PATCH REQUEST 2, check in seats for deleting license for asset {} '.format(item_str))
                                    if status == 'success':
                                        print('updating mongo remove 3')
                                        snipe_seats.update_one({'license_id': seat['License ID'], 'id': seat['id']},
                                                               {'$set': {'assigned_asset': None,
                                                                         'asset_name': None,
                                                                         'location': None}})

                                        snipe_lic.update_one({'License ID': seat['License ID']},
                                                             {'$set': {'Free Seats': int(lic['Free Seats']) + 1}})

                                # updated instance of lic with updated free seat numbers if it was updated
                                lic = snipe_lic.find_one({'License Name': sft},
                                                         {'License Name': 1, 'License ID': 1, 'Total Seats': 1, 'Free Seats': 1, '_id': 0})

                        # check if license has any seat checked out and if not, delete license
                        if lic['Total Seats'] == lic['Free Seats']:
                            url = cfg.api_url_software_lic.format(lic['License ID'])
                            if ct == 110:
                                sleep(30)
                                ct = 0
                            response = requests.request("DELETE",
                                                        url=url,
                                                        headers=cfg.api_headers)
                            print(response.text)
                            content = response.json()
                            ct += 1
                            status = str(content['status'])
                            status = ' '
                            print('DELETE REQUEST, delete license {}'.format(lic['License ID']))
                            if status == 'success':
                                print('Deleted license no longer in use')
                                # remove license from mongodb
                                snipe_lic.delete_one({'License ID': lic['License ID']})

        print(len(snipe_list))
        end = time()
        print(end - start)

    except:  # figuring this out still
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
    url = cfg.api_url_software_seat.format('44', '41974')
    # asset ID
    item_str = str({'asset_id': ''})
    payload = item_str.replace('\'', '\"')
    response = requests.request("PATCH",
                                url=url,
                                data=payload,
                                headers=cfg.api_headers)
    print(response.text)


def create_lic():
    '''gets total list of unique licenses and adds them to snipe it if not already added'''

    snipe_lic_list = []

    # url for snipe-it licenses
    url = cfg.api_url_soft_all

    client = pymongo.MongoClient("mongodb://localhost:27017/")
    software_db = client['software_inventory']

    # all-time unique software collection (may no longer need this)
    # soft_col = software_db['all_software']
    # all_software = soft_col.find()

    # current software from bigfix with seat amounts ('sw', 'count') collection
    software_col = software_db['software']
    software = software_col.find()

    # current license collection from snipe-it
    lic_col = software_db['snipe_lic']
    all_licenses = lic_col.find()

    # all_software = list(all_software)
    software = list(software)
    all_licenses = list(all_licenses)

    for item in all_licenses:
        # create list of all license names in snipe-it
        snipe_lic_list.append(item['License Name'])

    # for each software name in bigfix
    for item in software:

        # remove utf-8 character
        soft_str = item['sw']
        soft_str = soft_str.replace('Â', '')

        if soft_str not in snipe_lic_list:
            seat_amt = int(item['count']) + 10
            item_str = str({'name': item['sw'], 'seats': seat_amt, 'category_id': '11'})
            payload = item_str.replace('\'', '\"')

            response = requests.request("POST",
                                        url=url,
                                        data=payload,
                                        headers=cfg.api_headers)
            print(response.text)

        else:
            license = lic_col.find_one({'License Name': soft_str},
                                       {'_id': 0, 'License Name': 1, 'License ID': 1, 'Total Seats': 1})

            if int(item['count']) + 20 > int(license['Total Seats']) >= int(item['count']) + 10:
                continue

            else:
                url = cfg.api_url_software_lic.format(license['License ID'])
                seat_amt = int(item['count']) + 10
                item_str = str({'seats': seat_amt})
                payload = item_str.replace('\'', '\"')

                response = requests.request("PUT",
                                            url=url,
                                            data=payload,
                                            headers=cfg.api_headers)

                content = response.json()
                status = str(content['status'])

                if status == 'success':
                    lic_col.update_one({'License ID': license['License ID']},
                                       {'$set': {'Total Seats': seat_amt}})


match_dbs()
# comp_nums()
# create_lic()
# api_call()
