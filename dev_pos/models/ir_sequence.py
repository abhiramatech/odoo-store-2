from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
  

class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    is_from_operation_types = fields.Boolean(string="From Operation Types", default=False)
    is_integrated = fields.Boolean(string="Integrated", default=False, readonly=True, tracking=True)
    index_store = fields.Many2many('setting.config', string="Index Store", readonly=True)

    # @api.model
    # def create(self, vals):
    #     # Panggil metode create asli untuk membuat record
    #     record = super(IrSequence, self).create(vals)
    #     # Ambil ID dari record yang baru saja dibuat
    #     sequence_id = record.id

    #     if sequence_id:
    #         # Dapatkan nilai dari stock.picking.type yang berhubungan
    #         if not vals.get('warehouse_name'):
    #             # Mencari semua record dari stock.picking.type
    #             picking_types = self.env['stock.picking.type'].search([])
    #             # Loop melalui hasil pencarian dan akses nilai warehouse_id
    #             for picking_type in picking_types:
    #                 warehouse_id = picking_type.warehouse_id

    #             #warehouses = self.env['stock.warehouse'].search([])
    #             warehouse = self.env['stock.warehouse'].browse(warehouse_id)
                
    #             #picking_type = self.env['stock.picking.type'].browse(picking_type_id)
    #             if picking_type and picking_type.warehouse_id:
    #                 vals['warehouse_name'] = picking_type.warehouse_id.name
    #             else:
    #                 vals['warehouse_name'] = 'VIT'
    #         else:
    #             vals['warehouse_name'] = 'WH name ada di vals'
    #     else:
    #         vals['warehouse_name'] = 'Belum dapet value sequence_id'

    #     return super(IrSequence, self).create(vals)
        