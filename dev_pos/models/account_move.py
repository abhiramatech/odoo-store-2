import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    vit_trxid = fields.Char(string="Transaction ID", default=False, tracking=True)