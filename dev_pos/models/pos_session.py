import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class PosSession(models.Model):
    _inherit = 'pos.session'

    is_updated = fields.Boolean(string="Updated", default=False, readonly=True, tracking=True)
    name_session_pos = fields.Char(string="Name Session POS (Odoo Store)", tracking=True)

    def write_sessions(self):
        update_session = self.env['pos.session'].search([])
        for rec in update_session:
            rec.write({
                'state': 'opened'
            })