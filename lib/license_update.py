#!/usr/bin/env python3

import pymongo
from json import loads, dumps
import xmltodict
from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from json import decoder
from datetime import date
import config as cfg


# Logger setup
logger = getLogger('update_licenses')
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
    test = BigfixSoftware()
    test.get_software()
    test.parse_xml()
    test.updateMongoDB()


class BigfixSoftware:
    '''Class for updating software licenses information from BigFix in mongoDB'''

    software_response = cfg.response
    xml_list = []
    software_list = []
    all_software = []
    licenses_w_count = []

    def get_software(self):
        with open('software.txt', 'w') as file:
            file.write(self.software_response)

        file_ = open('/opt/Software_Inventory/XML_files/software.txt', 'rb')
        software_xml = dumps(xmltodict.parse(file_))
        software_xml = loads(software_xml)
        # get software name, computer name from xml file
        self.xml_list = software_xml['BESAPI']['Query']['Result']['Tuple']
        logger.debug('getting updated software')

    def parse_xml(self):
        for count, line in enumerate(self.xml_list):
            try:
                # reset line
                line1 = None
                line2 = None
                # if answer found add to dictionary
                line1 = self.xml_list[count]['Answer'][0]['#text']
                line2 = self.xml_list[count]['Answer'][1]['#text']

                software_dict = {'comp_name': line1,
                                 'sw': line2,
                                 'date': today_date}
                self.software_list.append(software_dict)

                self.all_software.append(line2)

            # if there was a value missing, add None
            except(KeyError, decoder.JSONDecodeError):
                software_dict = {'comp_name': line1,
                                 'sw': line2,
                                 'date': today_date}
                if line1:
                    software_dict['comp_name'] = line1
                if line2:
                    software_dict['sw'] = line2
                self.software_list.append(software_dict)
                continue

    def updateMongoDB(self):
        """Adds all Bigfix license information to MongoDB
        > db.licenses_info.findOne({})

        "_id" : "),
        "comp_name" : "",
        "sw" : "",
        "date": ""
        """
        try:
            # Adds all software information to mongoDB
            myclient = pymongo.MongoClient("mongodb://localhost:27017/")

            # use database named software_inventory"
            software_db = myclient['software_inventory']

            # mongo software collection with each software count
            licenses_w_count_col = software_db['licenses_w_count']

            # collection to add software with hostnames
            licenses_info_col = software_db['licenses_info']

            if licenses_info_col.count() > 0:
                licenses_info_col.delete_many({})
            licenses_info_col.insert_many(self.software_list)

            # get amount of seats(instances) for each license(software)
            lic_w_count = {i: self.all_software.count(i) for i in self.all_software}

            for count, lic in lic_w_count.items():
                lic_dict = {'sw': lic,
                            'count': count}
                self.licenses_w_count.append(lic_dict)

            if licenses_w_count_col.count() > 0:
                licenses_w_count_col.delete_many({})
            licenses_w_count_col.insert_many(self.licenses_w_count)

            logger.debug('License information updated in mongoDB')

        except(pymongo.errors.PyMongoError):
            logger.exception('error updating software in mongoDB')


if __name__ == '__main__':
    main()
