import pymongo
import requests
from pprint import pprint
import traceback
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
    snipe_list = snipe_hw.find({})
    snipe_list = list(snipe_list)

    # get license list from mongo 'snipe_lic'
    license_list = snipe_lic.find({}, {'License Name': 1, 'License ID': 1, '_id': 0})
    license_list = list(license_list)

    try:

        # for each asset in snipe_hw look up in mongodb big_fix_hw
        for count, item in enumerate(snipe_list):
            if count <= 6:
                asset_id = item['ID']
                location = item['Location']
                bgfix_item = bigfix_hw.find_one({'comp_name': item['Hostname'],
                                                 'IP': item['IP'],
                                                 'mac_addr': item['Mac Address']},
                                                {'comp_name': 1, 'IP': 1,
                                                 'mac_addr': 1, '_id': 0})
            if bgfix_item and count <= 6:
                # find all software with comp_name in bigfix_sw db
                bgfix_sw_list = bigfix_sw.find({'comp_name': item['Hostname']},
                                               {'sw': 1, 'comp_name': 1, '_id': 0})
                bgfix_sw_list = list(bgfix_sw_list)
                pprint(bgfix_sw_list)

                for itm in bgfix_sw_list:
                    software = itm['sw']
                    print(software)
                    comp_name = itm['comp_name']
                    print(comp_name)
                    license = snipe_lic.find_one({'License Name': software},
                                                 {'License Name': 1, 'License ID': 1})

                    found_seat = snipe_seats.find_one({'assigned_asset': asset_id, 'license_id': license['License ID']},
                                                      {'id': 1, 'assigned_asset': 1, 'name': 1, 'location': 1, '_id': 0})

                    if not found_seat:
                        seat = snipe_seats.find_one({'assigned_asset': None, 'license_id': license['License ID']},
                                                    {'id': 1, 'assigned_asset': 1, 'name': 1, 'location': 1, '_id': 0})

                        print(count)
                        print(license)
                        print(seat)
                        print(license['License ID'])
                        # license ID and seat id
                        url = cfg.api_url_software_seat.format(license['License ID'], seat['id'])
                        # asset ID
                        item_str = str({'asset_id': asset_id})
                        payload = item_str.replace('\'', '\"')
                        response = requests.request("PATCH",
                                                    url=url,
                                                    data=payload,
                                                    headers=cfg.api_headers)
                        print(response.text)
                        content = response.json()
                        status = str(content['status'])
                        if status == 'success':
                            updated_seat = snipe_seats.update_one({'license_id': license['License ID'], 'id': seat['id']},
                                                                  {'$set': {'assigned_asset': asset_id,
                                                                            'location': location}})

                            print(updated_seat)
                    else:
                        continue

    except:  # figuring this out still
        traceback.print_exc()
        print('error')


def comp_nums():
    client = pymongo.MongoClient("mongodb://localhost:27017/")

    software_db = client['software_inventory']
    inventory_db = client['inventory']
    snipe_hw_col = software_db['snipe_hw']
    snipe_del = inventory_db['deleted']

    comp_list = upd_dbs.upd_bx_hw()

    not_found = []
    found = []
    found_deleted = []
    found_deleted_mac = []
    found_del_snipe_mac = []
    found_mac = []
    snipe_fmac = []
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

    print('FOUND DIFF IP BIGFIX')
    pprint(found_mac)
    print('______________________________________________________')
    print('FOUND DIFF IP SNIPE')
    pprint(snipe_fmac)
    print('______________________________________________________')
    print('FOUND DIFF IP DELETED BIGFIX')
    pprint(found_deleted_mac)
    print('______________________________________________________')
    print('FOUND DIFF IP DELETED SNIPE')
    pprint(found_del_snipe_mac)
    print('______________________________________________________')
    print('NOT FOUND')
    pprint(not_found)
    print(len(found), 'found devices')
    print(len(comp_list), 'all bigfix devices')
    print(len(found_mac), 'diff ip in bigfix')
    print(len(found_deleted), 'found in deleted')
    print(len(found_deleted_mac), 'found in deleted_mac')
    print(len(not_found), 'not found')


def api_call():
    # license ID and seat id
    url = cfg.api_url_software_seat.format('3', '2007')
    # asset ID
    item_str = str({'asset_id': '7'})
    payload = item_str.replace('\'', '\"')
    response = requests.request("PATCH",
                                url=url,
                                data=payload,
                                headers=cfg.api_headers)
    print(response.text)


def create_lic():
    '''gets total list of unique licenses and adds them to snipe it if not already added'''

    snipe_lic = []

    # url for snipe-it licenses
    url = cfg.api_url_soft_all

    client = pymongo.MongoClient("mongodb://localhost:27017/")
    software_db = client['software_inventory']

    # unique software collection
    soft_col = software_db['all_software']
    all_software = soft_col.find()

    # license collection
    lic_col = software_db['snipe_lic']
    all_licenses = lic_col.find({}, {'_id': 0, 'License Name': 1, 'License ID': 1})

    all_software = list(all_software)
    all_licenses = list(all_licenses)

    for item in all_licenses:
        snipe_lic.append(item['License Name'])

    for item in all_software:

        print(item['sw'])

        if item['sw'] in snipe_lic:
            print('FOUND')
            continue

        else:
            print('NOT FOUND')
            item_str = str({'name': item['sw'], 'seats': '999', 'category_id': '11'})
            payload = item_str.replace('\'', '\"')

            response = requests.request("POST",
                                        url=url,
                                        data=payload,
                                        headers=cfg.api_headers)

            print(response.text)


def get_snipe_assets():
    ''' Using the license name, look for all assets that have that license, and match with snipe it Assets to assign seats.
        cross reference with big_fix_HW database to make sure it is the right asset.'''
    pass


# comp_nums()
match_dbs()
# create_lic()
