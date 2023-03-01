from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from datetime import date
from pprint import pformat
import pymongo
import requests
from update_dbs import config as cfg
# from update_dbs import snipe_lic_update as lic_db_upd

# get today's date
today = date.today()
today_date = today.strftime('%m-%d-%Y')

logger = getLogger('licenses')
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


class Licenses:

    client = pymongo.MongoClient("mongodb://localhost:27017/")
    software_db = client['software_inventory']
    # current licenses from bigfix
    lic_w_ct_col = software_db['licenses_w_count']
    # curent licenses from bigfix (license name & hostname)
    licenses_col = software_db['licenses_info']
    # current license collection from snipe-it
    snipe_lic_col = software_db['snipe_lic']
    # current snipeIT collection of license seats
    snipe_seat_col = software_db['snipe_seat']
    # curernt snipeIT computer information
    snipe_hw_col = software_db['snipe_hw']
    # current bigfix computer information
    computer_info_col = software_db['computer_info']

    def __init__(self):
        # current licenses to compare
        self.bigfix_licenses = tuple
        self.snipe_licenses = tuple
        self.lic_arguments = ()
        # new licenses from get_licenses_new.
        # New seats found go to seats_add
        self.new_licenses = []
        # licenses to delete. Seats to delete go to seats_rem
        self.del_licenses = []
        # licenses that need to be updated. Update seats go to
        # seats_add and seats_rem
        self.upd_licenses = []
        # check-in and check-out seats
        self.seats_add = []
        self.seats_rem = []

    def get_license_lists(self, args=None):
        ''' Gets license lists from licenses_w_count (BigFix)
            and from snipe_lic (snipe_it)
            and adds them to two lists
            if there are license arguments, get only those'''
        # make sure mongodb has the right lic information from snipe
        # upd = lic_db_upd.SnipeSoftware()
        # upd.get_licenses()
        # upd.update_licenses()
        # bigfix
        lic_args_list = []
        if args:
            # only get list of licenses in arguments to update
            for lic in args:
                lic_name = self.lic_w_ct_col.find_one({'sw': lic})
                lic_args_list.append(lic_name)

        lic_list = self.lic_w_ct_col.find()
        lic_list = list(lic_list)
        # snipe
        snipe_lic = self.snipe_lic_col.find()
        snipe_lic = list(snipe_lic)

        # create list of all license names in snipe-it
        snipe_lic = [item['License Name'] for item in snipe_lic]
        self.snipe_licenses = tuple(snipe_lic)

        # create tuple of all license names in bigfix
        self.bigfix_licenses = tuple(lic_list)
        # create tuple of license arguments if any
        if lic_args_list:
            self.lic_arguments = tuple(lic_args_list)

    def get_licenses_new(self, args=None):
        '''gets total list of unique licenses if not already in snipeIT'''
        if args:
            for item in args:
                if item['sw'] in self.bigfix_licenses and \
                        item['sw'] not in self.snipe_licenses:
                    # if license is not found, create a new license
                    logger.debug('Found new license {} '
                                 .format(item['sw']))
                    self.new_licenses.append(item)
            return
        # for each of the bigfix licenses
        for item in self.bigfix_licenses:
            # adding 100 extra seats to prevent future errors
            # check if the license is in snipeIT
            if item['sw'] not in self.snipe_licenses:
                # if license is not found, create a new license
                logger.debug('Found new license {} '
                             .format(item['sw']))
                self.new_licenses.append(item)

    def get_lic_seats_new(self, new_license):
        '''Gets seat information for new licenses'''
        # in order to get seat information a license needs to be created first
        # then get the license id from the POST response in 'create_license()
        # this information should already be mongo by the time this method
        # is called, but make sure you are aware of
        license_id = self.snipe_lic_col.find_one({'License Name': new_license},
                                                 {'_id': 0,
                                                 'License ID': 1})
        bigfix_assets = self.licenses_col.find({'sw': new_license},
                                               {'_id': 0,
                                                'comp_name': 1,
                                                'sw': 1})
        bigfix_assets = list(bigfix_assets)
        for asset in bigfix_assets:
            mac_addr = self.computer_info_col.find_one(
                {'comp_name': asset['comp_name']},
                {'_id': 0,
                 'mac_addr': 1})
            asset_info = self.snipe_hw_col.find_one(
                {'Hostname': asset['comp_name'],
                 'Mac Address': mac_addr['mac_addr']},
                {'_id': 0,
                 'ID': 1,
                 'Location': 1,
                 'Asset Tag': 1})
            seat = {'license_id': license_id['License ID'],
                    'assigned_asset': asset_info['ID'],
                    'location': asset_info['Location'],
                    'asset_name': asset['comp_name'],
                    'asset_tag': asset_info['Asset Tag'],
                    'license_name': new_license}
            self.seats_add.append(seat)

    def get_licenses_update(self, args=None):
        '''gets licenses that have different seat amounts to update in snipeIT'''
        upd_licenses = [item for item in self.bigfix_licenses]
        if args:
            upd_licenses = []
            for item in args:
                if item['sw'] in self.bigfix_licenses:
                    upd_licenses.append(item)
        for item in upd_licenses:
            license = self.snipe_lic_col.find_one({'License Name': item['sw']},
                                                  {'_id': 0,
                                                   'License Name': 1,
                                                   'License ID': 1,
                                                   'Total Seats': 1,
                                                   'Free Seats': 1})
            # get licenses that had any changes in seat numbers from last run
            # to find seats to update for those licenses only
            if (int(item['count']) == int(license['Total Seats'])):
                continue
            else:
                # if the seat amount is not right, update
                logger.debug('Found changes for license {}.\n'
                             'Updating seat amount from {} to {}'
                             .format(item['sw'],
                                     license['Total Seats'],
                                     item['count']))
                self.upd_licenses.append(item)

    def get_lic_seats_add(self, license_name):
        '''Gets seat information for licenses that need to be checked-out'''
        assets_not_found = []
        assets_not_anywhere = []
        lic_id = self.snipe_lic_col.find_one({'License Name': license_name['sw']},
                                             {'_id': 0,
                                              'License ID': 1})
        lic_id = lic_id['License ID']
        logger.debug('____________________CHECK-OUT_______________________')
        logger.debug(license_name['sw'].upper())
        # get all computers associated with this license
        # from bigfix
        bigfix_assets = self.licenses_col.find({'sw': license_name['sw']},
                                               {'_id': 0,
                                                'comp_name': 1,
                                                'sw': 1})
        bigfix_assets = list(bigfix_assets)
        # for each computer that has this license
        # check if there is a seat already in snipeIT
        # if not, a new seat needs to be added
        asset_count = 0
        for asset in bigfix_assets:
            seat = {'license_id': lic_id,
                    'assigned_asset': None,
                    'location': None,
                    'asset_name': asset['comp_name'],
                    'asset_tag': None,
                    'license_name': license_name['sw']}
            # check if the seat already exists in snipeIT
            snipe_seat = self.snipe_seat_col.find_one(
                {'license_id': lic_id,
                 'asset_name': asset['comp_name']})
            # if a seat is already checked out, move on to the nex asset
            if snipe_seat:
                continue
            # some of the seats have different hostnames,
            # in bigfix I think it is right, snipeIT has hostnames
            # that are old I believe.
            # find the mac address from the computer_info_col (bigfix)
            comp_info = self.computer_info_col.find_one(
                {'comp_name': asset['comp_name']},
                {'_id': 0,
                 'mac_addr': 1,
                 'IP': 1})
            if comp_info:
                snipe_asset = self.snipe_hw_col.find_one(
                    {'Mac Address': comp_info['mac_addr']},
                    {'_id': 0,
                     'ID': 1,
                     'Location': 1,
                     'Asset Tag': 1,
                     'IP': 1})
                if not snipe_asset:
                    asset = {'name': asset['comp_name'],
                             'IP': comp_info['IP'],
                             'mac_addr': comp_info['mac_addr']}
                    assets_not_found.append(asset)
                    continue
                # try to find the seat again with the mac address
                snipe_seat = self.snipe_seat_col.find_one(
                    {'license_id': lic_id,
                     'assigned_asset': snipe_asset['ID']})
                if snipe_seat:
                    continue
            else:
                # assets not found in SnipeIT with a hostname,
                # and cannot get a mac_address from bigfix to look it up that
                # way, so it is assets not found anywhere
                assets_not_anywhere.append(asset['comp_name'])
                continue
            # IF SEAT IS NOT FOUND, CREATE SEAT
            # if there is no seat checked out, get all info
            # necessary to create a seat
            # get computer info from snipe_hw
            asset_info = self.snipe_hw_col.find_one(
                {'Hostname': asset['comp_name']},
                {'_id': 0,
                 'ID': 1,
                 'Location': 1,
                 'Asset Tag': 1,
                 'IP': 1,
                 'Mac Address': 1})
            if asset_info:
                seat['location'] = asset_info['Location']
                seat['asset_tag'] = asset_info['Asset Tag']
                seat['assigned_asset'] = asset_info['ID']
            # if an asset was not found with the hostname in snipe_hw,
            # use the mac address
            else:
                # get mac addr from bigfix
                comp_info = self.computer_info_col.find_one(
                    {'comp_name': asset['comp_name']},
                    {'_id': 0,
                     'mac_addr': 1,
                     'IP': 1})
                if comp_info:
                    asset_info = self.snipe_hw_col.find_one(
                        {'Mac Address': comp_info['mac_addr']},
                        {'_id': 0,
                         'ID': 1,
                         'Location': 1,
                         'Asset Tag': 1,
                         'Hostname': 1})
                    if asset_info:
                        seat['asset_name'] = asset_info['Hostname']
                        seat['location'] = asset_info['Location']
                        seat['asset_tag'] = asset_info['Asset Tag']
                        seat['assigned_asset'] = asset_info['ID']
                    # asset not found in snipeIT, add to list to review
                    else:
                        asset = {'name': asset['comp_name'],
                                 'IP': comp_info['IP'],
                                 'mac_addr': comp_info['mac_addr']}
                        assets_not_found.append(asset)
                        continue
            # add new seat to upd_seat_add list
            if not snipe_seat:
                self.seats_add.append(seat)
                logger.debug('check-out asset: {}, asset ID {}'
                             .format(seat['asset_name'],
                                     seat['assigned_asset']))
                asset_count += 1

        total = self.lic_w_ct_col.find_one({'sw': license_name['sw']},
                                           {'_id': 0, 'count': 1})
        free = self.snipe_lic_col.find_one({'License Name': license_name['sw']},
                                           {'_id': 0, 'Free Seats': 1})
        logger.debug('Total count of assets associated with license - {}'
                     .format(int(total['count']) - int(len(assets_not_anywhere))))
        logger.debug('Assets to check out - {}'
                     .format(asset_count))
        logger.debug('Total Free Seats for license in SnipeIT - {}. '
                     'This could be outdated. Run snipe_lic_update.py'
                     .format(free['Free Seats']))
        logger.debug('Assets that cannot be found anywhere - {}'
                     .format(len(assets_not_anywhere)))
        logger.debug('Assets associated with license {}'
                     .format(len(bigfix_assets)))
        snipe_assets = self.snipe_seat_col.find(
            {'license_name': license_name['sw']},
            {'asset_name': seat['asset_name']})
        snipe_assets = list(snipe_assets)
        snipe_assets = [asset['asset_name'] for asset in snipe_assets]
        # for debugging
        # logger.debug('Assets not found in snipeIT (it checks hostnames only):')
        # logger.debug(pformat([item['comp_name'] for item in bigfix_assets
        #                      if item['comp_name'] not in snipe_assets]))
        logger.debug('Assets not found in snipeIT (checks mac_addresses '
                     'and hostnames) - {}'
                     .format(len(assets_not_found)))
        logger.debug(pformat([asset['name'] for asset in assets_not_found]))

    def get_lic_seats_rem(self, license_name):
        '''Gets seats that need to be checked-in'''
        logger.debug('____________________CHECK-IN_______________________')
        logger.debug(license_name['sw'].upper())
        lic_id = self.snipe_lic_col.find_one({'License Name': license_name['sw']},
                                             {'_id': 0,
                                              'License ID': 1})
        lic_id = lic_id['License ID']
        # only get seats that have an assigned asset ID
        snipe_seats = self.snipe_seat_col.find(
            {'license_id': lic_id,
             'assigned_asset': {'$ne': None}})
        snipe_seats = list(snipe_seats)
        #  for each seat already in snipe, check if it still
        # supposed to be checked out, or if it should be removed
        asset_ct = 0
        # get computer names from bigfix
        comp_names = self.licenses_col.find(
            {'sw': license_name['sw']},
            {'_id': 0,
             'comp_name': 1})
        comp_names = list(comp_names)
        comp_names = [item['comp_name'] for item in comp_names]
        
        bigfix_macs = self.computer_info_col.find({})
        bigfix_macs = list(bigfix_macs)
        bigfix_macs = [item['mac_addr'] for item in bigfix_macs]

        for seat in snipe_seats:
            if seat['asset_name'] not in comp_names:
                mac_addr_snipe = self.snipe_hw_col.find_one(
                    {'ID': seat['assigned_asset']},
                    {'_id': 0, 'Mac Address': 1})
                if not mac_addr_snipe:
                    continue
                # if mac_addr not in list of mac_addresses with this license
                # from bigfix, add to the remove list
                if mac_addr_snipe['Mac Address'] not in bigfix_macs:
                    self.seats_rem.append(seat)
                    logger.debug('check-in asset: {}, asset ID {}'
                                 .format(seat['asset_name'],
                                         seat['assigned_asset']))
                    asset_ct += 1

        total = self.lic_w_ct_col.find_one({'sw': license_name['sw']},
                                           {'_id': 0, 'count': 1})
        free = self.snipe_lic_col.find_one({'License Name': license_name['sw']},
                                           {'_id': 0, 'Free Seats': 1})
        logger.debug('Total count of assets for license - {}'
                     .format(total['count']))
        logger.debug('Total Free Seats for license in SnipeIT - {}.\n'
                     'This could be outdated. Run snipe_lic_update.py'
                     .format(free['Free Seats']))
        logger.debug('Assets to check in - {}'
                     .format(asset_ct))
        # logger.debug('Asset list for license:')
        # logger.debug(pformat([item['comp_name'] for item in bigfix_assets[:10]]))

    def get_licenses_delete(self, args=None):
        '''gets licenses that no longer are active in bigfix to remove from
            snipeIT'''
        # get list of license names
        bigfix_licenses = [item['sw'] for item in self.bigfix_licenses]
        if args:
            for item in args:
                if item['sw'] in self.snipe_licenses and \
                        item['sw'] not in bigfix_licenses:
                    # if license is not found, create a new license
                    logger.debug('Found removed license {} '
                                 .format(item))
                    self.del_licenses.append(item)
            return
        for item in self.snipe_licenses:
            if item not in bigfix_licenses:
                # if license is not found, create a new license
                logger.debug('Found removed license {} '
                             .format(item))
                self.del_licenses.append(item)

    def get_lic_seats_del(self, del_license):
        # get seats to check in
        del_seats = self.snipe_seat_col.find(
            {'license_name': del_license,
                'assigned_asset': {'$ne': None}})
        del_seats = list(del_seats)
        for seat in del_seats:
            self.seats_rem.append(seat)

    def create_license(self, new_license):
        '''If new licenses found update SnipeIT and databases'''
        seat_amt = int(new_license['count'])
        lic_name = new_license['sw']
        item_dict = str({'name': lic_name,
                         'seats': seat_amt,
                         'category_id': '11'})  # category for API (software)
        logger.debug('Adding new license {} with {} seats'
                     .format(lic_name, seat_amt))
        # url for snipe-it licenses
        url = cfg.api_url_soft_all
        payload = item_dict.replace('\'', '\"')
        response = requests.request("POST",
                                    url=url,
                                    data=payload,
                                    headers=cfg.api_headers)
        logger.debug(pformat(response.text))
        content = response.json()
        logger.debug(pformat(content))
        status = str(content['status'])
        if status == 'success':
            lic_info = self.snipe_lic_col.insert_one(
                {'License Name': lic_name,
                 'Total Seats': seat_amt,
                 'Free Seats': seat_amt,
                 'License ID': content['payload']['id'],
                 'Date': today_date})
            if lic_info is False:
                logger.debug('error, Could not add License {} '
                             'with {} seats to MongoDB'
                             .format(lic_name, seat_amt))
        else:
            logger.debug('error, Could not add License {} to SnipeIT'
                         .format(lic_name))

    def update_license(self, upd_license):
        '''If existing licenses have wrong amount of license seats update
        SnipeIT and databases'''
        license = self.snipe_lic_col.find_one({'License Name': upd_license['sw']},
                                              {'_id': 0,
                                               'License Name': 1,
                                               'License ID': 1,
                                               'Total Seats': 1})
        seat_amt = int(upd_license['count'])
        lic_name = upd_license['sw']
        if seat_amt == license['Total Seats']:
            return
        logger.debug('Updating license {} with {} seats'
                     .format(lic_name, seat_amt))
        url = cfg.api_url_software_lic.format(license['License ID'])
        item_str = str({'seats': seat_amt})
        payload = item_str.replace('\'', '\"')
        response = requests.request("PATCH",
                                    url=url,
                                    data=payload,
                                    headers=cfg.api_headers)
        # logger.debug(pformat(response.text))
        content = response.json()
        # logger.debug(pformat(content))
        status = str(content['status'])
        if status == 'success':
            lic_info = self.snipe_lic_col.update_one(
                {'License ID': license['License ID']},
                {'$set': {'Total Seats': seat_amt}})
            if lic_info is False:
                logger.debug('error, Could not update License {} '
                             'with {} seats to MongoDB'
                             .format(lic_name, seat_amt))
        else:
            logger.debug('Could not update license {} '
                         'with the right seat amount in SnipeIT'
                         .format(upd_license['sw']))

    def delete_license(self, del_license):
        ''' delete removed licenses from snipeIT and databases'''
        license = self.snipe_lic_col.find_one({'License Name': del_license},
                                              {'_id': 0,
                                               'License ID': 1,
                                               'License Name': 1,
                                               'Free Seats': 1,
                                               'Total Seats': 1})
        # find if license has seats checked out
        # if none checked out, delete license
        if license['Total Seats'] == license['Free Seats']:
            logger.debug('Deleting license {}'
                         .format(del_license))
            url = cfg.api_url_software_lic.format(license['License ID'])
            response = requests.request("DELETE",
                                        url=url,
                                        headers=cfg.api_headers)
            # logger.debug(pformat(response.text))
            status_code = response.status_code
            if status_code == 200:
                content = response.json()
                status = str(content['status'])
                if status == 'success':
                    logger.debug('Removed license {} from snipe-it'
                                 .format(license['License ID']))
                    # remove license from mongodb,
                    # returns true if deletion success
                    delete_lic = self.snipe_lic_col.delete_one(
                        {'License ID': license['License ID']})
                    delete_lic_seats = self.snipe_seat_col.delete_many(
                        {'license_id': license['License ID']})
                    if delete_lic is False:
                        logger.debug('error, could not delete License {} '
                                     'from MongoDB'
                                     .format(license['License ID']))
                    if delete_lic_seats is False:
                        logger.debug('error, could not delete License {} '
                                     'seats from MongoDB'
                                     .format(license['License ID']))
                else:
                    logger.debug('Could not delete license {} '
                                 'from SnipeIT'
                                 .format(license['License ID']))


if __name__ == '__main__':
    try:
        pass
    except(KeyError, pymongo.errors.PyMongoError):
        logger.critical('create_lic exception', exc_info=True)
