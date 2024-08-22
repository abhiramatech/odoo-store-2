import requests
from datetime import datetime, timedelta
import pytz
from odoo.http import request
import base64
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class MasterStockType(models.Model):
    _name = 'master.type'
    _rec_name = 'type_code'

    type_name = fields.Char(string="Name", tracking=True)
    type_code = fields.Char(string="Code", tracking=True)