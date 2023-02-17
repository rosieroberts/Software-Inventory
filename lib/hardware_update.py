#!/usr/bin/env python3

import pymongo
from json import loads, dumps
import xmltodict
from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from json import decoder
from datetime import date
from netaddr import EUI, mac_unix_expanded
import config as cfg


# Logger setup
logger = getLogger('update_hardware')
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
stream_handler.setLevel(DEBUG)
stream_handler.setFormatter(stream_formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def main():
    test = BigfixHardware()
    test.get_hardware()
    test.parse_xml()
    test.updateMongoDB()


class BigfixHardware:
    """Class for updating software current BigFix hardware information in mongoDB"""

    hardware_response = cfg.hardware()
    xml_list = []
    computer_list = []

    def get_hardware(self):
        with open('/opt/Software_Inventory/XML_files/hardware.txt', 'w') as file:
            file.write(self.hardware_response)

        file_ = open('/opt/Software_Inventory/XML_files/hardware.txt', 'rb')
        hardware_xml = dumps(xmltodict.parse(file_))
        hardware_xml = loads(hardware_xml)
        # get computer name, IP, Mac address
        self.xml_list = hardware_xml['BESAPI']['Query']['Result']['Tuple']
        logger.debug('getting updated hardware')
        print('get_hardware')

    def parse_xml(self):
        """ Parses xml file from BigFix and creates a list of dictionaries"""
        for count, line in enumerate(self.xml_list):
            try:
                # reset line
                line1 = None
                line2 = None
                line3 = None
                # if answer found add to dictionary
                line1 = self.xml_list[count]['Answer'][0]['#text']
                line2 = self.xml_list[count]['Answer'][1]['#text']
                line3 = self.xml_list[count]['Answer'][2]['#text']

                hardware_dict = {'comp_name': line1,
                                 'IP': line2,
                                 'mac_addr': self.mac_addr_format(line3),
                                 'date': today_date}

                self.computer_list.append(hardware_dict)

            # if there was a value missing, add None
            except(KeyError, decoder.JSONDecodeError):
                hardware_dict = {'comp_name': None,
                                 'IP': None,
                                 'mac_addr': None}
                if line1:
                    hardware_dict['comp_name'] = line1
                if line2:
                    hardware_dict['IP'] = line2
                if line3:
                    hardware_dict['mac_addr'] = self.mac_addr_format(line3)

                self.computer_list.append(hardware_dict)
                continue

    def updateMongoDB(self):
        """Adds all Bigfix hardware information to MongoDB
        > db.computer_info.findOne({})

        "_id" : ,
        "comp_name" : "",
        "IP" : "",
        "mac_addr" : ""
        """

        try:
            myclient = pymongo.MongoClient("mongodb://localhost:27017/")

            # use database named "inventory"
            software_db = myclient['software_inventory']

            # use collection to add computer information
            computer_info_col = software_db['computer_info']

            # delete prior scan items
            if computer_info_col.count() > 0:
                computer_info_col.delete_many({})

            # insert list of dictionaries
            computer_info_col.insert_many(self.computer_list)
            logger.debug('BigFix Computer information updated')

        except (pymongo.errors.PyMongoError):
            logger.debug('error updating computer information in mongoDB')

    def mac_addr_format(self, mac):
        """Formatted mac-address in format: XX:XX:XX:XX:XX:XX"""

        formatted_mac = EUI(str(mac))
        formatted_mac.dialect = mac_unix_expanded
        formatted_mac = (str(formatted_mac).upper())

        return formatted_mac


if __name__ == '__main__':
    main()
