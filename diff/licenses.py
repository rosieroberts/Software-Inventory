from time import sleep
from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from datetime import date
from pprint import pformat
import pymongo
import requests
from update_dbs import config as cfg

# get today's date
today = date.today()
today_date = today.strftime('%m-%d-%Y')

logger = getLogger('create_license')
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

    def __init__(self):
        self.bigfix_licenses = []
        self.snipe_licenses = []
        self.new_licenses = []
        self.upd_licenses = []
        self.del_licenses = []

    def get_license_lists(self, args=None):
        ''' Gets license lists from licenses_w_count (BigFix)
            and from snipe_lic (snipe_it)
            and adds them to two lists
            if there are license arguments, get only those'''
        # bigfix
        if args is not None:
            # only get list of licenses in arguments to update
            lic_list = []
            for lic in args:
                lic_name = self.lic_w_ct_col.find_one({'sw': lic})
                lic_list.append(lic_name)
        else:
            # else update all licenses
            lic_list = self.lic_w_ct_col.find()
            lic_list = list(lic_list)
        # snipe
        snipe_lic = self.snipe_lic_col.find()
        snipe_lic = list(snipe_lic)

        # create list of all license names in snipe-it
        for item in snipe_lic:
            self.snipe_licenses.append(item['License Name'])

        # create list of all license names in bigfix
        for item in lic_list:
            self.bigfix_licenses.append(item)

    def get_licenses_create(self):
        '''gets total list of unique licenses if not already in snipeIT'''
        # for each of the bigfix licenses
        for item in self.bigfix_licenses:
            # adding 100 extra seats to prevent future errors
            # check if the license is in snipeIT
            if item['sw'] not in self.snipe_licenses:
                # if license is not found, create a new license
                logger.debug('Found new license {} '
                             .format(item['sw']))
                self.new_licenses.append(item)

    def get_licenses_update(self):
        '''gets licenses that have different seat amounts to update in snipeIT'''
        for item in self.bigfix_licenses:
            license = self.snipe_lic_col.find_one({'License Name': item['sw']},
                                                  {'_id': 0,
                                                   'License Name': 1,
                                                   'License ID': 1,
                                                   'Total Seats': 1})
            # check if license has more than 50 empty seats
            # or no more than 100
            if (int(item['count']) + 100 >= int(license['Total Seats']) and
                    int(license['Total Seats']) >= int(item['count']) + 50):
                continue
            else:
                # if the seat amount is not right, update
                logger.debug('Found changes for license {}.\n'
                             'Updating seat amount from {} to {}'
                             .format(item['sw'],
                                     license['Total Seats'],
                                     item['count']))
                self.upd_licenses.append(item)

    def get_licenses_delete(self):
        '''gets licenses that no longer are active in bigfix to remove from
            snipeIT'''
        # get list of license names
        bigfix_licenses = [item['sw'] for item in self.bigfix_licenses]
        for item in self.snipe_licenses:
            if item not in bigfix_licenses:
                # if license is not found, create a new license
                logger.debug('Found removed license {} '
                             .format(item))
                self.del_licenses.append(item)

    def create_license(self):
        '''If new licenses found update SnipeIT and databases'''
        ct = 0
        for item in self.new_licenses:
            # add sleep to prevent API errors
            if ct == 118:
                sleep(60)
                ct = 0
            # adding 100 extra seats to prevent future errors
            seat_amt = int(item['count']) + 100
            lic_name = item['sw']
            item_dict = str({'name': lic_name,
                             'seats': seat_amt,
                             'category_id': '11'})  # category for API (software)
            logger.debug(item_dict)
            logger.debug('Adding new license {} with {} seats'
                         .format(lic_name, seat_amt))
            # url for snipe-it licenses
            url = cfg.api_url_soft_all
            payload = item_dict.replace('\'', '\"')
            response = requests.request("POST",
                                        url=url,
                                        data=payload,
                                        headers=cfg.api_headers)
            ct += 1
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
                print(lic_info)
                if lic_info is False:
                    logger.debug('error, Could not add License {} '
                                 'with {} seats to MongoDB'
                                 .format(lic_name, seat_amt))
            else:
                logger.debug('error, Could not add License {} to SnipeIT'
                             .format(lic_name))

    def update_license(self):
        '''If existing licenses have wrong amount of license seats update
        SnipeIT and databases'''
        ct = 0
        for item in self.upd_licenses:
            # add sleep to prevent API errors
            if ct == 118:
                sleep(60)
                ct = 0
            license = self.snipe_lic_col.find_one({'License Name': item['sw']},
                                                  {'_id': 0,
                                                   'License Name': 1,
                                                   'License ID': 1,
                                                   'Total Seats': 1})
            seat_amt = int(item['count']) + 100
            lic_name = item['sw']
            logger.debug('Updating license {} with {} seats'
                         .format(lic_name, seat_amt))
            url = cfg.api_url_software_lic.format(license['License ID'])
            item_str = str({'seats': seat_amt})
            payload = item_str.replace('\'', '\"')
            print(item['count'], payload)
            response = requests.request("PATCH",
                                        url=url,
                                        data=payload,
                                        headers=cfg.api_headers)
            ct += 1
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
                             .format(item['sw']))

    def delete_license(self):
        ''' delete removed licenses from snipeIT and databases'''
        if len(self.del_licenses) == 0:
            return None
        ct = 0
        for item in self.del_licenses:
            license = self.snipe_lic_col.find_one({'License Name': item},
                                                  {'_id': 0,
                                                   'License ID': 1,
                                                   'License Name': 1,
                                                   'Free Seats': 1,
                                                   'Total Seats': 1})
            # find if license has seats checked out
            # if none checked out, delete license
            if license['Total Seats'] == license['Free Seats']:
                logger.debug('Deleting license {}'
                             .format(item))
                url = cfg.api_url_software_lic.format(license['License ID'])
                if ct == 118:
                    sleep(60)
                    ct = 0
                response = requests.request("DELETE",
                                            url=url,
                                            headers=cfg.api_headers)
                logger.debug(pformat(response.text))
                status_code = response.status_code
                ct += 1
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
