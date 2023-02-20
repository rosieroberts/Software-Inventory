import pymongo
import requests
import sys
from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from json import decoder
from datetime import date, datetime
from re import compile
from time import sleep
from config import updateConfig as cfg

# Logger setup
logger = getLogger('update_snipe_licenses')
# TODO: set to ERROR later on after setup
logger.setLevel(DEBUG)

file_formatter = Formatter('{asctime} {name} {levelname}: {message}', style='{')
stream_formatter = Formatter('{message}', style='{')
today = date.today()
today_date = today.strftime('%Y-%m-%d')

# logfile
file_handler = FileHandler('/opt/Software_Inventory/logs/software_inventory-ref{}.log'
                           .format(today.strftime('%m%d%Y')))
file_handler.setLevel(DEBUG)
file_handler.setFormatter(file_formatter)

# console
stream_handler = StreamHandler()
stream_handler.setFormatter(stream_formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def main():
    test = SnipeSoftware()
    if test.get_software_count() == 0:
        sys.exit()
    # get licenses added to mongo
    test.get_licenses()
    test.update_licenses()
    # get seats added to mongo
    test.get_seats()
    test.update_seats()


class SnipeSoftware:
    '''Class for updating snipe-it software Licenses in mongoDB'''

    total_record_count = int
    license_info = []
    seat_info = []
    mongo_license_ids = []
    snipe_license_ids = []
    asset_tag_rgx = compile(r'([0-9]{3}[A-Z]{1}-[A-Za-z0-9]{4})')
    url = cfg.api_url_soft_all

    myclient = pymongo.MongoClient("mongodb://localhost:27017/")
    # use database named "software_inventory"
    soft_db = myclient['software_inventory']
    # use collection named "snipe_lic"
    snipe_lic = soft_db['snipe_lic']

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
                self.snipe_lic.delete_many({})
            if self.snipe_lic.count() == 0:
                self.snipe_lic.insert_many(self.license_info)
            if self.snipe_lic.count() > 0:
                logger.debug('added license information to mongoDB')
        except(pymongo.errors.PyMongoError):
            logger.exception('error adding snipe license information to mongoDB')

    def get_seats(self):
        # get license seat information (it is slow due to API pagination)
        try:
            count = 0
            for license in self.license_info:
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
                    # sleep if number of requests is 90 to prevent errors
                    count += 1
                    if count == 120:
                        sleep(60)
                        count = 0
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
                        logger.info('Got info for seat {} license {} from SnipeIT'
                                    .format(seat['id'], seat['license_id']))
        except(KeyError,
               decoder.JSONDecodeError):
            logger.exception('Problem adding License seats information to MongoDB')

    def update_seats(self):
        try:
            self.snipe_seat_col.delete_many({})
            # mongoDB adds no more than 1000 records at a time
            for seat in range(0, len(self.seat_info), 1000):
                self.snipe_seat_col.insert_many(self.seat_info[seat:seat + 1000])
                logger.info('Added seat {} for license {} to MongoDB '
                            .format(seat['id'], seat['license_id']))

            logger.info('Added all license seats to mongoDB')

        except(pymongo.errors.PyMongoError):
            logger.exception('error adding license seat information to mongoDB')


if __name__ == '__main__':
    main()
