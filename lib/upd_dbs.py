import pymongo
from json import loads, dumps
import xmltodict
import requests
from netaddr import EUI, mac_unix_expanded
from logging import FileHandler, Formatter, StreamHandler, getLogger, INFO
from json import decoder
from datetime import date
# from pprint import pprint
from time import sleep
from lib import config as cfg
# import config as cfg


logger = getLogger('upd_dbs')
# TODO: set to ERROR later on after setup
logger.setLevel(INFO)

file_formatter = Formatter('{asctime} {name} {levelname}: {message}', style='{')
stream_formatter = Formatter('{message}', style='{')
today = date.today()
today_date = today.strftime('%m-%d-%Y')

# logfile
file_handler = FileHandler('/opt/Software-Inventory/logs/software_inventory{}.log'
                           .format(today.strftime('%m%d%Y')))
file_handler.setLevel(INFO)
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

    try:
        all_items = []
        url = cfg.api_url_get_all
        response = requests.request("GET", url=url, headers=cfg.api_headers)
        content = response.json()
        total_record = content['total']

        if total_record == 0:
            logger.info('No data in Snipe-IT')
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


def upd_snipe_lic():
    """Returns all current license information in snipe
    and updates mongodb collection snipe_lic

    Args:
        None

    Returns:
        License ID
        License Name
        Total Seats
        Manufacturer

    """

    myclient = pymongo.MongoClient("mongodb://localhost:27017/")

    # use database named "software_inventory"
    soft_db = myclient['software_inventory']

    # use database named "inventory"
    hard_db = myclient['inventory']

    # use collection named "snipe"
    snipe_lic_col = soft_db['snipe_lic']

    # use collection for seats
    snipe_seat_col = soft_db['snipe_seat']

    # use collection for hardware
    hardware_col = hard_db['snipe']

    try:
        all_items = []
        seat_list = []
        url = cfg.api_url_soft_all
        response = requests.request("GET", url=url, headers=cfg.api_headers)
        content = response.json()
        total_record = content['total']
        count = 0

        # get total number of records and quit if none
        if total_record == 0:
            logger.info('No License data in Snipe-IT')
            content = None
            return content

        # for every 500 records in total license records
        for offset in range(65, total_record, 500):   # should be 0 instead of 65
            querystring = {"offset": offset}
            response2 = requests.request("GET",
                                         url=url,
                                         headers=cfg.api_headers,
                                         params=querystring)
            content2 = response2.json()
            count += 1
            for item in content2['rows']:
                # get all license information and add it to a dictionary
                print('BEGIN LICENSE _______________________________________')
                print(item['id'])
                ct = 0
                device = {'License ID': item['id'],
                          'License Name': item['name'],
                          'Total Seats': item['seats'],
                          'Free Seats': item['free_seats_count'],
                          'Date': today_date}

                # append each dictionary of license information into list of licenses
                all_items.append(device)

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
                        ct += 1
                        if itm['assigned_asset'] is None:
                            assigned_asset = None
                            location = None
                            hostname = None
                        else:
                            assigned_asset = itm['assigned_asset']['id']
                            location = itm['location']['name']
                            asset = hardware_col.find_one({'ID': assigned_asset},
                                                          {'Hostname': 1, '_id': 0})
                            if asset:
                                hostname = asset['Hostname']

                        seat = {'id': itm['id'],
                                'license_id': itm['license_id'],
                                'assigned_asset': assigned_asset,
                                'location': location,
                                'seat_name': itm['name'],
                                'asset_name': hostname,
                                'license_name': item['name'],
                                'date': today_date}

                        seat_list.append(seat)

                    print('LICENSE ', item['id'], 'seat count', ct)
                if snipe_seat_col.count() > 0:
                    snipe_seat_col.delete_many({'license_id': item['id']})
                deleted_test = snipe_seat_col.find_one({'license_id': item['id']})
                print('is mongo deleted?')
                print(deleted_test is None)

                times = 0
                for i in range(0, len(seat_list), 1000):
                    print('LICENSE ', item['id'], '********')
                    print('count', times, 'i', i)

                    # pprint(seat_list[i:i + 1000])

                    times += 1
                    # print(i)
                    snipe_seat_col.insert_many(seat_list[i:i + 1000])
                    print('Inserted seats for license {} into snipe seats collection'.format(item['id']))

                logger.debug('snipe db seats updated')
                print('FINAL len seat_list ', len(seat_list))
                seat_list = []
                print('CT Seat amt ', ct)

            # delete prior scan items
            if snipe_lic_col.count() > 0:
                snipe_lic_col.delete_many({})

            # insert list of dictionaries
            snipe_lic_col.insert_many(all_items)
            logger.debug('snipe db licenses updated')

        # print(*all_items, sep='\n')

        return all_items

    except (KeyError,
            decoder.JSONDecodeError):
        content = None
        logger.exception('No response')
        return content


def upd_bx_hw():
    """Returns all current hardware information in bigfix

    Args:
        None

    Returns:
        Name
        IP
        Mac Address

    """

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

    try:
        # get computer name, IP, Mac Address
        software_response = cfg.response

        soft_response = software_response.text

        # Adding response to file
        with open('software.txt', 'w') as f:
            f.write(soft_response)
        print('software updated')
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
        print(count)
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
        print(prev_sw)

        # create new collection named 'bigfix_sw'
        new_sw = software_db['bigfix_sw']
        print(new_sw)

        # delete prior scan items
        if new_sw.count() > 0:
            new_sw.delete_many({})
        print('inserting items into new db')
        # insert list of dictionaries
        print(len('soft_list len'), soft_list)
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
            print(del_prev)
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
    upd_snipe_lic()
