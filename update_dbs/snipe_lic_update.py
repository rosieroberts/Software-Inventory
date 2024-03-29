import pymongo
import requests
import sys
from argparse import ArgumentParser
from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from json import decoder
from datetime import date, datetime
from re import compile
from time import sleep
from update_dbs import config as cfg
#import config as cfg

# Logger setup
logger = getLogger('update_snipe_licenses')
# TODO: set to ERROR later on after setup
logger.setLevel(DEBUG)

file_formatter = Formatter('{asctime} {name} {levelname}: {message}', style='{')
stream_formatter = Formatter('{message}', style='{')
today = date.today()
today_date = today.strftime('%Y-%m-%d')

# logfile
file_handler = FileHandler('/opt/Software_Inventory/logs/update_dbs-{}.log'
                           .format(today.strftime('%m%d%Y')))
file_handler.setLevel(DEBUG)
file_handler.setFormatter(file_formatter)

# console
stream_handler = StreamHandler()
stream_handler.setFormatter(stream_formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def main(args=None):
    test = SnipeSoftware()
    if test.get_software_count() == 0:
        sys.exit()
    # get licenses added to mongo
    test.get_licenses()
    test.update_licenses()
    if args:
        test.update_one_lic(args)
    else:
        # get seats added to mongo
        test.get_seats()
        test.update_seats()


class SnipeSoftware:
    '''Class for updating snipe-it software Licenses in mongoDB'''

    def __init__(self):
        self.total_record_count = int
        self.license_info = []
        self.seat_info = []
        self.mongo_license_ids = []
        self.snipe_license_ids = []

    asset_tag_rgx = compile(r'([0-9]{3}[A-Z]{1}-[A-Za-z0-9]{4})')
    url = cfg.api_url_soft_all

    myclient = pymongo.MongoClient("mongodb://localhost:27017/")
    # use database named "software_inventory"
    soft_db = myclient['software_inventory']
    # use collection named "snipe_lic"
    snipe_lic = soft_db['snipe_lic']
    # use collection for seats
    snipe_seat_col = soft_db['snipe_seat']

    # use database named "inventory"
    hard_db = myclient['inventory']
    # use collection for hardware
    hardware_col = hard_db['snipe']
    # use collection for deleted hardware
    deleted_hw_col = hard_db['deleted']

    def get_software_count(self):
        try:
            # get count of licenses in snipeIT
            response = requests.request("GET",
                                        url=self.url,
                                        headers=cfg.api_headers)
            content = response.json()
            self.total_record_count = content['total']
            # no licenses in snipeIT
            if self.total_record_count == 0:
                logger.debug('No License data in Snipe-IT')

        except(KeyError, decoder.JSONDecodeError):
            logger.exception('error getting license count from snipe-it')

    def get_licenses(self):
        # get license information from snipe-it
        try:
            # for every 500 records in total license records
            for offset in range(0, self.total_record_count, 500):
                querystring = {"offset": offset}
                response = requests.request("GET",
                                            url=self.url,
                                            headers=cfg.api_headers,
                                            params=querystring)
                content = response.json()
                for item in content['rows']:
                    # get all license information and add it to a dictionary
                    snipe_upd_date = datetime.strptime(item['updated_at']['datetime'],
                                                       '%Y-%m-%d %H:%M:%S')
                    license = {'License ID': item['id'],
                               'License Name': item['name'],
                               'Total Seats': item['seats'],
                               'Free Seats': item['free_seats_count'],
                               'Date': today_date,
                               'Snipe Upd Date': snipe_upd_date.strftime('%Y-%m-%d')}
                    self.license_info.append(license)
        except(KeyError, decoder.JSONDecodeError):
            logger.exception('error getting license information from snipe-it')

    def update_licenses(self):
        # adds license information from snipe-it to mongoDB
        try:
            if len(self.license_info) > 0:
                lic_del = self.snipe_lic.delete_many({})
            if lic_del:
                lic_add = self.snipe_lic.insert_many(self.license_info)
            if lic_add:
                logger.debug('added license information to mongoDB')
        except(pymongo.errors.PyMongoError):
            logger.exception('error adding snipe license information to mongoDB')

    def get_seats(self, args=None):
        # get license seat information (it is slow due to API pagination)
        try:
            count = 0
            if args:
                for license_id in args:
                    license = [lic for lic in self.license_info
                               if lic['License ID'] == license_id]
                license_info = [license]
            else:
                license_info = self.license_info

            for license in license_info:
                seat_count = 0
                url = cfg.api_url_soft_all_seats.format(license['License ID'])
                # for every 50 seats in total seats per license
                for offset2 in range(0, license['Total Seats'], 50):
                    querystring = {'offset': offset2}
                    # get seat information from snipe-it and add to mongodb
                    response = requests.request("GET",
                                                url=url,
                                                headers=cfg.api_headers,
                                                params=querystring)
                    content = response.json()
                    status_code = response.status_code
                    # sleep if number of requests is 120 to prevent errors
                    count += 1
                    if count == 118:
                        sleep(65)
                        count = 0
                    if status_code != 200:
                        logger.debug(count)
                        logger.debug('error, too many requests '
                                     'trying again')
                        sleep(65)
                        response = requests.request("GET",
                                                    url=url,
                                                    headers=cfg.api_headers,
                                                    params=querystring)
                        content = response.json()
                    for row in content['rows']:
                        if row['assigned_asset'] is None:
                            assigned_asset = None
                            location = None
                            hostname = None
                            assigned_asset_name = None
                        else:
                            assigned_asset = row['assigned_asset']['id']
                            assigned_asset_name = row['assigned_asset']['name']
                            asset_name = self.asset_tag_rgx.search(assigned_asset_name)
                            if asset_name:
                                asset_name = str(asset_name.group(0))
                                assigned_asset_name = asset_name
                            location = row['location']['name']
                            asset = self.hardware_col.find_one({'ID': assigned_asset},
                                                               {'Hostname': 1,
                                                                '_id': 0})
                            if asset:
                                # if asset is found in active snipe db
                                hostname = asset['Hostname']
                            else:
                                # else look in the deleted assets db
                                asset = self.deleted_hw_col.find_one({'id': assigned_asset},
                                                                     {'_snipeit_hostname_8': 1,
                                                                      '_id': 0})
                                if asset:
                                    hostname = asset['_snipeit_hostname_8']
                                else:
                                    hostname = 'Not Found'

                        seat = {'id': row['id'],
                                'license_id': row['license_id'],
                                'assigned_asset': assigned_asset,
                                'location': location,
                                'seat_name': row['name'],
                                'asset_name': hostname,
                                'asset_tag': assigned_asset_name,
                                'license_name': license['License Name'],
                                'date': today_date}
                        self.seat_info.append(seat)
                        seat_count += 1
                # logger.info('{} seats found for license {} in SnipeIT'
                #            .format(seat_count, license['License ID']))

        except(KeyError,
               decoder.JSONDecodeError):
            # if error is KeyError: 'rows' - the problem is too many requests
            # 118 requests at a time with 61 seconds of sleep seems to do the trick
            logger.exception('error, problem getting seats information for MongoDB')

    def update_seats(self):
        try:
            self.snipe_seat_col.delete_many({})
            # mongoDB adds no more than 1000 records at a time
            for seat in range(0, len(self.seat_info), 1000):
                self.snipe_seat_col.insert_many(self.seat_info[seat:seat + 1000])
            logger.info('Added all license seats to mongoDB')

        except(pymongo.errors.PyMongoError):
            logger.exception('error adding license seat information to mongoDB')

    def update_one_lic(self, args):
        # only update one license if passed in args.
        # repeating most of the code from prior lines, but it gets
        # confusing otherwise. This *can* be done in the future.
        try:
            count = 0
            for license_id in args:
                license = [lic for lic in self.license_info
                           if lic['License ID'] == license_id]
                seat_count = 0
                url = cfg.api_url_soft_all_seats.format(license['License ID'])
                # for every 50 seats in total seats per license
                for offset2 in range(0, license['Total Seats'], 50):
                    querystring = {'offset': offset2}
                    # get seat information from snipe-it and add to mongodb
                    response = requests.request("GET",
                                                url=url,
                                                headers=cfg.api_headers,
                                                params=querystring)
                    content = response.json()
                    status_code = response.status_code
                    # sleep if number of requests is 120 to prevent errors
                    count += 1
                    if count == 118:
                        sleep(65)
                        count = 0
                    if status_code != 200:
                        logger.debug(count)
                        logger.debug('error, too many requests '
                                     'trying again')
                        sleep(65)
                        response = requests.request("GET",
                                                    url=url,
                                                    headers=cfg.api_headers,
                                                    params=querystring)
                        content = response.json()
                    for row in content['rows']:
                        if row['assigned_asset'] is None:
                            assigned_asset = None
                            location = None
                            hostname = None
                            assigned_asset_name = None
                        else:
                            assigned_asset = row['assigned_asset']['id']
                            assigned_asset_name = row['assigned_asset']['name']
                            asset_name = self.asset_tag_rgx.search(assigned_asset_name)
                            if asset_name:
                                asset_name = str(asset_name.group(0))
                                assigned_asset_name = asset_name
                            location = row['location']['name']
                            asset = self.hardware_col.find_one({'ID': assigned_asset},
                                                               {'Hostname': 1,
                                                                '_id': 0})
                            if asset:
                                # if asset is found in active snipe db
                                hostname = asset['Hostname']
                            else:
                                # else look in the deleted assets db
                                asset = self.deleted_hw_col.find_one({'id': assigned_asset},
                                                                     {'_snipeit_hostname_8': 1,
                                                                      '_id': 0})
                                if asset:
                                    hostname = asset['_snipeit_hostname_8']
                                else:
                                    hostname = 'Not Found'

                        seat = {'id': row['id'],
                                'license_id': row['license_id'],
                                'assigned_asset': assigned_asset,
                                'location': location,
                                'seat_name': row['name'],
                                'asset_name': hostname,
                                'asset_tag': assigned_asset_name,
                                'license_name': license['License Name'],
                                'date': today_date}
                        self.seat_info.append(seat)
                        seat_count += 1
                logger.info('{} seats found for license {} in SnipeIT'
                            .format(seat_count, license_id))
                try:
                    self.snipe_seat_col.delete_many({'license_id': license_id})
                    # mongoDB adds no more than 1000 records at a time
                    for seat in range(0, len(self.seat_info), 1000):
                        self.snipe_seat_col.insert_many(self.seat_info[seat:seat + 1000])
                    logger.info('Added all license seats for license {} to mongoDB'
                                .format(license_id))

                except(pymongo.errors.PyMongoError):
                    logger.exception('error adding license seat information to mongoDB')
        except(KeyError,
               decoder.JSONDecodeError):
            # if error is KeyError: 'rows' - the problem is too many requests
            # 118 requests at a time with 61 seconds of sleep seems to do the trick
            logger.exception('error, problem getting seats information for MongoDB')


class Args():

    def __init__(self) -> None:
        self.arguments = []

    def args(self):
        parser = ArgumentParser(description='snipe_lic_update')
        parser.add_argument(
            '-license', '-l',
            nargs='*',
            help='License ID of the license to update snipeIT DB.')
        args = parser.parse_args()
        try:
            format_msg = '{} is not in the right format, try again'
            if args.license:
                # as of now licenseIDs are not more than 3 digits,
                # after a while licenseIDs will probably increase
                # to 4 digits, if so, change the regex to r'([\d]{1,4})'
                # and the len to 4 or less
                license_rgx = compile(r'([\d]{1,3})')
                for count, item in enumerate(Args.args.license):
                    if len(item) <= 3:
                        license = license_rgx.search(item)
                        if license:
                            license = str(license.group(0))
                            if len(item) == len(license):
                                arg = {'argument': license,
                                       'func_type': 'license'}
                                self.arguments.append(arg)
                            else:
                                logger.warning(format_msg.format(item))
                                continue
                        else:
                            logger.warning(format_msg.format(item))
                            continue
                    else:
                        logger.warning('{} license ID has too many digits,'
                                       'try again'.format(item))
                        continue
        except(OSError, AttributeError):
            logger.critical('There was a problem, try again',
                            exc_info=True)
            return None


if __name__ == '__main__':
    args_obj = Args()
    args_obj.args()
    args = args_obj.arguments
    main(args)
