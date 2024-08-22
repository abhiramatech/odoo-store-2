import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)