from odoo import models, fields, _, api
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
from .odoo_client import OdooClient

class ManualSyncMCToSSIntegration(models.Model):
    _name = 'manual.sync.mc.to.ss'
    _inherit = "setting.config"
    _description = 'Manual Sync For Integration'

    store_sync = fields.Many2one('setting.config', string='Store')
    date_from = fields.Date(string='Date from')
    date_to = fields.Date(string='Date To')
    #MC To Store
    master_item_utils = fields.Boolean(string="Master Item Utility", default=False)
    master_item = fields.Boolean(string="Master Item", default=False)
    master_customer = fields.Boolean(string="Master Customer", default=False)
    master_location = fields.Boolean(string="Update Location", default=False)
    master_pricelist = fields.Boolean(string="Master Pricelist", default=False)
    master_operation_type = fields.Boolean(string="Master Operation Type", default=False)
    master_discount = fields.Boolean(string="Master Discount & Promo", default=False)
    update_discount = fields.Boolean(string="Update Discount & Promo", default=False)
    master_voucher = fields.Boolean(string="Master Voucher & Loyalty", default=False)
    update_voucher_mc = fields.Boolean(string="Update Voucher & Loyalty Store to MC", default=False)
    update_voucher_store = fields.Boolean(string="Update Voucher & Loyalty MC to Store", default=False)
    master_pos_utility = fields.Boolean(string="Master PoS Config", default=False)
    list_warehouse = fields.Boolean(string="Master List Warehouse", default=False)
    vit_internal_transfers = fields.Boolean(string="Internal Transfers", default=False)
    vit_goods_issue = fields.Boolean(string="Goods Issue", default=False)
    vit_goods_receipts = fields.Boolean(string="Goods Receipts", default=False)
    vit_receipts_to_ss = fields.Boolean(string="GRPO", default=False)
    vit_ts_in = fields.Boolean(string="TS In", default=False)
    vit_po = fields.Boolean(string="Purchase Orders", default=False)
    vit_val_inv = fields.Boolean(string="Create Invoice", default=False)
    vit_val_goods_receipts = fields.Boolean(string="Validate Goods Receipts", default=False)
    vit_val_goods_issue = fields.Boolean(string="Validate Goods Issue", default=False)
    vit_val_ts_out = fields.Boolean(string="Validate TS Out", default=False)

    def action_start(self):
        store, date_from, date_to, master_item_utils, master_item, master_customer, master_location, master_pricelist, master_operation_type, master_discount, update_discount, master_voucher, update_voucher_mc, update_voucher_store, master_pos_utility, list_warehouse, vit_internal_transfers, vit_goods_issue, vit_goods_receipts, vit_receipts_to_ss, vit_ts_in, vit_po, vit_val_inv, vit_val_goods_receipts, vit_val_goods_issue, vit_val_ts_out = self.search_manual_sync()
        mc_client, ss_clients = self.get_config(store.id)
        datefrom, dateto = self.get_date(date_from, date_to)

        if master_item_utils:
            self.create_master_item_utility(mc_client, ss_clients, datefrom, dateto)
        if master_item:
            self.create_master_items(mc_client, ss_clients, datefrom, dateto)
        if master_customer:
            self.create_master_customers_from_mc_to_store(mc_client, ss_clients, datefrom, dateto)
        if master_location:
            self.create_location(mc_client, ss_clients, datefrom, dateto)
        if master_pricelist:
            self.create_master_pricelist(mc_client, ss_clients, datefrom, dateto)
        if master_operation_type:
            self.create_master_operation_type(mc_client, ss_clients, datefrom, dateto)
        if master_discount:
            self.create_master_discount(mc_client, ss_clients, datefrom, dateto)
        if update_discount:
            self.update_master_discount(mc_client, ss_clients, datefrom, dateto)
        if master_voucher:
            self.create_voucher_loyalty(mc_client, ss_clients, datefrom, dateto)
        if update_voucher_mc:
            self.update_voucher_loyalty_store_to_mc(mc_client, ss_clients, datefrom, dateto)
        if update_voucher_store:
            self.update_voucher_loyalty_mc_to_store(mc_client, ss_clients, datefrom, dateto)
        if master_pos_utility:
            self.create_payment_method_pos_config_journal_invoicing(mc_client, ss_clients, datefrom, dateto)
        if list_warehouse:
            self.create_list_warehouse(mc_client, ss_clients, datefrom, dateto)
        if vit_internal_transfers:
            self.transfer_internal_transfers_from_mc_to_store(mc_client, ss_clients, datefrom, dateto)
        if vit_goods_issue:
            self.transfer_goods_issue_from_mc_to_store(mc_client, ss_clients, datefrom, dateto)
        if vit_goods_receipts:
            self.transfer_goods_receipt_from_mc_to_store(mc_client, ss_clients, datefrom, dateto)
        if vit_receipts_to_ss:
            self.transfer_receipt_from_mc_to_store(mc_client, ss_clients, datefrom, dateto)
        if vit_ts_in:
            self.transfer_ts_in(mc_client, ss_clients, datefrom, dateto)
        if vit_po:
            self.create_purchase_order_from_mc_to_ss(mc_client, ss_clients, datefrom, dateto)
        if vit_val_inv:
            self.validate_invoice(mc_client, ss_clients, datefrom, dateto)
        if vit_val_goods_receipts:
            self.validate_goods_receipts_mc(mc_client, ss_clients, datefrom, dateto)
        if vit_val_goods_issue:
            self.validate_goods_issue_mc(mc_client, ss_clients, datefrom, dateto)
        if vit_val_ts_out:
            self.validate_ts_out_mc(mc_client, ss_clients, datefrom, dateto)

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
        search_manual_sync = self.env['manual.sync.mc.to.ss'].search([], order='id desc', limit=1)
        if search_manual_sync:
            configs = search_manual_sync[0]
            store = configs.store_sync
            date_from = configs.date_from
            date_to = configs.date_to
            master_item_utils = configs.master_item_utils
            master_item = configs.master_item
            master_customer = configs.master_customer
            master_location = configs.master_location
            master_pricelist = configs.master_pricelist
            master_operation_type = configs.master_operation_type
            master_discount = configs.master_discount
            update_discount = configs.update_discount
            master_voucher = configs.master_voucher
            update_voucher_mc = configs.update_voucher_mc
            update_voucher_store = configs.update_voucher_store
            master_pos_utility = configs.master_pos_utility
            list_warehouse = configs.list_warehouse
            vit_internal_transfers= configs.vit_internal_transfers
            vit_goods_issue= configs.vit_goods_issue
            vit_goods_receipts = configs.vit_goods_receipts
            vit_receipts_to_ss = configs.vit_receipts_to_ss
            vit_ts_in = configs.vit_ts_in
            vit_po = configs.vit_po
            vit_val_inv = configs.vit_val_inv
            vit_val_goods_receipts = configs.vit_val_goods_receipts
            vit_val_goods_issue = configs.vit_val_goods_issue
            vit_val_ts_out = configs.vit_val_ts_out
        return store, date_from, date_to, master_item_utils, master_item, master_customer, master_location, master_pricelist, master_operation_type, master_discount, update_discount, master_voucher, update_voucher_mc, update_voucher_store, master_pos_utility, list_warehouse, vit_internal_transfers, vit_goods_issue, vit_goods_receipts, vit_receipts_to_ss, vit_ts_in, vit_po, vit_val_inv, vit_val_goods_receipts, vit_val_goods_issue, vit_val_ts_out
    
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
            if store_sync:
                vals['vit_config_server'] = store_sync.vit_config_server
                vals['vit_config_server_name'] = store_sync.vit_config_server_name + " - " + fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                vals['vit_config_url'] = store_sync.vit_config_url + " - " + fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                vals['vit_config_db'] = store_sync.vit_config_db
                vals['vit_config_username'] = store_sync.vit_config_username
                vals['vit_config_password'] = store_sync.vit_config_password
                vals['vit_linked_server'] = store_sync.vit_linked_server
            else:
                raise ValidationError(_(f"The master configuration has not been set. Please set the master configuration first."))
            
        return super(ManualSyncMCToSSIntegration, self).create(vals)