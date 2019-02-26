# -*- coding: utf-8 -*-
{
    'name': 'sosync_gui',
    'version': '0.1',
    'summary': 'FS-Online Sosync v2 GUI',
    'sequence': 1,
    'description': """
FS-Online Sosyncer GUI
======================
Very simple gui for the sosyncer v2 sync jobs table

Adds two new config Options for odoo.conf:
------------------------------------------
# Use a cheaper hdd location for archive tables
archive_table_space_name = odoo_archive_tablespace
archive_table_space_path = /path/to/cheap/hdd/space

    """,
    'category': '',
    'website': 'https://www.datadialog.net',
    'images': [
    ],
    'depends': [
        'base_setup',
    ],
    'data': [
        'views/sosync_job.xml',
        'views/sosync_job_archive.xml',
        'security/ir.model.access.csv',
    ],
    'demo': [
    ],
    'qweb': [
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    #'post_init_hook': '_auto_install_l10n',
}
