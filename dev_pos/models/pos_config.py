# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfigInherit(models.Model):
    _inherit = 'pos.config'

    default_partner_id = fields.Many2one('res.partner', string="Select Customer")
    id_mc = fields.Char(string="ID MC", default=False)
    is_integrated = fields.Boolean(string="Integrated", tracking=True)
    is_updated = fields.Boolean(string="Updated", tracking=True)
    is_store = fields.Many2one('setting.config', string="Send Store")
    vit_trxid = fields.Char(string="Transaction ID", default=False)