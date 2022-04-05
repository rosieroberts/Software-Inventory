import pymongo
import xmltodict
import requests
from pprint import pprint
from json import loads, dumps
from netaddr import EUI, mac_unix_expanded

from lib import config as cfg

# get all software installed with computer name
response = cfg.response


# get computer name, IP, Mac Address
hardware_response = cfg.hardware_response

def mac_address_format(mac):
    """Return formatted version of mac address

    Args:
        mac - device mac-address

    Returns:
        Formatted mac-address in format: XX:XX:XX:XX:XX:XX

    Raises:
        No error is raised.
    """
    formatted_mac = EUI(str(mac))
    formatted_mac.dialect = mac_unix_expanded
    formatted_mac = (str(formatted_mac).upper())

    return formatted_mac

client = pymongo.MongoClient("mongodb://localhost:27017/")


xml_response = response.text
hard_response = hardware_response.text



# Adding response to file (waiting on bigfix problem to get fixed due to it having errors)
with open('hardware.txt', 'w') as f:
    f.write(hard_response)

with open('software.txt', 'w') as f:
    f.write(xml_response)

#print(hardware_response.text)
#print(hardware_response)

file2 = open('hardware.txt', 'rb')
file_ = open('software.txt', 'rb')
testj = dumps(xmltodict.parse(file_))
testj = loads(testj)

testh = dumps(xmltodict.parse(file2))
testh = loads(testh)

soft_dict = {'seat_id' : None,
             'soft_name': None,
             'seat_amt': 10_000,
             'seat_info': None}

full_soft_list = []
#get software name, computer name
answer = testj['BESAPI']['Query']['Result']['Tuple']

for count, item in enumerate(answer):
    answer1 = answer[count]['Answer'][0]['#text']
    answer1_2 = answer[count]['Answer'][1]['#text']


inventory_db = client['inventory']
snipe_col = inventory_db['snipe']
snipe_del = inventory_db['deleted']

comp_list = []


# get computer name, IP, Mac address
answer2 = testh['BESAPI']['Query']['Result']['Tuple']
for count, item in enumerate(answer2):
    try:
        # initializing fresh answers to prevent duplicates
        answer1 = None
        answer1_2 = None
        answer1_3 = None

        # if answer found add to dictionary
        answer1 = answer2[count]['Answer'][0]['#text']
        answer1_2 = answer2[count]['Answer'][1]['#text']
        answer1_3 = answer2[count]['Answer'][2]['#text']

        comp_dict = {'id': None,
                     'comp_name': answer1,
                     'IP': answer1_2,
                     'mac_addr': mac_address_format(answer1_3)}
        comp_list.append(comp_dict)

    # if there was a value missing, add None
    except (KeyError):
        comp_dict = {'id': None,
                     'comp_name': None,
                     'IP': None,
                     'mac_addr': None}
        if answer1:
            comp_dict['comp_name'] = answer1
        if answer1_2:
            comp_dict['IP'] = answer1_2
        if answer1_3:
            comp_dict['mac_addr'] = mac_address_format(answer1_3)

        comp_list.append(comp_dict)

        continue

not_found = []
found = []
found_deleted = []
found_deleted_mac = []
found_del_snipe_mac = []
found_mac = []
snipe_fmac = []
for item in comp_list:
    snipe_ip = snipe_col.find({'IP': item['IP'], 'Mac Address': item['mac_addr']},
                              {'IP': 1, 'Mac Address': 1, '_id': 0})
    snipe_ip = list(snipe_ip)

    if snipe_ip:
        found.append(item)

    else:
        deleted = snipe_del.find({'_snipeit_ip_6': item['IP'], '_snipeit_mac_address_7': item['mac_addr']},
                                 {'_snipeit_ip_6': 1, '_snipeit_mac_address_7': 1, '_id': 0})
        deleted = list(deleted)
        if deleted:
            found_deleted.append(item)
        else:
            snipe_mac = snipe_col.find({'Mac Address': item['mac_addr']},
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

snipe_all = snipe_col.find({}, {'IP': 1, 'Mac Address': 1, '_id': 0})
snipe_all2 = snipe_col.find({'Category': 'Router'},{'Hostname': 1, 'IP': 1, '_id': 0})
snipe_all = list(snipe_all)
snipe_all2 = list(snipe_all2)
ct = 0
ct2 = 0
for count, item in enumerate(snipe_all):
    IP = str(item['IP'])
    mac = str(item['Mac Address'])
    for itm in comp_list:
        if IP in itm.values():
            ct += 1
        if mac in itm.values():
            ct2 += 1

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


# Use database called inventory
db = client['software']
software = 'all_software'
computers = 'club_computers'

# use collection named by date of scan
#today_date = today.strftime('%m%d%Y')
#collection_name = 'scan_' + today_date
soft_col = db[software]

# insert full scan into mongodb collection
# soft_col.insert_many()


# Adding json to file
with open('response.json', 'w') as f:
    f.write(str(testj))
    f.write(dumps(testj, indent=4))
    f.close()

#resp_j = dumps(xmltodict.parse(hardware_response.text))
#resp_j = loads(resp_j)
# print(resp_j)

#url to patch seats snipe

# license ID and seat id
url = cfg.api_url_software_seat.format('3','2007')
# asset ID
item_str = str({'asset_id': '7'})
payload = item_str.replace('\'', '\"')
response = requests.request("PATCH",
                             url=url,
                             data=payload,
                             headers=cfg.api_headers)
print(response.text)

