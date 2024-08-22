import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class AccountTax(models.Model):
    _inherit = 'account.tax'

    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)