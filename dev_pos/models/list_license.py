import uuid
import hashlib
from odoo import models, fields, api, tools
from odoo.exceptions import UserError
import re

class ListLicense(models.Model):
    _name = 'list.license'
    _description = 'List License'

    vit_cust_id = fields.Char(string='Customer ID')
    vit_total_user = fields.Char(string='Total User')
    vit_mac_address = fields.Char(string='MAC Address')
    vit_license_key = fields.Char(string='License Key')
    vit_input_license = fields.Char(string='Input License')
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)

    def action_apply_license(self):
        print("Apply License")
        

