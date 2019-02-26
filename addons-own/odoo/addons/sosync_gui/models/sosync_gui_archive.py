# -*- coding: utf-'8' "-*-"
from odoo import api, models, fields
from odoo.tools import config

from contextlib import closing

import logging
_logger = logging.getLogger(__name__)


class SosyncJobArchive(models.Model):
    _name = 'sosync.job_archive'
    _inherit = 'sosync.job'

    # HINT: init() is called after _auto_init() and therefore the tables and db schema is already created
    @api.model
    def init(self):
        res = super(SosyncJobArchive, self).init()

        archive_table_space_name = config['archive_table_space_name']
        archive_table_space_path = config['archive_table_space_path']

        # Create archive tablespace if missing
        # ------------------------------------
        # HINT: This is done with a new cursor since we have to change the isolation level to 0
        with closing(self.pool.cursor()) as cr:
            _logger.info("Create/Check tablespace %s at path %s" % (archive_table_space_name, archive_table_space_path))
            cr.execute("SELECT * FROM pg_tablespace WHERE spcname='"+archive_table_space_name+"';")
            if not cr.fetchone():
                # Set the isolation level to 0 for CREATE TABLESPACE
                cr.autocommit(True)
                # Create the Tablespace
                cr.execute("CREATE TABLESPACE "+archive_table_space_name+" "
                           "OWNER SESSION_USER "
                           "LOCATION '"+archive_table_space_path+"';")

        # Move model table to archive tablespace if not already there
        # -----------------------------------------------------------
        # HINT: This is done with the current env cursor because new tables from the addon already exits there when
        #       init() is called!
        cr = self.env.cr
        model_table_name = self._name.replace('.', '_')
        _logger.info("Create/Check that table %s is in tablespace %s"
                     % (model_table_name, archive_table_space_name))

        # Check if the table exits already
        cr.execute("SELECT * FROM pg_tables WHERE tablename='"+model_table_name+"';")
        if cr.fetchone():
            _logger.info("Table %s was found in the database!" % model_table_name)

            # Check if the table is in the correct tablespace
            cr.execute("SELECT * FROM pg_tables WHERE tablename='" + model_table_name + "' AND tablespace='" + archive_table_space_name + "';")
            if not cr.fetchone():
                _logger.info("Moving table %s to tablespace %s" % (model_table_name, archive_table_space_name))
                # Move the model table to the new tablespace
                cr.execute("ALTER TABLE "+model_table_name+" "
                           "SET TABLESPACE "+archive_table_space_name+";")

        return res
    
    # ------
    # FIELDS
    # ------
    # ATTENTION: OVERRIDE FIELD DEFINTIONS FOR MANY2ONE IF THEY POINT TO THE INHERITED MODLE
    #            OR THE WRONG MODEL (TABLES) WILL BE USED!!!
    parent_job_id = fields.Many2one(comodel_name="sosync.job_archive",
                                    string="Parent Job", readonly=True, index=True, ondelete='set null')
    child_job_ids = fields.One2many(comodel_name="sosync.job_archive", inverse_name="parent_job_id",
                                    string="Child Jobs", readonly=True)
    
    job_closed_by_job_id = fields.Many2one(comodel_name="sosync.job_archive",
                                           string="Closed by Job", readonly=True, index=True, ondelete='set null')
    job_closed_jobs_ids = fields.One2many(comodel_name="sosync.job_archive", inverse_name="job_closed_by_job_id",
                                          string="Closed Jobs", readonly=True)

