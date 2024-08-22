import requests
from datetime import datetime, timedelta
import pytz
from odoo.http import request
import random
import base64
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError

class PurchaseOrderIntegration(models.Model):
    _inherit = 'purchase.order'

    vit_trxid = fields.Char(string='Transaction ID')
    is_integrated = fields.Boolean(string="Integrated", default=False)

    def create_purchase_orders(self):
        partner_id = 7
        picking_type_id = 1

        product_codes = ['LBR00001', 'LBR00002', 'LBR00003', 'LBR00088', 'LBR00099', 'LBR00008', 'LBR00007', 'LBR00006', 'LBR00009', 'LBR00004']

        # Get product IDs
        product_ids = self.env['product.product'].search([('default_code', 'in', product_codes)])

        # Create 100 purchase orders
        for i in range(500):
            order_date = datetime.now() - timedelta(days=random.randint(0, 30))
            order_lines = []

            # Create 3-5 order lines for each purchase order
            for _ in range(random.randint(3, 5)):
                product = random.choice(product_ids)
                order_lines.append((0, 0, {
                    'product_id': product.id,
                    'name': product.name,
                    'product_qty': random.randint(1, 10),
                    'price_unit': product.list_price + 5000,
                }))

            # Create the purchase order
            purchase_order = self.env['purchase.order'].create({
                'partner_id': partner_id,
                'picking_type_id': picking_type_id,
                'date_order': order_date,
                'order_line': order_lines,
            })

            # Confirm the purchase order
            purchase_order.button_confirm()

            print(f"Created and confirmed Purchase Order {purchase_order.name}")

        print("Finished creating 100 purchase orders")