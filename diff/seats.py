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

logger = getLogger('Seats')
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


class Seats():
    '''Class to check in or check out seats based on weekly
    changes in license_info DB'''
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    software_db = client['software_inventory']
    # snipe Seats collection
    snipe_seat_col = software_db['snipe_seat']
    # snipe lic collection
    snipe_lic_col = software_db['snipe_lic']
    # snipe hw collection (computers only col in software_inventory db)
    snipe_hw_col = software_db['snipe_hw']

    def check_in(self, seats):
        # method for checking seats in
        if len(seats) == 0:
            print('NO SEATS TO CHECK IN')
        ct = 0
        for seat in seats:
            # for each seat checked out to asset
            license_id = seat['license_id']
            seat_id = seat['id']
            asset_id = seat['assigned_asset']
            logger.debug('CHECKING IN - license {}, seat {}, asset {}'
                         .format(license_id, seat_id, asset_id))
            # to prevent API errors
            if ct == 118:
                sleep(61)
                ct = 0
            url = cfg.api_url_software_seat.format(license_id, seat_id)
            item_str = str({'asset_id': ''})
            payload = item_str.replace('\'', '\"')
            response = requests.request("PATCH",
                                        url=url,
                                        data=payload,
                                        headers=cfg.api_headers)
            status_code = response.status_code
            ct += 1
            content = response.json()
            if status_code != 200:
                message = str(content['messages'])
                if message == 'Too many requests':
                    logger.debug(message)
                else:
                    logger.debug('error, there was something wrong removing '
                                 'seat to license {} to asset {}'
                                 .format(license_id,
                                         asset_id))
                    logger.debug(pformat(response.text))
                continue
            status = str(content['status'])
            if status != 'success':
                message = str(content['messages'])
                if message == 'Seat not found':
                    logger.debug('error, asset {} is not currently active, '
                                 'cannot update license. Asset needs to be '
                                 'restored in SnipeIT first.'
                                 .format(asset_id))
                else:
                    logger.debug('error, license {} removal not successful '
                                 'for asset {}'
                                 .format(license_id, asset_id))
                    logger.debug(pformat(response.text))
                continue
            # updating seat in Mongo snipe_seat collection
            seat_upd = self.snipe_seat_col.update_one(
                {'license_id': license_id,
                 'id': seat_id},
                {'$set': {'assigned_asset': None,
                          'asset_name': None,
                          'location': None,
                          'asset_tag': None,
                          'date': today_date}})
            if seat_upd is False:
                logger.debug('error, could not update snipe_seat collection '
                             'for license {} and asset {}'
                             .format(license_id, asset_id))
            free_seats = self.snipe_lic_col.find_one(
                {'License ID': license_id}, {'_id': 0, 'Free Seats': 1})
            # updating license in Mongo snipe_lic collection
            lic_upd = self.snipe_lic_col.update_one(
                {'License ID': license_id},
                {'$set':
                    {'Free Seats': int(free_seats['Free Seats']) + 1}})
            if lic_upd is False:
                logger.debug('error, could not update snipe_lic collection '
                             'for license {}'
                             .format(license_id))

    def check_out(self, seats):
        # method for checking seats out
        if len(seats) == 0:
            print('NO SEATS TO CHECK OUT')
        ct = 0
        for seat in seats:
            # get asset information
            asset_info = self.snipe_hw_col.find_one(
                {'ID': seat['assigned_asset']})
            # find an unassigned seat to check out asset
            empty_seat = self.snipe_seat_col.find_one(
                {'assigned_asset': None,
                 'license_id': seat['license_id']},
                {'id': 1,
                 'assigned_asset': 1,
                 'name': 1,
                 'location': 1,
                 '_id': 0})
            if not empty_seat:
                logger.debug('error, there are no empty seats left. '
                             'check license {}'
                             .format(seat['license_id']))
                return
            license_id = seat['license_id']
            seat_id = empty_seat['id']
            asset_id = seat['assigned_asset']
            logger.debug('CHECKING OUT - license {}, seat {}, asset {}'
                         .format(license_id, seat_id, asset_id))
            # to prevent API errors
            if ct == 118:
                sleep(61)
                ct = 0
            url = cfg.api_url_software_seat.format(license_id, seat_id)
            item_str = str({'asset_id': asset_id})
            payload = item_str.replace('\'', '\"')
            response = requests.request("PATCH",
                                        url=url,
                                        data=payload,
                                        headers=cfg.api_headers)
            status_code = response.status_code
            content = response.json()
            ct += 1
            if status_code != 200:
                message = str(content['messages'])
                if message == 'Too many requests':
                    logger.debug(message)
                else:
                    logger.debug('error, there was something wrong adding seat '
                                 'for license {} to asset {}'
                                 .format(license_id,
                                         asset_id))
                    logger.debug(pformat(response.text))
                continue
            status = str(content['status'])
            if status != 'success':
                message = str(content['messages'])
                if message == 'Seat not found':
                    logger.debug('error, asset {} is not currently active, '
                                 'cannot update license. Asset needs to be '
                                 'restored in SnipeIT first.'
                                 .format(asset_id))
                else:
                    logger.debug('error, license {} check-out not successful '
                                 'for asset {}'
                                 .format(license_id, asset_id))
                    logger.debug(pformat(response.text))
                continue
            # updating seat in Mongo snipe_seat collection
            seat_upd = self.snipe_seat_col.update_one(
                {'license_id': license_id,
                 'id': seat_id},
                {'$set': {'assigned_asset': asset_id,
                          'asset_name': asset_info['Hostname'],
                          'location': asset_info['Location'],
                          'asset_tag': asset_info['Asset Tag']}})
            if seat_upd is False:
                logger.debug('error, could not update snipe_seat collection '
                             'for license {} and asset {}'
                             .format(license_id, asset_id))
            free_seats = self.snipe_lic_col.find_one(
                {'License ID': license_id}, {'_id': 0, 'Free Seats': 1})
            # updating license in Mongo snipe_lic collection
            lic_upd = self.snipe_lic_col.update_one(
                {'License ID': license_id},
                {'$set':
                    {'Free Seats': int(free_seats['Free Seats']) - 1}})
            if lic_upd is False:
                logger.debug('error, could not update snipe_lic collection '
                             'for license {}'
                             .format(license_id))
