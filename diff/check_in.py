import pymongo

def check_in(snipe_list):
        # check in seats for each asset in list of snipe assets
        # use this when deleting an item from snipe it.
        # might add this to the inventory script

        id_list = []

        if snipe_list is None:
            return None

        for item in snipe_list:
            # get asset ids for each asset and append to id_list
            asset_id = item['ID']
            id_list.append(asset_id)

        client = pymongo.MongoClient("mongodb://localhost:27017/")
        software_db = client['software_inventory']
        # asset_db = client['inventory']

        # Snipe Seats collection
        snipe_seats = software_db['snipe_seat']

        # deleted assets collection
        # deleted = asset_db['deleted']

        for id_ in id_list:
            # for each asset in list
            seats = snipe_seats.find({'assigned_asset': id_},
                                     {'id': 1, 'license_id': 1, '_id': 0})

            seats = list(seats)
            logger.debug('check in seats {}'.format(seats))
            for seat in seats:
                # for each seat checked out to asset
                license_id = seat['license_id']
                seat_id = seat['id']
                print(license_id, seat_id)

                # license ID and seat id
                url = cfg.api_url_software_seat.format(license_id, seat_id)

                item_str = str({'asset_id': ''})
                payload = item_str.replace('\'', '\"')
                response = requests.request("PATCH",
                                            url=url,
                                            data=payload,
                                            headers=cfg.api_headers)
                logger.debug(pformat(response.text))
