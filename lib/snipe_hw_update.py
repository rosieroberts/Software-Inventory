import pymongo
import requests
from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from json import decoder
from datetime import date
import config as cfg

# Logger setup
logger = getLogger('update_snipe_hardware')
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
    test = SnipeHardware()
    test.get_hardware()
    test.updateMongoDB()


class SnipeHardware:
    '''Class for updating snipe-it hardware in mongoDB
        Returns all current information for each host.
        this function returns SNIPE-IT's current device information,
        this device information will be used to have a snapshot of
        the devices already in snipe-it.
        This function deletes the prior contents of the snipe_hw collection
        and it populates it again with the new information'''

    all_hardware = []

    def get_hardware(self):
        try:
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
                        self.all_hardware.append(device)
                    else:
                        continue
        except(KeyError, decoder.JSONDecodeError):
            logger.exception('error getting hardware information from snipe-it')

    def updateMongoDB(self):
        try:
            # Adds all snipe-hw information to mongoDB
            myclient = pymongo.MongoClient("mongodb://localhost:27017/")

            # use database named "inventory"
            mydb = myclient['software_inventory']

            # use collection named "snipe_hw"
            snipe_hw = mydb['snipe_hw']

            # delete prior scan items
            if snipe_hw.count() > 0:
                snipe_hw.delete_many({})

            # insert list of dictionaries
            snipe_hw.insert_many(self.all_hardware)
            logger.debug('snipe-it hardware information updated in mongoDB')

        except(pymongo.errors.PyMongoError):
            logger.exception('error updating snipe-hw in mongoDB')


if __name__ == '__main__':
    main()
