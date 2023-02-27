from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from datetime import date
import pymongo
import sys
from re import compile

# get today's date
today = date.today()
today_date = today.strftime('%m-%d-%Y')

logger = getLogger('getAssets')
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


class getData:
    """ Class that converts command line arguments,
        hostname, club, asset_tag and licenses and creates a list of
        dictionaries with the asset information stored in mongo that is
        associated with the argument
        """
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    software_db = client['software_inventory']
    asset_db = client['inventory']
    # Snipe HW collection
    snipe_hw = software_db['snipe_hw']
    # Snipe Seats collection
    snipe_seats = software_db['snipe_seat']
    # deleted assets collection
    deleted = asset_db['deleted']

    def __init__(self):
        # assets info from args and if no args, all assets in snipeIT
        self.asset_list_hw = []
        # assets info for assets checked out to license provided in args
        self.asset_list_sw = []
        # license names for any license arguments if provided
        self.arg_licenses = []

    def get_all_assets(self):
        # get list of snipe hw devices to look up software for.
        # If no arguments, it returns full list of all hosts that
        # have software sorted
        self.asset_list_hw = self.snipe_hw.find({}).sort('Asset Tag',
                                                         pymongo.ASCENDING)
        self.asset_list_hw = list(self.asset_list_hw)

    def get_asset_list(self, asset_list):
        '''takes in list of arguments such as asset hostnames, club, asset_tag,
        and returns list of dictionaries from snipe_hw db. '''
        if not asset_list:
            return None
        club_rgx = compile(r'((club)[\d]{3})')
        asset_tag_rgx = compile(r'([0-9]{3}[A-Z]{1}-[A-Za-z0-9]{4})')
        hostname_rgx = compile(r'[A-Z]{1,3}[PC]{1}\d{3}(-[\d]{1,2})*')
        deleted_assets_ct = 0
        not_found_assets_ct = 0
        found_assets_ct = 0
        for item in asset_list:
            club = club_rgx.search(item)
            asset_tag = asset_tag_rgx.search(item)
            hostname = hostname_rgx.search(item)
            if club:
                assets = self.snipe_hw.find({'Location': item})
            elif asset_tag:
                assets = self.snipe_hw.find({'Asset Tag': item})
            elif hostname:
                assets = self.snipe_hw.find({'Hostname': item})
            else:
                # skip those args that are not in the right format
                continue
            assets = list(assets)
            if assets:
                for asset in assets:
                    self.asset_list_hw.append(asset)
                    found_assets_ct += 1
            else:
                # check if the asset is currently deleted
                if asset_tag:
                    del_asset = self.deleted.find_one({'asset_tag': item})
                    if not del_asset:
                        continue
                    if del_asset['Category'] != 'Computer' or \
                            del_asset['Category'] != 'POS':
                        continue
                    asset = {'ID': del_asset['id'],
                             'Asset Tag': del_asset['asset_tag'],
                             'IP': del_asset['_snipeit_ip_6'],
                             'Mac Address': del_asset['_snipeit_mac_address_7'],
                             'Location': del_asset['Location'],
                             'Hostname': del_asset['_snipeit_hostname_8']}
                    deleted_assets_ct += 1
                    self.asset_list_hw.append(asset)
                else:
                    # skip args in the right format but are not found anywhere
                    not_found_assets_ct += 1
                    continue
        # only found assets and deleted assets associated with a seat will be
        # returned. This message for review.
        logger.debug('Asset {}'.format(item['Asset Tag']))
        logger.debug('Assets found {}'.format(found_assets_ct))
        if not_found_assets_ct > 0:
            logger.debug('Assets not found {}'.format(not_found_assets_ct))
        if deleted_assets_ct > 0:
            logger.debug('Assets deleted {}'.format(deleted_assets_ct))

    def get_lic_list(self, lic_list):
        ''' Only runs when a list of licenses ('123' format) is provided in
            arguments take list of licenses and return list of assets that are
            associated with that license this function only runs
            when -l <licenseID> is added as an argument '''
        license_rgx = compile(r'([\d]{1,3})')
        if not lic_list:
            return None
        deleted_assets_ct = 0
        not_found_assets_ct = 0
        found_assets_ct = 0
        for item in lic_list:
            # for each license in list of licenses provided in command line
            lic = license_rgx.search(item)
            if not lic:
                continue
            # license found in db, add to list
            found_lic = self.snipe_seats.find_one({'license_id': int(item)},
                                                  {'_id': 0, 'license_name': 1})
            if found_lic:
                self.arg_licenses.append(found_lic['license_name'])
            # make sure the input matches the license number regex and looks
            # only for license with active assets seats with no assets
            # associated with them will have a None in asset_name in the
            # snipe_seats collection
            # this is getting licenses WITH SEATS
            lic_item = self.snipe_seats.find({'license_id': int(item),
                                              'asset_name': {'$ne': None}})
            lic_item = list(lic_item)
            if not lic_item:  # license ID not found in snipe_seats collection
                logger.debug('error, license {} not found in database.'
                             .format(item))
                continue
            for seat in lic_item:
                asset = self.snipe_hw.find_one({'Location': seat['location'],
                                                'Hostname': seat['asset_name']})
                if asset:
                    # if there is a record of a an asset associated with this
                    # license, append the asset info to list
                    self.asset_list_sw.append(asset)
                    found_assets_ct += 1
                else:
                    # if an asset has been deleted the asset info will be in
                    # the deleted collection in the 'inventory' mongodb if
                    # there is a case where the asset was deleted but the seat
                    # is still checked out, this will return the asset info
                    if seat['asset_name']:
                        del_asset = self.deleted.find_one(
                            {'_snipeit_hostname_8': seat['asset_name']})
                        if del_asset:
                            deleted_assets_ct += 1
                            asset = {'ID': del_asset['id'],
                                     'Asset Tag': del_asset['asset_tag'],
                                     'IP': del_asset['_snipeit_ip_6'],
                                     'Mac Address': del_asset['_snipeit_mac_address_7'],
                                     'Location': del_asset['Location'],
                                     'Hostname': del_asset['_snipeit_hostname_8']}
                            self.asset_list_sw.append(asset)
                        else:
                            not_found_assets_ct += 1
                            logger.debug('error, there is a seat associated to'
                                         'an asset not found. Review lic {} seat {}'
                                         .format(item, seat['id']))
                            continue
                    else:
                        continue
        # only found assets and deleted assets associated with a seat will be
        # returned. This message is for review.
        logger.debug('License {}'.format(item))
        logger.debug('Assets found {}'.format(found_assets_ct))
        if not_found_assets_ct > 0:
            logger.debug('Assets not found {}'.format(not_found_assets_ct))
        if deleted_assets_ct > 0:
            logger.debug('Assets deleted {}'.format(deleted_assets_ct))

