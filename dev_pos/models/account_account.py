import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class AccountAccount(models.Model):
    _inherit = 'account.account'

    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    is_store = fields.Many2one('setting.config', string="Send Store")