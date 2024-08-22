from odoo import models, fields, api
from datetime import datetime, timedelta
from pytz import timezone

class PosCashierLog(models.Model):
    _name = 'pos.cashier.log'
    _description = 'POS Cashier Log'

    employee_id = fields.Many2one('hr.employee', string='Cashier', required=True)
    timestamp = fields.Datetime(string='Timestamp', required=True, default=lambda self: self._default_jakarta_time())
    session_id = fields.Many2one('pos.session', string='POS Session', required=True)
    state = fields.Selection([
        ('opened', 'Opened'),
        ('closed', 'Closed')
    ], string='Status', default='opened', required=True)

    @api.model
    def _default_jakarta_time(self):
        jakarta_tz = timezone('Asia/Jakarta')
        return datetime.now(jakarta_tz).replace(tzinfo=None)

    def action_close(self):
        for record in self:
            record.state = 'closed'

    @api.model
    def create(self, vals):
        if 'timestamp' in vals:
            # Convert the incoming timestamp to Jakarta time
            timestamp = fields.Datetime.from_string(vals['timestamp'])
            jakarta_tz = timezone('Asia/Jakarta')
            jakarta_timestamp = jakarta_tz.localize(timestamp).replace(tzinfo=None)
            vals['timestamp'] = fields.Datetime.to_string(jakarta_timestamp)
        return super(PosCashierLog, self).create(vals)

    def write(self, vals):
        if 'timestamp' in vals:
            # Convert the incoming timestamp to Jakarta time
            timestamp = fields.Datetime.from_string(vals['timestamp'])
            jakarta_tz = timezone('Asia/Jakarta')
            jakarta_timestamp = jakarta_tz.localize(timestamp).replace(tzinfo=None)
            vals['timestamp'] = fields.Datetime.to_string(jakarta_timestamp)
        return super(PosCashierLog, self).write(vals)