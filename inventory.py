import pymongo
import xmltodict
import requests
from pprint import pprint

from lib import config as cfg
from lib import upd_dbs


def comp_nums():
    client = pymongo.MongoClient("mongodb://localhost:27017/")

    software_db = client['software_inventory']
    inventory_db = client['inventory']
    snipe_hw_col = software_db['snipe_hw']
    snipe_del = inventory_db['deleted']

    comp_list = upd_dbs.upd_bx_hw()


def mac_address_format(mac):

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


comp_nums()
