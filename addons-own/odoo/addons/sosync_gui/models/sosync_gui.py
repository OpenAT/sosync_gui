# -*- coding: utf-'8' "-*-"
from odoo import api, models, fields

import logging
_logger = logging.getLogger(__name__)


class SosyncJob(models.Model):
    _name = 'sosync.job'

    # CONSTANTS
    _systems = [("fso", "FS-Online"), ("fs", "Fundraising Studio")]

    # Default order
    _order = 'write_date DESC'

    # Create indexes on install/update
    @api.model
    def _auto_init(self):
        res = super(SosyncJob, self)._auto_init()

        _logger.info('AUTO INIT')

        cr = self.env.cr

        # DROP OLD UNUSED INDEXES
        # -----------------------
        for index_to_drop in ('skip_jobs_idx', 'skip_jobs_idx_new', 'get_first_open_jobs_v2_idx',
                              'sosync_job_job_source_model_index', 'sosync_job_job_source_system_index',
                              'sosync_job_job_source_type_index', 'sosync_job_sync_source_record_id_index',
                              'sosync_job_sync_target_record_id_index'):
            cr.execute("SELECT indexname FROM pg_indexes WHERE indexname = '%s';" % index_to_drop)
            if cr.fetchone():
                _logger.info("DROP pgsql index '%s'" % index_to_drop)
                cr.execute("DROP INDEX %s;" % index_to_drop)

        # Create index if missing: "idx_skip_jobs"
        # ----------------------------------------
        _logger.info("Create/Check pgsql index 'idx_skip_jobs'")
        cr.execute('SELECT indexname FROM pg_indexes '
                   'WHERE indexname = \'idx_skip_jobs\';')
        if not cr.fetchone():
            cr.execute('CREATE INDEX idx_skip_jobs '
                       'ON sosync_job USING btree '
                       '(job_source_sosync_write_date, job_source_system COLLATE pg_catalog."default", '
                       'job_source_model COLLATE pg_catalog."default", job_source_record_id, '
                       'job_state COLLATE pg_catalog."default")'
                       'WHERE job_state in (\'new\', \'error\', \'error_retry\');')

        # Create index if missing: "idx_job_sort_order"
        # ---------------------------------------------
        _logger.info("Create/Check pgsql index 'idx_job_sort_order'")
        cr.execute('SELECT indexname FROM pg_indexes '
                   'WHERE indexname = \'idx_job_sort_order\';')
        if not cr.fetchone():
            cr.execute('CREATE INDEX idx_job_sort_order '
                       'ON sosync_job USING btree '
                       '(job_state, job_priority DESC, job_date DESC);')

        # Continue with super
        return res

    # ======
    # FIELDS
    # ======

    # SYNCJOB SOURCE INFO
    # -------------------
    job_date = fields.Datetime(string="Job Create Date", readonly=True,
                               help="Creation Date of the Job in the Job Source System")
    job_fetched = fields.Datetime(string="Fetched at", readonly=True) # identical with create_date ?
    job_priority = fields.Integer(string="Priority", default=1000, help="Higher numbers will be processed first",
                                  group_operator=False)
    job_source_system = fields.Selection(selection=_systems, string="System", readonly=True)
    job_source_model = fields.Char(string="Model", readonly=True)
    job_source_record_id = fields.Integer(string="Record ID", readonly=True, group_operator=False)
    job_source_target_record_id = fields.Integer(string="Target Rec. ID", readonly=True, group_operator=False,
                                                 help="Only filled if the target system id is already available in the "
                                                      "job source system at job creation time!")
    job_source_sosync_write_date = fields.Datetime(string="sosync_write_date", readonly=True)
    job_source_fields = fields.Text(string="Fields", readonly=True)

    # Additional info for merge and delete sync jobs
    # HINT: It would be best if this information could be retrieved from the job source system by the sync flow
    #       but for now this is the quicker next-best-alternative
    job_source_type = fields.Selection(string="Type", selection=[("delete", "Delete"),
                                                                 ("merge_into", "Merge Into"),
                                                                 ("temp", "Temporary Flow")
                                                                 ],
                                       help="Job type indicator for special sync jobs. "
                                            "If empty it is processed as a default sync job = 'create' or 'update'",
                                       readonly=True, default=False)
    job_source_type_info = fields.Char(string='Syncflow Indi.', readonly=True,
                                       help="Indicator for repair sync flows (to group by later on) "
                                            "e.g.: 'donation_deduction_disabled_repair' This should NOT be used for"
                                            "long descriptions!")

    job_source_merge_into_record_id = fields.Integer(string="MergeInto ID", readonly=True, group_operator=False)
    job_source_target_merge_into_record_id = fields.Integer(string="MergeInto Trg. ID",
                                                            readonly=True, group_operator=False)

    # SYNCJOB PROCESSING INFO
    # -----------------------
    job_start = fields.Datetime(string="Started at", readonly=True)
    job_end = fields.Datetime(string="Finished at", readonly=True)
    job_duration = fields.Integer(compute='_compute_job_duration', store=True,
                                  string="Duration (ms)",  readonly=True, group_operator=False)
    job_run_count = fields.Integer(string="Run Count", readonly=True, group_operator=False,
                                   help="Restarts triggered by changed source data in between job processing")

    # ATTENTION: May cause performance issues! THEREFORE INDEX IS MANDATORY ON MANY2ONE!
    job_closed_by_job_id = fields.Many2one(comodel_name="sosync.job",
                                           string="Closed by Job", readonly=True, index=True, ondelete='set null')
    job_closed_jobs_ids = fields.One2many(comodel_name="sosync.job", inverse_name="job_closed_by_job_id",
                                          string="Closed Jobs", readonly=True)

    job_log = fields.Text(string="Log", readonly=True)
    job_state = fields.Selection(selection=[("new", "New"),
                                            ("inprogress", "In Progress"),
                                            ("child", "ChildJob Processing"),   # Not sure if in use?!?
                                            ("done", "Done"),
                                            ("done_archived", "Done-Archived"),
                                            ("error", "Error"),
                                            ("error_retry", "Error-Retry"),
                                            ("error_archived", "Error-Archived"),
                                            ("skipped", "Skipped")],
                                 string="State", default="new", readonly=True,
                                 help="If a sync job is related to a flow listed in the instance pillar option "
                                      "'sosync_skipped_flows' the job and any related parent-job will get the state "
                                      "'skipped' from the sosyncer service")
    job_error_code = fields.Selection(selection=[("timeout", "Job timed out"),
                                                 ("run_counter", "Run count exceeded"),
                                                 ("child_job", "Child job error"),
                                                 ("sync_source", "Could not determine sync direction"),
                                                 ("transformation", "Model transformation error"),
                                                 ("cleanup", "Job finalization error"),
                                                 ("unknown", "Unexpected error")],
                                      string="Error Code", readonly=True)
    job_error_text = fields.Text(string="Error Info", readonly=True)

    # # No longer needed because no sync of jobs to FS-Online anymore
    # job_to_fso_can_sync = fields.Boolean(string="Job to FS-Online: Can Sync")
    # job_to_fso_sync_date = fields.Datetime(string="Job to FS-Online: Date")
    # job_to_fso_sync_version = fields.Datetime(string="Job to FS-Online: Version")


    # CHILD JOB INFO
    # --------------

    # ATTENTION: May cause performance issues! THEREFORE INDEX IS MANDATORY ON MANY2ONE!
    parent_job_id = fields.Many2one(comodel_name="sosync.job",
                                    string="Parent Job", readonly=True, index=True, ondelete='set null')
    child_job_ids = fields.One2many(comodel_name="sosync.job", inverse_name="parent_job_id",
                                    string="Child Jobs", readonly=True)

    parent_path = fields.Char("Path", readonly=True, help="Find ancestors and siblings of job")
    child_job_start = fields.Datetime(string="CJ Started at", readonly=True)
    child_job_end = fields.Datetime(string="CJ Finished at", readonly=True)
    child_job_duration = fields.Integer(compute="_compute_child_job_duration", store=True, group_operator=False,
                                        string="CJ Duration (ms)", readonly=True)

    # COMPUTED SOURCE
    # ---------------
    sync_source_system = fields.Selection(selection=_systems, string="Source System", readonly=True)
    sync_source_model = fields.Char(string="Source Model", readonly=True)
    sync_source_record_id = fields.Integer(string="Source Record ID", readonly=True, group_operator=False)
    sync_source_merge_into_record_id = fields.Integer(string="Source Merge-Into Record ID", readonly=True,
                                                      group_operator=False)

    # COMPUTED TARGET
    # ---------------
    sync_target_system = fields.Selection(selection=_systems, string="Target System", readonly=True)
    sync_target_model = fields.Char(string="Target Model", readonly=True)
    sync_target_record_id = fields.Integer(string="Target Record ID", readonly=True, group_operator=False)
    sync_target_merge_into_record_id = fields.Integer(string="Target Merge-Into Record ID", readonly=True)

    # SYNC INFO
    # ---------
    sync_source_data = fields.Text(string="Sync Source Data", readonly=True)
    sync_target_data_before = fields.Text(string="Sync Target Data before", readonly=True)
    sync_target_data_after = fields.Text(string="Sync Target Data after", readonly=True)
    sync_target_request = fields.Text(string="Sync Target Request(s)", readonly=True)
    sync_target_answer = fields.Text(string="Sync Target Answer(s)", readonly=True)
    sync_start = fields.Datetime(string="Sync Start", readonly=True)
    sync_end = fields.Datetime(string="Sync End", readonly=True)
    sync_duration = fields.Integer(compute="_compute_sync_duration", store=True, group_operator=False,
                                   string="Sync Duration (ms)",  readonly=True)

    # HELPER
    @staticmethod
    def _duration_in_ms(start_datetime, end_datetime):
        try:
            duration = end_datetime - start_datetime
            return int(duration.total_seconds() * 1000)
        except Exception as e:

            return False

    # COMPUTED FIELDS METHODS
    @api.depends('job_start', 'job_end')
    def _compute_job_duration(self):
        for rec in self:
            if rec.job_start and rec.job_end:
                rec.job_duration = self._duration_in_ms(rec.job_start, rec.job_end)

    @api.depends('sync_start', 'sync_end')
    def _compute_sync_duration(self):
        for rec in self:
            if rec.sync_start and rec.sync_end:
                rec.sync_duration = self._duration_in_ms(rec.sync_start, rec.sync_end)

    @api.depends('child_job_start', 'child_job_end')
    def _compute_child_job_duration(self):
        for rec in self:
            if rec.child_job_start and rec.child_job_end:
                rec.child_job_duration = self._duration_in_ms(rec.child_job_start, rec.child_job_end)

