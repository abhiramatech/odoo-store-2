import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID, _
from odoo.exceptions import UserError
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

class POSIntegration(models.Model):
    _inherit = 'pos.order'

    vit_trxid = fields.Char(string='Transaction ID', tracking=True)
    vit_id = fields.Char(string='Document ID', tracking=True)
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)

    def generate_pos_order_invoice(self):
        return self._generate_pos_order_invoice()

    def create_order_picking(self):
        self.ensure_one()  # Menjamin hanya satu record yang diproses
        
        if self.company_id.anglo_saxon_accounting and self.session_id.update_stock_at_closing and self.session_id.state != 'closed':
            return self._create_order_picking()
        else:
            return False

    # @api.model
    # def process_pos_orders_to_invoice(self):
    #     # Mengambil rekaman berdasarkan kondisi yang ditentukan
    #     pos_orders = self.search([
    #         ('is_integrated', '=', True),
    #         ('to_invoice', '=', True),
    #         ('state', '=', 'paid')
    #     ], limit=100)

    #     # Proses dalam batch per 100
    #     batch_size = 100
    #     for i in range(0, len(pos_orders), batch_size):
    #         batch = pos_orders[i:i + batch_size]

    #         try:
    #             # Memanggil fungsi _generate_pos_order_invoice untuk setiap batch
    #             batch._generate_pos_order_invoice()
    #         except Exception as e:
    #             raise UserError(f"Error processing batch: {str(e)}")

    #     return True

    # @api.model
    # def action_generate_invoice(self, order_ids):
    #     # Ensure we are working with the correct record set
    #     orders = self.browse(order_ids)  # Use browse to get records from IDs

    #     if not orders:
    #         print("No orders found for the given IDs.")
    #         return

    #     for order in orders:
    #         try:
    #             # Call the private method to generate the invoice
    #             order._generate_pos_order_invoice()
    #             print(f"Invoice generated for POS Order (ID: {order.id})")
    #         except Exception as e:
    #             print(f"Failed to generate invoice for POS Order (ID: {order.id}) with error: {e}")


    @api.model
    def create_pos_orders(self):
        # Get the active POS session
        pos_session = self.env['pos.session'].search([('state', '=', 'opened')], limit=1)
        if not pos_session:
            raise UserError('No active POS session found.')
        
        # Get all products to be used in orders
        product_codes = ['LBR00001', 'LBR00002', 'LBR00003', 'LBR00088', 'LBR00099', 'LBR00008', 'LBR00007', 'LBR00006', 'LBR00009', 'LBR00004']
        products = self.env['product.product'].search([('default_code', 'in', product_codes)])
        if not products:
            raise UserError('No products found.')

        pos_orders = []
        for i in range(100):  # Create 50 POS orders
            order_lines = []
            payment_lines = []
            total_amount = 0  # Initialize total_amount
            total_tax = 0  # Initialize total_tax

            for product in products:
                qty = random.randint(1, 10)  # Set quantity to a random number between 1 and 10
                taxes = product.taxes_id.compute_all(product.list_price, quantity=qty, product=product)
                line_tax = sum(t['amount'] for t in taxes['taxes'])
                line_total = taxes['total_included']
                line_subtotal = taxes['total_excluded']
                line_subtotal_incl = line_subtotal + line_tax 

                order_line = (0, 0, {
                    'product_id': product.id,
                    'name': product.name,
                    'full_product_name': product.name,
                    'qty': qty,  # Use the random quantity here
                    'price_unit': product.list_price,
                    'price_subtotal': line_subtotal,  # Set subtotal
                    'price_subtotal_incl': line_subtotal_incl,
                    'tax_ids': [(6, 0, product.taxes_id.ids)],
                })
                order_lines.append(order_line)
                
                total_amount += line_total
                total_tax += line_tax

            payment_method = self.env['pos.payment.method'].search([], limit=1)
            if not payment_method:
                raise UserError('No payment method found.')
            
            payment_line = (0, 0, {
                'payment_method_id': 6,
                'amount': total_amount,  # Full amount as paid
            })

            amount_paid = total_amount  # Assuming the full amount is paid
            amount_return = 0

            pos_order = self.env['pos.order'].create({
                'session_id': pos_session.id,
                'name': f"POS-{i+1:05d}",
                'partner_id': False,  # or you can set a specific partner
                'lines': order_lines,
                'partner_id': 322,
                'employee_id': 1,
                'payment_ids': [payment_line],
                'amount_total': total_amount,
                'amount_tax': total_tax,
                'amount_paid': amount_paid,
                'amount_return': amount_return,
                'state': 'invoiced'
            })
            pos_orders.append(pos_order)

        return pos_orders

    def write_orderref(self):
        pos = self.env['pos.order'].search([])
        for i in pos:
            i.write({'to_invoice': True})