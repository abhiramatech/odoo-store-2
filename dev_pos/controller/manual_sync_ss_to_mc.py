from odoo import models, fields, _, api
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from .odoo_client import OdooClient

class ManualSyncSSToMCIntegratiion(models.Model):
    _name = 'manual.sync.ss.to.mc'
    _inherit = "setting.config"
    _description = 'Manual Sync For Integration'

    store_sync = fields.Many2one('setting.config', string='Store')
    date_from = fields.Date(string='Date from')
    date_to = fields.Date(string='Date To')
    #Store To MC
    master_customer_to_mc = fields.Boolean(string="Master Customer", default=False)
    master_employee_to_mc = fields.Boolean(string="Master Employee", default=False)
    vit_session = fields.Boolean(string="Session", default=False)
    vit_end_shift = fields.Boolean(string="End of Shift", default=False)
    vit_invoice = fields.Boolean(string="PoS Order", default=False)
    vit_invoice_rescue = fields.Boolean(string="PoS Order Rescue", default=False)
    vit_internal_transfers_to_mc = fields.Boolean(string="Internal Transfers", default=False)
    vit_goods_receipts_to_mc = fields.Boolean(string="Goods Receipts", default=False)
    vit_goods_issue_to_mc = fields.Boolean(string="Goods Issue", default=False)
    vit_receipts_to_mc = fields.Boolean(string="GRPO", default=False)
    vit_inventory_adjustment_to_mc = fields.Boolean(string="Inventory Adjustment", default=False)
    vit_ts_out = fields.Boolean(string="TS Out", default=False)
    vit_val_ts_in = fields.Boolean(string="Validate TS In", default=False)
    vit_val_grpo = fields.Boolean(string="Validate GRPO", default=False)
    vit_val_goods_receipts = fields.Boolean(string="Validate Goods Receipts", default=False)
    vit_val_goods_issue = fields.Boolean(string="Validate Goods Issue", default=False)

    def action_start(self):
        store, date_from, date_to, master_customer_to_mc, master_employee_to_mc, vit_session, vit_end_shift, vit_invoice, vit_invoice_rescue, vit_internal_transfers_to_mc, vit_goods_receipts_to_mc, vit_goods_issue_to_mc, vit_receipts_to_mc, inventory_adjustment_to_mc, vit_ts_out, vit_val_ts_in, vit_val_grpo, vit_val_goods_receipts, vit_val_goods_issue = self.search_manual_sync()
        store_id = store.id
        mc_client, ss_clients = self.get_config(store_id)
        datefrom, dateto = self.get_date(date_from, date_to)

        if master_customer_to_mc:
            self.create_master_customers_from_ss_to_mc(mc_client, ss_clients, datefrom, dateto)
        if master_employee_to_mc:
            self.create_master_employee_from_ss_to_mc(mc_client, ss_clients, datefrom, dateto)
        if vit_session:
            self.create_update_session_pos(mc_client, ss_clients, datefrom, dateto)
        if vit_end_shift:
            self.create_end_of_shift(mc_client, ss_clients, datefrom, dateto)
        if vit_invoice:
            self.transfer_pos_order_invoice(mc_client, ss_clients, datefrom, dateto)
        if vit_invoice_rescue:
            self.transfer_pos_order_invoice_rescue(mc_client, ss_clients, datefrom, dateto)
        if vit_internal_transfers_to_mc:
            self.transfer_internal_transfers(mc_client, ss_clients, datefrom, dateto)
        if vit_goods_receipts_to_mc:
            self.transfer_goods_receipt(mc_client, ss_clients, datefrom, dateto)
        if vit_goods_issue_to_mc:
            self.transfer_goods_issue(mc_client, ss_clients, datefrom, dateto)
        if vit_receipts_to_mc:
            self.transfer_receipts_ss_to_mc(mc_client, ss_clients, datefrom, dateto)
        if inventory_adjustment_to_mc:
            self.transfer_inventory_adjustment(mc_client, ss_clients, datefrom, dateto)
        if vit_ts_out:
            self.transfer_ts_out(mc_client, ss_clients, datefrom, dateto)
        if vit_val_ts_in:
            self.validate_transfer_ts_in(mc_client, ss_clients, datefrom, dateto)
        if vit_val_grpo:
            self.validate_GRPO(mc_client, ss_clients, datefrom, dateto)
        if vit_val_goods_receipts:
            self.validate_goods_receipts_store(mc_client, ss_clients, datefrom, dateto)
        if vit_val_goods_issue:
            self.validate_goods_issue_store(mc_client, ss_clients, datefrom, dateto)

        message = _("Sync Finished")
        return {'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': message,
                    'type': 'info',  # types: success, warning, info, danger
                    'sticky': True,  # True/False will display for few seconds if false
                }}
        
    def search_manual_sync(self):
        search_manual_sync = self.env['manual.sync.ss.to.mc'].search([], order='id desc', limit=1)
        if search_manual_sync:
            configs = search_manual_sync[0]
            store = configs.store_sync
            date_from = configs.date_from
            date_to = configs.date_to
            master_customer_to_mc = configs.master_customer_to_mc
            master_employee_to_mc = configs.master_employee_to_mc
            session = configs.vit_session
            end_shift = configs.vit_end_shift
            invoice = configs.vit_invoice
            invoice_rescue = configs.vit_invoice_rescue
            internal_transfers_to_mc = configs.vit_internal_transfers_to_mc
            goods_receipts_to_mc = configs.vit_goods_receipts_to_mc
            goods_issue_to_mc = configs.vit_goods_issue_to_mc
            receipts_to_mc = configs.vit_receipts_to_mc
            inventory_adjustment_to_mc = configs.vit_inventory_adjustment_to_mc
            ts_out = configs.vit_ts_out
            ts_in = configs.vit_val_ts_in
            grpo = configs.vit_val_grpo
            vit_val_goods_receipts = configs.vit_val_goods_receipts
            vit_val_goods_issue = configs.vit_val_goods_issue
        return store, date_from, date_to, master_customer_to_mc, master_employee_to_mc, session, end_shift, invoice, invoice_rescue,internal_transfers_to_mc, goods_receipts_to_mc, goods_issue_to_mc, receipts_to_mc, inventory_adjustment_to_mc, ts_out, ts_in, grpo, vit_val_goods_receipts, vit_val_goods_issue

    def create(self, vals):
        if vals.get('store_sync'):
            store_sync = self.env['setting.config'].browse(vals['store_sync'])
            vals['vit_config_server'] = store_sync.vit_config_server
            vals['vit_config_server_name'] = store_sync.vit_config_server_name + " - " + fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            vals['vit_config_url'] = store_sync.vit_config_url + " - " + fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            vals['vit_config_db'] = store_sync.vit_config_db
            vals['vit_config_username'] = store_sync.vit_config_username
            vals['vit_config_password'] = store_sync.vit_config_password
            vals['vit_linked_server'] = store_sync.vit_linked_server
        else:
            # jika store_sync kosong karena untuk semua store
            store_sync = self.env['setting.config'].search([('vit_config_server', '=', 'mc')])
            vals['vit_config_server'] = store_sync.vit_config_server
            vals['vit_config_server_name'] = store_sync.vit_config_server_name + " - " + fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            vals['vit_config_url'] = store_sync.vit_config_url + " - " + fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            vals['vit_config_db'] = store_sync.vit_config_db
            vals['vit_config_username'] = store_sync.vit_config_username
            vals['vit_config_password'] = store_sync.vit_config_password
            vals['vit_linked_server'] = store_sync.vit_linked_server

        return super(ManualSyncSSToMCIntegratiion, self).create(vals)