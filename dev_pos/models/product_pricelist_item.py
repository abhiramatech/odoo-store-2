import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    is_updated = fields.Boolean(string="Updated", default=False, readonly=True, tracking=True)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)