from odoo import models, fields


class LogCodeRuntime(models.Model):
    _name = "log.code.runtime"
    _description = "Log Code Runtime"

    vit_code_type = fields.Char(string='Code Type')
    vit_start_sync = fields.Datetime(string='Start Sync')
    vit_end_sync = fields.Datetime(string='End Sync')
    vit_duration = fields.Char(string='Duration')
