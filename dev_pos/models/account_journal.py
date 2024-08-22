import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class AccountJournal(models.Model):
    _inherit = 'account.journal'
    
    vit_trxid = fields.Char(string="Transaction ID", default=False)
    is_store = fields.Many2one('setting.config', string="Send Store")