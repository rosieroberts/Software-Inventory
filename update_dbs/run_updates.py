# updating all databases for software inventory
# !/usr/bin/env python3

import hardware_update
import license_update
import snipe_hw_update
import snipe_lic_update


def run():
    hardware_update.main()
    license_update.main()
    snipe_hw_update.main()
    snipe_lic_update.main()


if __name__ == '__main__':
    run()
