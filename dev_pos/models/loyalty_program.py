# -*- coding: utf-8 -*-
from odoo import fields, models, api


class LoyaltyProgramInherit(models.Model):
    _inherit = 'loyalty.program'

    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    is_updated = fields.Boolean(string="Updated", default=False, readonly=True, tracking=True)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)
    vit_trxid = fields.Char(string="Transaction ID", default=False)

    def write(self, vals):
        # Only set is_updated to True if it hasn't been explicitly set to False in vals
        if 'is_updated' not in vals:
            vals['is_updated'] = True
            
        return super(LoyaltyProgramInherit, self).write(vals)

    def create_loyalty_programs(self):
        for i in range(100):  # Loop untuk membuat 100 data
            # Hard-coded values
            currency_target_id = 12  # Ganti dengan ID mata uang yang sesuai
            target_pricelist_ids = [(6, 0, [1])]  # Ganti dengan ID pricelist yang sesuai
            target_pos_config_ids = [(6, 0, [1])]  # Ganti dengan ID pos config yang sesuai
            reward_target_product_ids = [1]  # Ganti dengan ID produk yang sesuai
            reward_target_category_id = 1  # Ganti dengan ID kategori produk yang sesuai
            rule_target_product_ids = [1]  # Ganti dengan ID produk yang sesuai
            rule_target_category_id = 1  # Ganti dengan ID kategori produk yang sesuai

            # Data untuk loyalty program
            discount_data = {
                'name': f'Loyalty Program {i + 1}',
                'program_type': 'promotion',  # Ganti dengan tipe program yang sesuai
                'currency_id': currency_target_id,
                'portal_visible': True,  # Ganti dengan trigger yang sesuai
                'applies_on': 'current',  # Ganti dengan applies_on yang sesuai
                'date_from': '2023-01-01',  # Ganti dengan tanggal yang sesuai
                'date_to': '2023-12-31',  # Ganti dengan tanggal yang sesuai
                'vit_trxid': f'vit_trxid_{i + 1}',
                'pricelist_ids': target_pricelist_ids,
                'pos_ok': True,
                'sale_ok': True,
                'pos_config_ids': target_pos_config_ids,
                'reward_ids': [],
                'rule_ids': [],
            }

            # Data untuk reward_ids
            discount_loyalty_line_ids = []
            for j in range(3):  # Misalnya, 3 reward per program
                discount_line_data = {
                    'reward_type': 'discount',  # Ganti dengan tipe reward yang sesuai
                    'discount': 10.0,  # Ganti dengan nilai diskon yang sesuai
                    'discount_applicability': 'specific',  # Ganti dengan aplikasi diskon yang sesuai
                    'discount_max_amount': 100000,
                    'discount_product_ids': [(6, 0, reward_target_product_ids)],
                    'discount_product_category_id': reward_target_category_id,
                    'vit_trxid': f'vit_trxid_{i + 1}',
                }
                discount_loyalty_line_ids.append((0, 0, discount_line_data))

            discount_data['reward_ids'] = discount_loyalty_line_ids

            # Data untuk rule_ids
            rule_ids = []
            for k in range(2):  # Misalnya, 2 rule per program
                rule_data = {
                    'minimum_qty': 3,  # Ganti dengan jumlah minimum yang sesuai
                    'minimum_amount': 50000,  
                    'product_ids': rule_target_product_ids,
                    'product_category_id': rule_target_category_id,
                    'vit_trxid': f'vit_trxid_{i + 1}',
                }
                rule_ids.append((0, 0, rule_data))

            discount_data['rule_ids'] = rule_ids

            # Membuat loyalty program menggunakan ORM
            self.env['loyalty.program'].create(discount_data)
            print(f'Loyalty Program {i + 1} telah dibuat.')