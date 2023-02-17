import pymongo
# import sys
from json import loads, dumps
import xmltodict
import requests
from netaddr import EUI, mac_unix_expanded
from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from json import decoder
from re import compile
from datetime import date, datetime
from pprint import pprint
from time import sleep
from lib import config as cfg
# import config as cfg


logger = getLogger('upd_dbs')
# TODO: set to ERROR later on after setup
logger.setLevel(DEBUG)

file_formatter = Formatter('{asctime} {name} {levelname}: {message}', style='{')
stream_formatter = Formatter('{message}', style='{')
today = date.today()
today_date = today.strftime('%Y-%m-%d')

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


def upd_snipe_hw():
    """Returns all current information for each host.
    this function returns SNIPE-IT's current device information
    this device information will be used to have a snapshot of
    the devices already in snipe-it.
    This function deletes the prior contents of the snipe_hw collection
    and it populates it again with the new information

    Args:
        None

    Returns:
        Hostname
        ID
        Mac Address
        IP Address
        Asset Tag
        Location

    """
    logger.debug('FUNCTION upd_snipe_hw')

    try:
        all_items = []
        url = cfg.api_url_get_all
        response = requests.request("GET", url=url, headers=cfg.api_headers)
        content = response.json()
        total_record = content['total']

        if total_record == 0:
            logger.debug('No data in Snipe-IT')
            content = None

        for offset in range(0, total_record, 500):
            querystring = {"offset": offset}
            response = requests.request("GET",
                                        url=url,
                                        headers=cfg.api_headers,
                                        params=querystring)
            content = response.json()
            for item in content['rows']:
                # only assets that have a hostname and it is category 'computer'
                if item['custom_fields']['Hostname']['value'] != '' and \
                   item['category']['id'] == 2:
                    device = {'ID': item['id'],
                              'Asset Tag': item['asset_tag'],
                              'IP': item['custom_fields']['IP']['value'],
                              'Mac Address': item['custom_fields']['Mac Address']['value'],
                              'Location': item['location']['name'],
                              'Hostname': item['custom_fields']['Hostname']['value'],
                              'Date': today_date}
                    all_items.append(device)
                else:
                    continue

        # print(*all_items, sep='\n')

        myclient = pymongo.MongoClient("mongodb://localhost:27017/")

        # use database named "inventory"
        mydb = myclient['software_inventory']

        # use collection named "snipe"
        mycol = mydb['snipe_hw']

        # delete prior scan items
        if mycol.count() > 0:
            mycol.delete_many({})

        # insert list of dictionaries
        mycol.insert_many(all_items)
        logger.debug('snipe db updated')

        return all_items

    except (KeyError,
            decoder.JSONDecodeError):
        content = None
        logger.exception('No response')
        return content


def upd_lic(*licenseID):
    ''' Function to add/update licenses in mongo for licenseID provided
        if no licenseID provided, it updates all licenses to match snipeIT'''

    logger.debug('FUNCTION upd_lic')
    if licenseID:
        print(licenseID)
        # making licenseIDs integers for all arguments provided
        licenseID = [int(i) for i in licenseID]

    myclient = pymongo.MongoClient("mongodb://localhost:27017/")

    # use database named "software_inventory"
    soft_db = myclient['software_inventory']

    # use collection named "snipe"
    snipe_lic_col = soft_db['snipe_lic']


    try:
        # get count of licenses in snipeIT
        url = cfg.api_url_soft_all
        response = requests.request("GET", url=url, headers=cfg.api_headers)
        content = response.json()
        total_record = content['total']
        count = 0
        upd_ct = 0

        # quit if no licenses in snipeIT
        if total_record == 0:
            logger.debug('No License data in Snipe-IT')
            content = None
            return content
        # all seat information for all licenses
        seat_info = []
        # seat info for only licenses in arguments
        arg_seat_info = []

        # get all current license information from mongo, pull out the license numbers to a list
        mongo_lic_list = snipe_lic_col.find({}, {'License ID': 1, '_id': 0})
        mongo_lic_list = list(mongo_lic_list)
        mg_lic_lst = []
        sn_lic_lst = []

        for lic in mongo_lic_list:
            mg_lic_lst.append(lic['License ID'])

        # for every 500 records in total license records
        for offset in range(0, total_record, 500):   # should be total_record in second argument
            querystring = {"offset": offset}
            response2 = requests.request("GET",
                                         url=url,
                                         headers=cfg.api_headers,
                                         params=querystring)
            content2 = response2.json()
            count += 1

            # for each license in snipe-it
            for ct, item in enumerate(content2['rows']):
                print('******')
                print(item['id'], ct)
                # get all license information and add it to a dictionary
                snipe_upd_date = datetime.strptime(item['updated_at']['datetime'], '%Y-%m-%d %H:%M:%S')
                license = {'License ID': item['id'],
                           'License Name': item['name'],
                           'Total Seats': item['seats'],
                           'Free Seats': item['free_seats_count'],
                           'Date': today_date,
                           'Snipe Upd Date': snipe_upd_date.strftime('%Y-%m-%d')}

                # delete prior license scan items for each License ID
                if snipe_lic_col.count({'License ID': item['id']}) > 0:
                    current_rec = snipe_lic_col.find_one({'License ID': item['id']},
                                                         {'_id': 0,
                                                          'Total Seats': 1,
                                                          'Free Seats': 1,
                                                          'Snipe Upd Date': 1})
                    snipe_lic_col.delete_many({'License ID': item['id']})
                    logger.debug('removing old mongo license records for License ID {} '
                                 'and date {}'
                                 .format(item['id'], current_rec['Snipe Upd Date']))
                # insert record
                if snipe_lic_col.count({'License ID': item['id']}) == 0:
                    snipe_lic_col.insert(license)
                    if snipe_lic_col.count({'License ID': item['id']}) != 1:
                        logger.debug('error, license {} not updated in MongoDB'.format(item['id']))    # keep track of these
                    else:
                        upd_ct += 1
                        logger.debug('License {} updated in MongoDB'.format(item['id']))

                seat_dict = {'id': item['id'],
                             'seats': item['seats'],
                             'lic_name': item['name']}
                if licenseID:
                   if item['id'] in licenseID:
                       arg_seat_info.append(seat_dict)

                else:
                    seat_info.append(seat_dict)

        # if license argument is provided, only update seats for that license
        # send a list of seat dictionaries for that license to upd_seats
        if licenseID:
            logger.debug('LICENSE ___ {} updating seats'.format(item['id']))
            # upd_seats() is very slow, so only send licenses in arguments if provided
            print('UPD LIC, seat info len {}'.format(len(arg_seat_info)))
            pprint(seat_info)
            upd_seats(arg_seat_info)

        logger.debug('{} licenses updated in MongoDB'.format(upd_ct))
        # get all license IDs from snipe to a list
        for license in seat_info:
            sn_lic_lst.append(license['id'])

        # see if the current list of mongo licenses is no longer in snipe, and remove from mongo
        for mg_lic in mg_lic_lst:
            if mg_lic not in sn_lic_lst:
                snipe_lic_col.delete_many({'License ID': mg_lic})

        # if there is no argument, update the seats for all licenses
        # this function takes hours to run
        if not licenseID:
            logger.debug('License count {}'.format(ct))
            #upd_seats(seat_info)
        # if there was a license argument provided
        else:
            for itm in licenseID:
                if itm not in sn_lic_lst:
                    # if licenseID is provided but it is not in snipeIT
                    logger.debug('License {} does not exist'.format(itm))
                    continue

        # seat information
        return seat_info

    except (KeyError,
            decoder.JSONDecodeError):
        logger.exception('error with function upd_lic()')
        return None


def upd_seats(seat_info):
    ''' Update seat information from snipeit in mongo
        this is a very slow function, it pulls the seat information from snipe-it via api
        and updates mongo.
        seat info is all the seats sent from upd_lic regardless of argument or not. 
        gets a list of dictionaries:
        seat_dict = {'id': item['id'],
                     'seats': item['seats'],
                     'lic_name': item['name']}'''

    myclient = pymongo.MongoClient("mongodb://localhost:27017/")

    # use database named "software_inventory"
    soft_db = myclient['software_inventory']

    # use database named "inventory"
    hard_db = myclient['inventory']

    # use collection for hardware
    hardware_col = hard_db['snipe']

    # use collection for deleted hardware
    deleted_hw_col = hard_db['deleted']

    # use collection for seats
    snipe_seat_col = soft_db['snipe_seat']

    # use collection for amount of assets with software
    software = soft_db['software']

    seat_list = []

    asset_tag_rgx = compile(r'([0-9]{3}[A-Z]{1}-[A-Za-z0-9]{4})')

    logger.debug('FUNCTION upd_seats')

    # get all current seat information from mongo, pull out the seat numbers to a list
    mongo_seat_list = snipe_seat_col.find({}, {'id': 1, '_id': 0})
    mongo_seat_list = list(mongo_seat_list)
    mg_seat_lst = []
    sn_seat_lst = []

    for seat in mongo_seat_list:
        mg_seat_lst.append(seat['id'])
    count = 0
    # for each dict (seat)
    for item in seat_info:
        try:
            url2 = cfg.api_url_soft_all_seats.format(item['id'])

            # for every 50 seats in total seats per license
            for offset2 in range(0, item['seats'], 50):
                querystring = {'offset': offset2}
                # get seat information from snipe-it and add to mongodb
                response3 = requests.request("GET",
                                             url=url2,
                                             headers=cfg.api_headers,
                                             params=querystring)
                content3 = response3.json()
                # sleep if number of requests is 90 to prevent errors
                count += 1
                if count == 90:
                    sleep(60)
                    count = 0
                for itm in content3['rows']:
                    if itm['assigned_asset'] is None:
                        assigned_asset = None
                        location = None
                        hostname = None
                        assigned_asset_name = None
                    else:
                        assigned_asset = itm['assigned_asset']['id']
                        assigned_asset_name = itm['assigned_asset']['name']
                        asset_name = asset_tag_rgx.search(assigned_asset_name)
                        if asset_name:
                            asset_name = str(asset_name.group(0))
                            assigned_asset_name = asset_name
                        location = itm['location']['name']
                        asset = hardware_col.find_one({'ID': assigned_asset},
                                                      {'Hostname': 1, '_id': 0})
                        if asset:
                            # if asset is found in active snipe db
                            hostname = asset['Hostname']
                        else:
                            # else look in the deleted assets db
                            asset = deleted_hw_col.find_one({'id': assigned_asset},
                                                            {'_snipeit_hostname_8': 1, '_id': 0})
                            if asset:
                                hostname = asset['_snipeit_hostname_8']
                            else:
                                hostname = 'Not Found'

                    seat = {'id': itm['id'],
                            'license_id': itm['license_id'],
                            'assigned_asset': assigned_asset,
                            'location': location,
                            'seat_name': itm['name'],
                            'asset_name': hostname,
                            'asset_tag': assigned_asset_name,
                            'license_name': item['lic_name'],
                            'date': today_date}
                    seat_list.append(seat)

            # count of current assets with license
            asset_ct = software.find_one({'sw': item['lic_name']}, {'_id': 0, 'count': 1})
            if not asset_ct:
                bigfix_asset_ct = 0
            else:
                bigfix_asset_ct = asset_ct['count']

            logger.info('BigFix asset_ct {} for software {}'.format(bigfix_asset_ct, item['id']))
            if snipe_seat_col.count({'license_id': item['id']}) > 0:
                logger.debug('removing existing {} mongo entries for license id {}'
                             .format(snipe_seat_col.count({'license_id': item['id']}), item['id']))
                snipe_seat_col.delete_many({'license_id': item['id']})
            print('^^^^^^^^^^^^^^^^^')
            # if there are more than 10 licenses being updated,
            # means that no arguments were used and all seats are getting updated
            # testing adding seats for all licenses in an asset if the asset was passed in args.
            # that would be more than 10 licenses too.
            print(len(seat_info))
            if len(seat_info) >= 100:
                print('MORE THAN 100')
                for seat in seat_list:
                    sn_seat_lst.append(seat['id'])

                # see if the current list of mongo seats is no longer in snipe, and if not, remove from mongo
                for mg_seat in mg_seat_lst:
                    if mg_seat not in sn_seat_lst:
                        snipe_seat_col.delete_many({'id': mg_seat})
            times = 0
            # iterate every 1000 seats in seat_list and add to mongo
            for i in range(0, len(seat_list), 1000):
                print('LICENSE {} *********'.format(item['id']))
                # pprint(seat_list[i:i + 1000])

                times += 1
                # insert up to 1000 seats at a time to mongo
                snipe_seat_col.insert_many(seat_list[i:i + 1000])
                logger.info('Inserted seats for license {} into snipe seats collection'.format(item['id']))

            logger.debug('snipe db seats updated')
            logger.info('Seat amount - {} for licenseID {}'.format(len(seat_list),       # delete this line
                                                                   item['id']))
            seat_list = []

            logger.info('Current assigned seats in mongo {} for licenseID {}'
                        .format(snipe_seat_col.count({'license_id': item['id'],
                                                      'asset_name': {'$ne': None}}),
                                item['id']))

            # if count of license seats currently in snipeIT does not match with current count in BigFix
            if snipe_seat_col.count({'license_id': item['id'], 'asset_name': {'$ne': None}}) != bigfix_asset_ct:
                # figure out what to do here, perhaps send the ones that do not match to a list to review...
                logger.info('LicenseID {} Snipe_IT count {} does not match BigFix {}'
                            .format(item['id'],
                                    snipe_seat_col.count({'license_id': item['id'],
                                                          'asset_name': {'$ne': None}}),
                                    bigfix_asset_ct))

            else:
                logger.info('LicenseID {} count {} in Snipe_IT matches BigFix {}'
                            .format(item['id'], 
                                    snipe_seat_col.count({'license_id': item['id'],
                                                          'asset_name': {'$ne': None}}),
                                    bigfix_asset_ct))
        except(KeyError,
               decoder.JSONDecodeError):
            logger.exception('Problem with adding seats')


def upd_bx_hw():
    """Returns all current hardware information in bigfix

    Args:
        None

    Returns:
        Name
        IP
        Mac Address

    """
    logger.debug('FUNCTION upd_bx_hw')

    try:
        # get computer name, IP, Mac Address
        hardware_response = cfg.hardware_response

        hard_response = hardware_response.text

        # Adding response to file (waiting on bigfix problem to get fixed due to it having errors)
        with open('hardware.txt', 'w') as f:
            f.write(hard_response)

        file_ = open('hardware.txt', 'rb')
        testh = dumps(xmltodict.parse(file_))
        testh = loads(testh)

        comp_list = []

        # get computer name, IP, Mac address
        answer = testh['BESAPI']['Query']['Result']['Tuple']
        for count, item in enumerate(answer):
            try:
                # initializing fresh answers to prevent duplicates
                answer1 = None
                answer1_2 = None
                answer1_3 = None

                # if answer found add to dictionary
                answer1 = answer[count]['Answer'][0]['#text']
                answer1_2 = answer[count]['Answer'][1]['#text']
                answer1_3 = answer[count]['Answer'][2]['#text']

                comp_dict = {'comp_name': answer1,
                             'IP': answer1_2,
                             'mac_addr': mac_address_format(answer1_3),
                             'date': today_date}

                comp_list.append(comp_dict)

            # if there was a value missing, add None
            except (KeyError):
                comp_dict = {'comp_name': None,
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

        # print(*comp_list, sep='\n')

        myclient = pymongo.MongoClient("mongodb://localhost:27017/")

        # use database named "inventory"
        mydb = myclient['software_inventory']

        # use collection named "snipe"
        mycol = mydb['bigfix_hw']

        # delete prior scan items
        if mycol.count() > 0:
            mycol.delete_many({})

        # insert list of dictionaries
        mycol.insert_many(comp_list)
        logger.debug('bigfix harware updated')
        print(comp_list)

        return comp_list

    except (KeyError,
            decoder.JSONDecodeError):
        content = None
        logger.exception('No response')
        return content


def upd_bx_sw():
    """Returns all current software information in bigfix

    Args:
        None

    Returns:
        Asset Name
        Software Name

    """
    logger.debug('FUNCTION upd_bx_sw')

    try:
        # get computer name, IP, Mac Address
        software_response = cfg.response
        software_response2 = cfg.response2

        soft_response = software_response.text
        soft_response2 = software_response2.text

        # Adding response to file
        with open('software.txt', 'w') as f:
            f.write(soft_response)

        # Adding response to file, this is for corporate laptops, looking for putty.exe
        with open('software2.txt', 'w') as f:
            f.write(soft_response2)

        logger.debug('software updated')
        file_ = open('software.txt', 'rb')
        tests = dumps(xmltodict.parse(file_))
        tests = loads(tests)

        soft_list = []
        # list of all lines of software names in bigfix
        all_software = []

        # get software name, computer name
        answer = tests['BESAPI']['Query']['Result']['Tuple']
        for count, item in enumerate(answer):

            try:
                # initializing fresh answers to prevent duplicates
                answer1 = None
                answer1_2 = None

                # if answer found add to dictionary
                answer1 = answer[count]['Answer'][0]['#text']
                answer1_2 = answer[count]['Answer'][1]['#text']

                soft_dict = {'comp_name': answer1,
                             'sw': answer1_2,
                             'date': today_date}
                soft_list.append(soft_dict)

                all_software.append(answer1_2)

            # if there was a value missing, add None
            except (KeyError):
                soft_dict = {'comp_name': answer1,
                             'sw': answer1_2,
                             'date': today_date}
                if answer1:
                    soft_dict['comp_name'] = answer1
                if answer1_2:
                    soft_dict['sw'] = answer1_2

                soft_list.append(soft_dict)

                continue

        # print(*soft_list, sep='\n')

        myclient = pymongo.MongoClient("mongodb://localhost:27017/")

        # use database named software_inventory"
        software_db = myclient['software_inventory']

        # unique software collection
        soft_col = software_db['all_software']

        # testing another software collection
        software = software_db['software']

        # rename 'old' previous collection 'prev_bigfix_sw' to later drop
        prev_sw = software_db['prev_bigfix_sw']
        prev_sw.rename('del_prev_bigfix_sw')
        del_prev = software_db['del_prev_bigfix_sw']

        # use collection named "bigfix_sw" and rename
        bigfix_sw = software_db['bigfix_sw']
        # rename previous bigfix sw collection
        bigfix_sw.rename('prev_bigfix_sw')
        prev_sw = software_db['prev_bigfix_sw']

        # create new collection named 'bigfix_sw'
        new_sw = software_db['bigfix_sw']

        # delete prior scan items
        if new_sw.count() > 0:
            new_sw.delete_many({})
        print('inserting items into new db')
        # insert list of dictionaries
        print('soft_list len', len(soft_list))
        new_sw.insert_many(soft_list)
        logger.debug('bigfix software updated')

        # get amount of seats(instances) for each license(software)
        soft_count = {i: all_software.count(i) for i in all_software}

        soft_count_list = []
        for sftw, count in soft_count.items():
            soft_count_itm = {'sw': sftw,
                              'count': count}
            soft_count_list.append(soft_count_itm)

        # get unique list of software in all devices (all time)
        all_software = set(all_software)

        for item in all_software:
            found_item = soft_col.find_one({'sw': item})

            if not found_item:
                soft_dict1 = {'sw': item}
                soft_col.insert_one(soft_dict1)
            else:
                continue

        if software.count() > 0:
            software.delete_many({})
        software.insert_many(soft_count_list)

        if new_sw.count() > 150000:
            # remove 'old' previous collection 'prev_bigfix_sw'

            print('deleted old bigfix collection')
            del_prev.drop()

        return soft_list

    except (KeyError,
            decoder.JSONDecodeError):
        content = None
        logger.exception('No response')
        return content


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


if __name__ == '__main__':
    upd_snipe_hw()
    upd_bx_hw()
    upd_bx_sw()
    upd_lic()
    upd_seats([])
