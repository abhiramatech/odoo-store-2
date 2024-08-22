import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class PoSPaymentMethodInherit(models.Model):
    _inherit = 'pos.payment.method'

    is_integrated = fields.Boolean(string="Integrated", default=False)
    is_updated = fields.Boolean(string="Updated", default=False)
    is_store = fields.Many2one('setting.config', string="Send Store")
    vit_trxid = fields.Char(string="Transaction ID", default=False)