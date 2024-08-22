import requests
from datetime import datetime, timedelta
import pytz
from odoo.http import request
import base64
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    is_integrated = fields.Boolean(string="Integrated", default=False)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)