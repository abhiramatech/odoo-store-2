# -*- coding: utf-8 -*-
from odoo import fields, models


class HREmployeeInherit(models.Model):
    _inherit = 'hr.employee'
    
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)