#!/usr/bin/env python3

import pytest
import Software_Inventory.inventory as inv
import lib.hardware_update as hardware
import lib.license_update as license
import lib.snipe_hw_update as snipe_hw
import lib.snipe_lic_update as snipe_lic

# from lib.inv_mail import send_mail
import lib.config as cfg
from re import compile
from datetime import date
# from time import time, ctime
import pymongo
from logging import (
    FileHandler,
    Formatter,
    StreamHandler,
    getLogger,
    DEBUG)


today = date.today()

# logging set up
logger = getLogger(__name__)

file_formatter = Formatter('{asctime} {threadName}: {message}', style='{')
stream_formatter = Formatter('{threadName} {message}', style='{')

# logfile
file_handler = FileHandler('/opt/Software_Inventory/logs/tests{}.log'
                           .format(today.strftime('%m%d%Y')))
file_handler.setLevel(DEBUG)
file_handler.setFormatter(file_formatter)

# console
stream_handler = StreamHandler()
stream_handler.setFormatter(stream_formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

client = pymongo.MongoClient("mongodb://localhost:27017/")
software_db = client['software_inventory']
asset_db = client['inventory']
snipe_hw = software_db['snipe_hw']
snipe_lic = software_db['snipe_lic']
snipe_seats = software_db['snipe_seat']
deleted = asset_db['deleted']
bigfix_hw = software_db['bigfix_hw']
bigfix_sw = software_db['bigfix_sw']


mac_regex = compile(r'^([0-9A-Fa-f]{2}[:]){5}([0-9A-Fa-f]{2})$')
ip_regex = compile(r'(?:\d+\.){3}\d+')


@pytest.fixture()
def get_club():
    club = list(snipe_hw.aggregate([{'$sample': {'size': 1}}, {'$project': {'Location': 1, '_id': 0}}]))
    club = club[0]['Location']
    print(club)
    return club


@pytest.fixture()
def get_assettag():
    asset_tag = list(snipe_hw.aggregate([{'$sample': {'size': 1}}, {'$project': {'Asset Tag': 1, '_id': 0}}]))
    asset_tag = asset_tag[0]['Asset Tag']
    print(asset_tag)
    return asset_tag


@pytest.fixture()
def get_hostname():
    hostname = list(snipe_hw.aggregate([{'$sample': {'size': 1}}, {'$project': {'Hostname': 1, '_id': 0}}]))
    hostname = hostname[0]['Hostname']
    print(hostname)
    return hostname


@pytest.fixture
def get_license():
    print('***')
    license = list(snipe_lic.aggregate([{'$sample': {'size': 1}}, {'$project': {'License ID': 1, '_id': 0}}]))
    print(license)
    if len(license) > 0:
        license = license[0]['License ID']
    return license


@pytest.fixture
def get_assets(get_club, get_assettag, get_hostname):
    asset_list = inv.get_asset_list([get_club, get_assettag, get_hostname])
    print('ASSET LIST')
    # print(asset_list)
    return asset_list


@pytest.fixture
def get_lic_assets(get_license):
    asset_lic_list = inv.get_lic_list([get_license])
    asset_lic_list = []
    print('LICENSE ASSET LIST')
    print(asset_lic_list)
    return asset_lic_list


@pytest.fixture
def match(get_assets, get_lic_assets):
    get_assets.extend(get_lic_assets)
    results = inv.match_dbs(get_assets)
    print(results)
    # added this line to see the test, it will fail.
    # results['License']
    return results


class testHardwareUpdate:
    """Test class for hardware_update"""

    def test_1(self):

        pass

    def test_2(self):
        pass


class testLicenseUpdate:
    """Test class for license_update"""

    def test_1(self):
        pass

    def test_2(self):
        pass


class testSnipehwUpdate:
    """Test class for snipe_hw_update"""

    def test_1(self):
        pass

    def test_2(self):
        pass


class testSnipeLicUpdate:
    """Test class for snipe_lic_update"""

    def test_1(self):
        pass

    def test_2(self):
        pass



class TestInventory:
    """Test class for Inventory

    # tests for inventory.py

    FUNCTIONS:

    main
    match_dbs
    comp_nums
    check_in
    create_lic
    inv_args


    """
    # main
    def test_1(self):
        pass

    # match_dbs
    def test_2(self, match):
        # all api calls info
        api = match[0]
        # all current mongo info after updates
        mongo = match[1]
        # licenses that could not be updated, due to asset not being available
        not_added = match[2]
        # licenses that could not be updated due to no free seats
        # not_free_seats = match[3]

        if len(api) > 0 and len(mongo) > 0:
            for dct in api:
                license_id = dct['license_id']
                seat_id = dct['seat_id']
                asset_id = dct['asset_id']
                asset_tag = dct['asset_tag']
                asset_name = dct['asset_name']

                if dct['type'] == 'checkout_seat':
                    if dct['status'] == 'success':
                        for itm in mongo:
                            if itm['license_id'] == license_id:
                                assert itm['seat_id'] == seat_id
                                assert itm['asset_id'] == asset_id
                                assert itm['asset_tag'] == asset_tag
                                assert itm['asset_name'] == asset_name
                    if dct['status'] == 'error':
                        pass

                if dct['type'] == 'remove seat':
                    if dct['status'] == 'success':
                        for item in mongo:
                            if item['license_id'] == license_id:
                                assert item['seat_id'] == seat_id
                                assert item['asset_id'] is None
                                assert item['asset_tag'] is None
                                assert item['location'] is None
                                assert item['asset_tag'] is None
                                assert item['asset_name'] is None

                if dct['type'] == 'remove_license':
                    if dct['status'] == 'success':
                        for i in mongo:
                            if i['license_id'] == license_id:
                                assert i['seat_id'] is None
                                assert i['seat_license_id'] is None
                                assert i['asset_id'] is None
                                assert i['asset_tag'] is None
                                assert i['location'] is None
                                assert i['asset_tag'] is None
                                assert i['asset_name'] is None

                if dct['status'] == 'error':
                    assert not_added > 0
                    assert dct['asset_id'] in not_added
                else:
                    assert len(not_added) == 0

    # comp_nums
    def test_3(self):
        pass

    # test for each key in results from club_scan
    def test_4(self):
        pass

    # connect
    def test_5(self):
        pass

    # mongo locations test
    def test_6(self):
        pass


class TestInvMail:
    """Test for mail_inv"""

    def test_1(self):
        pass


if __name__ == '__main__':
    pytest.main()
