import requests
from datetime import datetime, timedelta
import pytz
from odoo import models, fields, api, SUPERUSER_ID
from odoo.exceptions import UserError
import random

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    is_closed = fields.Boolean(string="Closed", default=False, readonly=True, tracking=True)
    vit_trxid = fields.Char(string="Transaction ID", default=False, tracking=True)
    target_location = fields.Char(string="Target Location")
    stock_type = fields.Many2one('master.type', string="Stock Type")

    def button_validate(self):
        # Check if the operation type is 'Internal Transfers'
        if self.picking_type_id.code == 'internal':
            # Check if the source and destination locations are the same
            if self.location_id.id == self.location_dest_id.id:
                raise UserError("Cannot validate this operation: Source and destination locations are the same.")
        
        # Call the super method
        res = super(StockPicking, self).button_validate()
        return res
    
    @api.model
    def create_stock_pickings(self):
        # Temukan ID untuk operation type TS Out
        operation_type_id = self.env['stock.picking.type'].search([('name', 'ilike', 'Goods Issue')], limit=1)
        if not operation_type_id:
            raise UserError('Operation Type TS Out tidak ditemukan.')
        
        product_codes = ['LBR00001', 'LBR00002', 'LBR00003', 'LBR00088', 'LBR00099', 'LBR00008', 'LBR00007', 'LBR00006', 'LBR00009', 'LBR00004']
        products = self.env['product.product'].search([('default_code', 'in', product_codes)])
        # if len(products) != 10:
        #     raise UserError('Tidak semua produk dengan default_code yang ditentukan ditemukan.')

        stock_pickings = []
        for i in range(500):
            # Mengatur move_lines untuk setiap `stock.picking`
            move_lines = []
            for j, product in enumerate(products):
                quantity = random.uniform(1, 10)
                move_lines.append((0, 0, {
                    'name': product.name,
                    'product_id': product.id,
                    # 'product_uom_id': product.uom_id.id,
                    'product_uom_qty': quantity,
                    'quantity': quantity,
                    'location_id': 4,
                    'location_dest_id': 8,
                }))

            # target_location = self.env['master.warehouse'].search([('warehouse_name', '=', "Store 02")], limit=1)
            
            stock_picking = {
                'picking_type_id': operation_type_id.id,
                'location_id': 4,
                'location_dest_id': 8,
                # 'target_location': target_location.id,
                'move_ids_without_package': move_lines,
            }
            stock_pickings.append(stock_picking)
        
        self.env['stock.picking'].create(stock_pickings)

    def write_tsout(self):
        ts_out = self.env['stock.picking'].search([('picking_type_id.name', '=', 'TS In'), ('state', '=', 'assigned')])

        for res in ts_out:
            res.write({'is_integrated': True})