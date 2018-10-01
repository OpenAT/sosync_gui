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

        cr = self.env.cr

        # Create index if missing: "get_first_open_jobs_v2_idx"
        # -----------------------------------------------------
        _logger.info("Create/Check pgsql index 'get_first_open_jobs_v2_idx'")
        cr.execute('SELECT indexname FROM pg_indexes '
                   'WHERE indexname = \'get_first_open_jobs_v2_idx\';')
        if not cr.fetchone():
            cr.execute('CREATE INDEX get_first_open_jobs_v2_idx '
                       'ON sosync_job USING btree '
                       '(job_priority DESC, job_date DESC, job_state COLLATE pg_catalog."default", parent_job_id) '
                       'WHERE job_state = \'new\'::text AND parent_job_id IS NULL;')

        # # Create index if missing: "protocol_idx"
        # -----------------------------------------
        # # No longer needed because no sync of jobs to FS-Online anymore
        # cr.execute('SELECT indexname FROM pg_indexes '
        #            'WHERE indexname = \'protocol_idx\';')
        # if not cr.fetchone():
        #     cr.execute('CREATE INDEX protocol_idx '
        #                'ON sosync_job USING btree '
        #                '(write_date DESC, job_to_fso_can_sync, job_to_fso_sync_version) '
        #                'WHERE job_to_fso_can_sync = true '
        #                'AND (job_to_fso_sync_version IS NULL '
        #                'OR job_to_fso_sync_version < write_date '
        #                'OR job_to_fso_sync_version > write_date);')

        # Create index if missing: "skip_jobs_idx"
        # ----------------------------------------
        _logger.info("Create/Check pgsql index 'skip_jobs_idx'")
        cr.execute('SELECT indexname FROM pg_indexes '
                   'WHERE indexname = \'skip_jobs_idx\';')
        if not cr.fetchone():
            cr.execute('CREATE INDEX skip_jobs_idx '
                       'ON sosync_job USING btree '
                       '(job_source_sosync_write_date, job_source_system COLLATE pg_catalog."default", '
                       'job_source_model COLLATE pg_catalog."default", job_source_record_id, '
                       'job_state COLLATE pg_catalog."default") '
                       'WHERE job_state = \'new\'::text;')

        return res

    # ======
    # FIELDS
    # ======

    # SYNCJOB SOURCE INFO
    # -------------------
    job_date = fields.Datetime(string="Job Create Date", readonly=True,
                               help="Creation Date of the Job in the Job Source System")
    job_fetched = fields.Datetime(string="Fetched at", readonly=True) # identical with create_date ?
    job_priority = fields.Integer(string="Priority", default=1000, help="Higher numbers will be processed first")
    job_source_system = fields.Selection(selection=_systems, string="System", readonly=True, index=True)
    job_source_model = fields.Char(string="Model", readonly=True, index=True)
    job_source_record_id = fields.Integer(string="Record ID", readonly=True)
    job_source_target_record_id = fields.Integer(string="Target Rec. ID", readonly=True,
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
                                       readonly=True, default=False,
                                       index=True)
    job_source_type_info = fields.Char(string='Syncflow Indi.', readonly=True,
                                       help="Indicator for repair sync flows (to group by later on) "
                                            "e.g.: 'donation_deduction_disabled_repair' This should NOT be used for"
                                            "long descriptions!")

    job_source_merge_into_record_id = fields.Integer(string="MergeInto ID", readonly=True)
    job_source_target_merge_into_record_id = fields.Integer(string="MergeInto Trg. ID",
                                                            readonly=True)

    # SYNCJOB PROCESSING INFO
    # -----------------------
    job_start = fields.Datetime(string="Started at", readonly=True)
    job_end = fields.Datetime(string="Finished at", readonly=True)
    job_duration = fields.Integer(compute='_compute_job_duration', store=True,
                                  string="Duration (ms)",  readonly=True)
    job_run_count = fields.Integer(string="Run Count", readonly=True,
                                   help="Restarts triggered by changed source data in between job processing")

    job_closed_by_job_id = fields.Many2one(comodel_name="sosync.job",
                                           string="Closed by Job", readonly=True)
    job_closed_jobs_ids = fields.One2many(comodel_name="sosync.job", inverse_name="job_closed_by_job_id",
                                          string="Closed Jobs", readonly=True)
    job_log = fields.Text(string="Log", readonly=True)
    job_state = fields.Selection(selection=[("new", "New"),
                                            ("inprogress", "In Progress"),
                                            ("child", "ChildJob Processing"),
                                            ("done", "Done"),
                                            ("error", "Error"),
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
    parent_job_id = fields.Many2one(comodel_name="sosync.job",
                                    string="Parent Job", readonly=True, index=True)
    child_job_ids = fields.One2many(comodel_name="sosync.job", inverse_name="parent_job_id",
                                    string="Child Jobs", readonly=True)
    parent_path = fields.Char("Path", readonly=True, help="Find ancestors and siblings of job")
    child_job_start = fields.Datetime(string="CJ Started at", readonly=True)
    child_job_end = fields.Datetime(string="CJ Finished at", readonly=True)
    child_job_duration = fields.Integer(compute="_compute_child_job_duration", store=True,
                                        string="CJ Duration (ms)", readonly=True)

    # COMPUTED SOURCE
    # ---------------
    sync_source_system = fields.Selection(selection=_systems, string="Source System", readonly=True)
    sync_source_model = fields.Char(string="Source Model", readonly=True)
    sync_source_record_id = fields.Integer(string="Source Record ID", readonly=True)
    sync_source_merge_into_record_id = fields.Integer(string="Source Merge-Into Record ID", readonly=True)

    # COMPUTED TARGET
    # ---------------
    sync_target_system = fields.Selection(selection=_systems, string="Target System", readonly=True)
    sync_target_model = fields.Char(string="Target Model", readonly=True)
    sync_target_record_id = fields.Integer(string="Target Record ID", readonly=True)
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
    sync_duration = fields.Integer(compute="_compute_sync_duration", store=True,
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

