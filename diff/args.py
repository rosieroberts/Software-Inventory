from argparse import ArgumentParser
from logging import FileHandler, Formatter, StreamHandler, getLogger, DEBUG
from datetime import date
import sys

# get today's date
today = date.today()
today_date = today.strftime('%m-%d-%Y')

# pass test_list in inv_args if wanting to use for testing
test_list = ['CMPC893', 'EEPC893-1', 'EEPC893-2', 'FMPC893', 'club963', '960C-9125', '954C-37F1']

logger = getLogger('inventory')
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

def inv_args():
    list_iter = []

    parser = ArgumentParser(description='Software Inventory Script')
    parser.add_argument(
        '-club', '-c',
        nargs='*',
        help='Club Number in "club000" format')
    parser.add_argument(
        '-assetTag', '-a',
        nargs='*',
        help='Asset tag of the computer to get list of software')
    parser.add_argument(
        '-hostname', '-n',
        nargs='*',
        help='Hostname of the computer to get list of software')
    parser.add_argument(
        '-license', '-l',
        nargs='*',
        help='License ID of the license to update, limit 10 licenses.')
    inv_args = parser.parse_args()

    try:

        if inv_args.club:
            club_rgx = compile(r'((club)[\d]{3})')
            for item in inv_args.club:
                club_ = club_rgx.search(item)
                if club_:
                    club_ = str(club_.group(0))
                    if len(item) == len(club_):
                        arg = {'argument': club_,
                               'func_type': 'asset'}
                        list_iter.append(arg)
                    else:
                        logger.warning('{} is not in the right format, try again'.format(item))
                        continue
                else:
                    logger.warning('{} is not in the right format, try again'.format(item))
                    continue

        if inv_args.assetTag:
            asset_tag_rgx = compile(r'([0-9]{3}[A-Z]{1}-[A-Za-z0-9]{4})')
            for item in inv_args.assetTag:
                asset_tag = asset_tag_rgx.search(item)
                if asset_tag:
                    asset_tag = str(asset_tag.group(0))
                    if len(item) == len(asset_tag):
                        arg = {'argument': asset_tag,
                               'func_type': 'asset'}
                        list_iter.append(arg)
                    else:
                        logger.warning('{} is not in the right format, try again'.format(item))
                        continue
                else:
                    logger.warning('{} is not in the right format, try again'.format(item))
                    continue

        if inv_args.hostname:
            hostname_rgx = compile(r'[A-Z]{1,3}[PC]{1}\d{3}(-[\d]{1,2})*')
            if len(inv_args.hostname) > 10:
                logger.warning('error, entered more than 10 license arguments, try again')
                sys.exit()
            for item in inv_args.hostname:
                hostname = hostname_rgx.search(item)
                if hostname:
                    hostname = str(hostname.group(0))
                    if len(item) == len(hostname):
                        arg = {'argument': hostname,
                               'func_type': 'asset'}
                        list_iter.append(arg)
                    else:
                        logger.warning('{} is not in the right format, try again'.format(item))
                        continue
                else:
                    logger.warning('{} is not in the right format, try again'.format(item))
                    continue

        if inv_args.license:
            # as of now licenseIDs are not more than 3 digits, after a while licenseIDs will probably increase
            # to 4 digits, if so, change the regex to r'([\d]{1,4})' and the len to 4 or less
            license_rgx = compile(r'([\d]{1,3})')
            for count, item in enumerate(inv_args.license):
                # limit arguments to 10, otherwise upd_dbs.upd_seats() will not work properly
                if len(item) <= 3 and count < 10:
                    license = license_rgx.search(item)
                    if license:
                        license = str(license.group(0))
                        if len(item) == len(license):
                            arg = {'argument': license,
                                   'func_type': 'license'}
                            list_iter.append(arg)
                        else:
                            logger.warning('{} is not in the right format, try again'.format(item))
                            continue
                    else:
                        logger.warning('{} is not in the right format, try again'.format(item))
                        continue
                else:
                    if count >= 10:
                        logger.warning('Too many license arguments, try again')
                    else:
                        logger.warning('{} license ID has too many digits, try again'.format(item))
                    continue

        if not inv_args.club and not inv_args.assetTag and not inv_args.hostname and not inv_args.license:
            return None
        else:
            if len(list_iter) > 0:
                return list_iter
            else:
                logger.warning('error, the argument is not in the right format, exiting')
                sys.exit()

    except(OSError, AttributeError):
        logger.critical('There was a problem getting all assets, try again', exc_info=True)
        return None