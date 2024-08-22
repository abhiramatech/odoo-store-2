# -*- coding: utf-8 -*-
from odoo import fields, models


class LoyaltyRuleInherit(models.Model):
    _inherit = 'loyalty.rule'

    vit_trxid = fields.Char(string="Transaction ID", default=False)
