# Software-Inventory
A script to inventory all software installed in all club computers and update Software Mongo database and SnipeIT via API.

# Install

`$ git clone https://github.com/rosieroberts/Software-Inventory.git`

# Usage:

>To run script:
>`$ python3 inventory.py`

>No arguments - default scan all locations, all software

>Optional positional arguments:
>-c, --club (club number) scans specific club/s
>`$ python3 inventory.py -c club000`
>-a, --assetTag (computer snipe asset tag) scans specific computers
>`$ python3 inventory.py -a C163-XXXX`
stname (hostname) scans specific computers
>`$ python3 inventory.py -n CMP000`
>-l, --license (software license ID) scans specific licenses
>`$ python3 inventory.py -n 000`

# Testing

Automated tests are included using the pytest framework.
`$ python3 -m pytest`

# Documentation

See DOCS.md for more detailed documentation (in work)
