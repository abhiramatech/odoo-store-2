from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import xmlrpc.client
from .odoo_client import OdooClient
from .data_transaksi import DataTransaksi
from .data_integrator import DataIntegrator
from .data_transaksiMCtoSS import DataTransaksiMCtoSS
from datetime import datetime, timedelta

class SettingConfig(models.Model):
    _name = "setting.config"
    _rec_name = "vit_config_server_name"
    _description = "Master Configuration"

    SERVER_SELECTION = [
        ('mc', 'Master Console'),
        ('ss', 'Store Server'),
    ]

    vit_config_server = fields.Selection(selection=SERVER_SELECTION, string='Server Selection', required=True)
    vit_config_server_name = fields.Char(string='Server Name', required=True)
    vit_config_url = fields.Char(string='url', required=True)
    vit_config_db = fields.Char(string='Database Name', required=True)
    vit_config_username = fields.Char(string='Username', required=True)
    vit_config_password = fields.Char(string='Password', required=True)
    vit_config_password_api = fields.Char(string='Password API')
    vit_linked_server = fields.Boolean(string="Linked Server", default=False, required=True)
    vit_state = fields.Selection([
        ('failed', 'Failed'),
        ('success', 'Success')], default='failed', string="Status")

    def get_config_mc(self):
        search_config = self.env['setting.config'].search([('vit_config_server', '=', 'mc')])
        if search_config:
            config_mc = search_config[0]
            url = config_mc.vit_config_url + "/jsonrpc"
            db_name = config_mc.vit_config_db
            username = config_mc.vit_config_username
            password = config_mc.vit_config_password
            server_type = config_mc.vit_config_server
            server_name = config_mc.vit_config_server_name
            linked_server = config_mc.vit_linked_server

            if linked_server == True:
                mc_client = OdooClient(url, db_name, username, password, server_name)
                # raise ValidationError(_(f"{url}, {db_name}, {username}, {password}")) buat check debug ya 
        else:
            raise ValidationError(_(f"Master Console belum terkonfigurasi"))
        
        return mc_client
    
    def get_config(self, store):
        mc_client = self.get_config_mc()
        ss_clients = []

        if store:
            search_config = self.env['setting.config'].search([('id', '=', store)])
        else:
            # get config all store
            search_config = self.env['setting.config'].search([('vit_config_server', '=', 'ss')])

        for configs in search_config:
            url = configs.vit_config_url + "/jsonrpc"
            db_name = configs.vit_config_db
            username = configs.vit_config_username
            password = configs.vit_config_password
            server_type = configs.vit_config_server
            server_name = configs.vit_config_server_name
            linked_server = configs.vit_linked_server
            # raise ValidationError(_(f"{url}, {db_name}, {username}, {password}, {server_type}, {server_name}, {linked_server}"))

            if linked_server == True:
                ss_clients.append(OdooClient(url, db_name, username, password, server_name))

        if mc_client is None or not ss_clients:
            raise ValueError("Both Master Console and Store Server configurations are required.")

        return mc_client, ss_clients
    
    def get_date(self, datefrom, dateto):
        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
        else:
            date_to = datetime.today()
            date_from = date_to - timedelta(days=3)
        
        return date_from, date_to
    
    def create_list_warehouse(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.transfer_warehouse_master('stock.warehouse', ['name', 'lot_stock_id', 'location_transit'], 'Insert Warehouse', datefrom, dateto)

    def convert_datetime_to_string(self, date_from, date_to):
        # Konversi datetime ke string
        if isinstance(date_from, datetime):
            date_from = date_from.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(date_to, datetime):
            date_to = date_to.strftime('%Y-%m-%d %H:%M:%S')

        return date_from, date_to
    
    def update_location_idmc(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksiMCtoSS.update_location_id_mc('stock.location', ['id', 'complete_name'], 'Update ID MC', datefrom, dateto)

    def create_master_item_utility(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_master = DataIntegrator(mc_client, ss_client)
            integrator_master.transfer_data('account.tax', ['name', 'description', 'amount_type', 'active', 'type_tax_use', 'tax_scope', 'amount', 'invoice_label', 'price_include', 'include_base_amount', 'include_base_amount', 'invoice_repartition_line_ids', 'create_date', 'write_date'], 'Master Tax', date_from, date_to)
            integrator_master.transfer_data('product.category', ['complete_name', 'name', 'parent_id', 'property_valuation', 'create_date', 'write_date'], 'Master Item Group', date_from, date_to)
            integrator_master.transfer_data('pos.category', ['name', 'parent_id', 'sequence', 'create_date', 'write_date'], 'Master POS Category', date_from, date_to)
            integrator_master.transfer_data('uom.category', ['name', 'is_pos_groupable', 'create_date', 'write_date'], 'Master UoM Group', date_from, date_to)
            integrator_master.transfer_data('uom.uom', ['category_id', 'uom_type', 'name', 'factor', 'rounding', 'active', 'create_date', 'write_date'], 'Master UoM', date_from, date_to)

    def create_master_items(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_master = DataIntegrator(mc_client, ss_client)
            # raise ValidationError(_(f"{mc_client}, {ss_client}, {ss_clients}, {mc}, {ss}, {datefrom}, {dateto}, {date_from}, {date_to}")) # buat check debug ya
            integrator_master.transfer_data('product.template', ['name', 'sale_ok', 'purchase_ok', 'detailed_type', 'invoice_policy', 'uom_id', 'uom_po_id', 'list_price', 'standard_price', 'categ_id', 'default_code', 'pos_categ_ids', 'available_in_pos', 'taxes_id', 'active', 'create_date', 'write_date'], 'Master Item', date_from, date_to)

    def create_location(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksiMCtoSS.update_location_id_mc('stock.location', ['id', 'complete_name'], 'Update ID MC', datefrom, dateto)
    
    def create_payment_method_pos_config_journal_invoicing(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksiMCtoSS.payment_method_from_mc('pos.payment.method', ['id', 'name', 'is_online_payment', 'split_transactions', 'journal_id', 'config_ids'], 'Transaksi PoS Payment Method', datefrom, dateto)
            integrator_transaksiMCtoSS.journal_account_from_mc('account.journal', ['id', 'name', 'type', 'refund_sequence', 'code', 'account_control_ids', 'invoice_reference_type', 'invoice_reference_model' ], 'Transaksi Journal', datefrom, dateto)
            # integrator_transaksiMCtoSS.pos_config_from_mc('pos.config', ['id', 'name', 'module_pos_hr', 'is_posbox', 'other_devices'], 'Transaksi PoS Config', datefrom, dateto)

    def create_master_pricelist(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_master = DataIntegrator(mc_client, ss_client)
            integrator_master.transfer_data('product.pricelist', ['name', 'currency_id', 'item_ids', 'create_date', 'write_date'], 'Master Pricelist', date_from, date_to)

    def create_master_operation_type(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_master = DataIntegrator(mc_client, ss_client)
            integrator_master.transfer_data('ir.sequence', ['name', 'implementation', 'code', 'active', 'prefix', 'suffix', 'use_date_range', 'padding', 'number_increment', 'create_date', 'write_date'], 'Master Sequence', date_from, date_to)
            integrator_master.transfer_data('stock.picking.type', ['name', 'code', 'sequence_id', 'sequence_code', 'warehouse_id', 'reservation_method', 'return_picking_type_id', 'default_location_return_id', 'create_backorder', 'use_create_lots', 'use_existing_lots', 'default_location_src_id', 'default_location_dest_id', 'create_date', 'write_date'], 'Master Operation', date_from, date_to)

    def create_master_discount(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksiMCtoSS.transfer_discount_loyalty('loyalty.program', ['id', 'name', 'program_type', 'currency_id', 'pricelist_ids', 'portal_point_name', 'portal_visible', 'trigger', 'applies_on', 'date_from', 'date_to', 'limit_usage', 'pos_ok', 'pos_config_ids', 'sale_ok', 'vit_trxid', 'index_store', 'reward_ids', 'rule_ids'], 'Transfer Discount/Loyalty', datefrom, dateto)
            # integrator_transaksiMCtoSS.update_discount_loyalty('loyalty.program', ['id', 'name', 'program_type', 'currency_id', 'pricelist_ids', 'portal_point_name', 'portal_visible', 'trigger', 'applies_on', 'date_from', 'date_to', 'limit_usage', 'pos_ok', 'pos_config_ids', 'sale_ok', 'vit_trxid', 'index_store', 'reward_ids', 'rule_ids'], 'Transfer Discount/Loyalty', datefrom, dateto)

    def update_master_discount(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksiMCtoSS.update_discount_loyalty('loyalty.program', ['id', 'name', 'program_type', 'currency_id', 'pricelist_ids', 'portal_point_name', 'portal_visible', 'trigger', 'applies_on', 'date_from', 'date_to', 'limit_usage', 'pos_ok', 'pos_config_ids', 'sale_ok', 'vit_trxid', 'index_store', 'reward_ids', 'rule_ids'], 'Transfer Discount/Loyalty', datefrom, dateto)
    
    def create_voucher_loyalty(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksiMCtoSS.transfer_loyalty_point_mc_to_ss('loyalty.program', ['id', 'name', 'program_type', 'currency_id', 'pricelist_ids', 'portal_point_name', 'portal_visible', 'trigger', 'applies_on', 'date_from', 'date_to', 'limit_usage', 'pos_ok', 'pos_config_ids', 'sale_ok', 'vit_trxid', 'index_store', 'reward_ids', 'rule_ids'], 'Transfer Loyalty Point', datefrom, dateto)
            # integrator_transaksi.update_loyalty_point_ss_to_mc('loyalty.program', ['id', 'name', 'program_type', 'currency_id', 'pricelist_ids', 'portal_point_name', 'portal_visible', 'trigger', 'applies_on', 'date_from', 'date_to', 'limit_usage', 'pos_ok', 'pos_config_ids', 'sale_ok', 'vit_trxid', 'reward_ids', 'rule_ids'], 'Transfer Discount/Loyalty', datefrom, dateto)

    def update_voucher_loyalty_store_to_mc(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.update_loyalty_point_ss_to_mc('loyalty.program', ['id', 'name', 'program_type', 'currency_id', 'pricelist_ids', 'portal_point_name', 'portal_visible', 'trigger', 'applies_on', 'date_from', 'date_to', 'limit_usage', 'pos_ok', 'pos_config_ids', 'sale_ok', 'vit_trxid', 'reward_ids', 'rule_ids'], 'Transfer Discount/Loyalty', datefrom, dateto)

    def update_voucher_loyalty_mc_to_store(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksiMCtoSS.update_loyalty_point_mc_to_ss('loyalty.program', ['id', 'name', 'program_type', 'currency_id', 'pricelist_ids', 'portal_point_name', 'portal_visible', 'trigger', 'applies_on', 'date_from', 'date_to', 'limit_usage', 'pos_ok', 'pos_config_ids', 'sale_ok', 'vit_trxid', 'reward_ids', 'rule_ids'], 'Transfer Discount/Loyalty', datefrom, dateto)

    def create_master_customers_from_mc_to_store(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_master = DataIntegrator(mc_client, ss_client)
            integrator_master.transfer_data('res.partner.title', ['name', 'shortcut', 'create_date', 'write_date'], 'Master Customer Title', date_from, date_to)
            integrator_master.transfer_data('res.partner', ['name', 'street', 'street2', 'phone', 'mobile', 'email', 'website','title','customer_rank', 'supplier_rank', 'customer_code', 'create_date', 'write_date'], 'Master Customer', date_from, date_to)

    def create_master_customers_from_ss_to_mc(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_master = DataIntegrator(mc_client, ss_client)
            # raise ValidationError(_(f"{mc_client}, {ss_client}, {ss_clients}, {mc}, {ss}, {datefrom}, {dateto}, {date_from}, {date_to}")) buat check debug ya
            integrator_master.transfer_data_mc('res.partner.title', ['name', 'shortcut', 'create_date', 'write_date'], 'Master Customer Title', date_from, date_to)
            integrator_master.transfer_data_mc('res.partner', ['name', 'street', 'street2', 'phone', 'mobile', 'email', 'website','title','customer_rank', 'supplier_rank', 'customer_code', 'create_date', 'write_date'], 'Master Customer', date_from, date_to)
            # integrator_master.transfer_data_mc('loyalty.card', ['code', 'points_display', 'expiration_date', 'partner_id', 'points', 'program_id'], 'Master Loyalty', date_from, date_to)

    def create_master_employee_from_ss_to_mc(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_master = DataIntegrator(mc_client, ss_client)
            integrator_master.transfer_data_mc('hr.employee', ['name', 'mobile_phone', 'work_phone', 'work_email', 'create_date', 'write_date'], 'Sales Employee', date_from, date_to)

    def create_purchase_order_from_mc_to_ss(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksiMCtoSS.purchase_order_from_mc('purchase.order', ['name', 'partner_id', 'partner_ref', 'currency_id', 'date_approve', 'date_planned', 'picking_type_id', 'vit_trxid'], 'Transaksi Purchase Order', date_from, date_to)

    def delete_log_note(self):
        mc_client, ss_clients = self.get_config(False)
        for ss_client in ss_clients:
            integrator_master = DataIntegrator(mc_client, ss_client)
            integrator_master.set_log_mc.delete_data_log_expired()
            integrator_master.set_log_ss.delete_data_log_expired()

    def transfer_pos_order_invoice(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.transfer_pos_order_invoice_ss_to_mc('pos.order', ['id', 'name', 'date_order', 'session_id', 'user_id', 'partner_id', 'pos_reference', 'vit_trxid', 'tracking_number', 'pricelist_id', 'employee_id', 'margin', 'amount_tax', 'amount_total', 'amount_paid', 'amount_return', 'state', 'lines', 'payment_ids'], 'Transaksi PoS Order Invoice', date_from, date_to)

    def transfer_pos_order_invoice_rescue(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.transfer_pos_order_invoice_session_closed('pos.order', ['id', 'name', 'date_order', 'session_id', 'user_id', 'partner_id', 'pos_reference', 'vit_trxid', 'tracking_number', 'pricelist_id', 'employee_id', 'margin', 'amount_tax', 'amount_total', 'amount_paid', 'amount_return', 'state', 'lines', 'payment_ids'], 'Transaksi PoS Order Invoice', date_from, date_to)

    def create_end_of_shift(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.transfer_end_shift_from_store('end.shift', ['doc_num', 'cashier_id', 'session_id', 'start_date', 'end_date', 'is_integrated', 'line_ids'], 'Transfer End Shift')

    def create_update_session_pos(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.update_session_status('pos.session', ['name', 'state', 'start_at', 'stop_at', 'cash_register_balance_start', 'cash_register_balance_end_real'], 'Update Session PoS Order', date_from, date_to)
            integrator_transaksi.transfer_pos_order_session('pos.session', ['name', 'config_id', 'user_id', 'start_at', 'stop_at', 'state'], 'Master Session PoS Order Invoice', date_from, date_to)

    def create_pos_order_utility(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.update_session_status('pos.ses?sion', ['name', 'id','state', 'start_at', 'stop_at', 'cash_register_balance_start', 'cash_register_balance_end_real'], "Session Updated", date_from, date_to)
            integrator_transaksi.transfer_pos_order_session('pos.session', ['name', 'config_id', 'user_id', 'start_at', 'stop_at', 'state'], 'Master Session PoS Order Invoice', date_from, date_to)

    def validate_GRPO(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.validate_GRPO('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'move_ids_without_package'], 'Validate GRPO Inventory', date_from, date_to)

    def validate_goods_receipts_store(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.validate_goods_receipts_store('stock.picking', ['id'], 'Validate GRPO Inventory', date_from, date_to)

    def validate_goods_issue_store(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.validate_goods_issue_store('stock.picking', ['id'], 'Validate GRPO Inventory', date_from, date_to)

    def transfer_goods_receipt(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.transfer_goods_receipt('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'move_ids_without_package'],'Transaksi Goods Receipt', date_from, date_to)

    def transfer_goods_issue(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.transfer_goods_issue('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'move_ids_without_package'], 'Transaksi PoS Order Inventory', date_from, date_to)

    def transfer_internal_transfers(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.transfer_internal_transfers('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'move_ids_without_package'], 'Transaksi Goods Issue', date_from, date_to)

    def transfer_receipts_ss_to_mc(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.transfer_receipts_ss('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'move_ids_without_package'],'Transaksi Receipt', date_from, date_to)

    def transfer_inventory_adjustment(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksi.transfer_stock_adjustment('stock.move.line', ['reference', 'quantity', 'product_id', 'location_id', 'location_dest_id', 'company_id', 'state'], 'Transaksi Adjustment Stock', date_from, date_to)
            
    def transfer_ts_out(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksi.transfer_TSOUT_NEW('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'target_location', 'move_ids_without_package'], 'Transaksi TS Out', date_from, date_to)
            # integrator_transaksiMCtoSS.ts_in_from_mc('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'target_location', 'move_ids_without_package'], 'Transaksi TS In', date_from, date_to)
            # integrator_transaksi.validate_tsin_tsout('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'vit_trxid', 'move_ids_without_package'], 'Transaksi PoS Order Inventory', date_from, date_to)
    
    def transfer_ts_in(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksiMCtoSS.ts_in_from_mc('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'target_location', 'move_ids_without_package'], 'Transaksi TS In', date_from, date_to)
            # integrator_transaksi.validate_tsin_tsout('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'vit_trxid', 'move_ids_without_package'], 'Transaksi PoS Order Inventory', date_from, date_to)
    
    def validate_transfer_ts_in(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksi = DataTransaksi(ss_client, mc_client)
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            # integrator_transaksiMCtoSS.ts_in_from_mc('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'target_location', 'move_ids_without_package'], 'Transaksi TS In', date_from, date_to)
            integrator_transaksi.validate_tsin_tsout('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'vit_trxid', 'move_ids_without_package'], 'Transaksi PoS Order Inventory', date_from, date_to)

    def transfer_goods_receipt_from_mc_to_store(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksiMCtoSS.transfer_goods_receipt('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'move_ids_without_package'], 'Transaksi Goods Receipts', date_from, date_to)

    def validate_invoice(self, mc, ss, datefrom, dateto):
            if mc and ss:
                mc_client = mc
                ss_clients = ss
            else:
                mc_client, ss_clients = self.get_config(False)

            if datefrom and dateto:
                date_from = datefrom
                date_to = dateto
                # Format date_from and date_to to include time
                date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
                date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
            else:
                date_from, date_to = self.get_date(False, False)

            date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

            for ss_client in ss_clients:
                integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
                integrator_transaksiMCtoSS.validate_invoice('pos.order', ['id'], 'Validate PoS Order Invoice', date_from, date_to)

    def validate_ts_out_mc(self, mc, ss, datefrom, dateto):
            if mc and ss:
                mc_client = mc
                ss_clients = ss
            else:
                mc_client, ss_clients = self.get_config(False)

            if datefrom and dateto:
                date_from = datefrom
                date_to = dateto
                # Format date_from and date_to to include time
                date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
                date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
            else:
                date_from, date_to = self.get_date(False, False)

            date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

            for ss_client in ss_clients:
                integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
                integrator_transaksiMCtoSS.validate_tsout_mc('stock.picking', ['id'], 'Validate TS Out MC', date_from, date_to)

    def validate_goods_receipts_mc(self, mc, ss, datefrom, dateto):
            if mc and ss:
                mc_client = mc
                ss_clients = ss
            else:
                mc_client, ss_clients = self.get_config(False)

            if datefrom and dateto:
                date_from = datefrom
                date_to = dateto
                # Format date_from and date_to to include time
                date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
                date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
            else:
                date_from, date_to = self.get_date(False, False)

            date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

            for ss_client in ss_clients:
                integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
                integrator_transaksiMCtoSS.validate_goods_receipts_mc('stock.picking', ['id'], 'Validate Goods Receipts MC', date_from, date_to)

    def validate_goods_issue_mc(self, mc, ss, datefrom, dateto):
            if mc and ss:
                mc_client = mc
                ss_clients = ss
            else:
                mc_client, ss_clients = self.get_config(False)

            if datefrom and dateto:
                date_from = datefrom
                date_to = dateto
                # Format date_from and date_to to include time
                date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
                date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
            else:
                date_from, date_to = self.get_date(False, False)

            date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

            for ss_client in ss_clients:
                integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
                integrator_transaksiMCtoSS.validate_goods_issue_mc('stock.picking', ['id'], 'Validate Goods Receipts MC', date_from, date_to)

    def transfer_receipt_from_mc_to_store(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksiMCtoSS.transfer_receipts('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'move_ids_without_package'], 'Transaksi Goods Receipts', date_from, date_to)

    def transfer_goods_issue_from_mc_to_store(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksiMCtoSS.transfer_goods_issue('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'move_ids_without_package'], 'Transaksi Goods Issue', date_from, date_to)        

    def transfer_internal_transfers_from_mc_to_store(self, mc, ss, datefrom, dateto):
        if mc and ss:
            mc_client = mc
            ss_clients = ss
        else:
            mc_client, ss_clients = self.get_config(False)

        if datefrom and dateto:
            date_from = datefrom
            date_to = dateto
            # Format date_from and date_to to include time
            date_from = date_from.strftime("%Y-%m-%d %H:%M:%S.%f")
            date_to = date_to.strftime("%Y-%m-%d %H:%M:%S.%f")
        else:
            date_from, date_to = self.get_date(False, False)

        date_from, date_to = self.convert_datetime_to_string(date_from, date_to)

        for ss_client in ss_clients:
            integrator_transaksiMCtoSS = DataTransaksiMCtoSS(mc_client, ss_client)
            integrator_transaksiMCtoSS.transfer_internal_transfers('stock.picking', ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'move_ids_without_package'], 'Transaksi Internal Transfers', date_from, date_to)
    
    def create(self, vals):
        if vals:
            try:
                url = vals.get('vit_config_url')
                db = vals.get('vit_config_db')
                username = vals.get('vit_config_username')
                password = vals.get('vit_config_password')
                common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
                uid = common.authenticate(db, username, password, {})
                
                if uid:
                    vals['vit_linked_server'] = True
                    vals['vit_state'] = 'success'
                if not uid:
                    vals['vit_linked_server'] = False
                    vals['vit_state'] = 'failed'
            except Exception as e:
                vals['vit_linked_server'] = False
                vals['vit_state'] = 'failed'

        if vals.get('vit_config_url'):
            existing_record = self.env['setting.config'].search([('vit_config_url', '=', vals['vit_config_url'])])
            if existing_record:
                raise UserError(_("URL already exists"))
            
        if vals.get('vit_config_server_name'):
            existing_record = self.env['setting.config'].search([('vit_config_server_name', '=', vals['vit_config_server_name'])])
            if existing_record:
                raise UserError(_("Server Name already exists"))

        return super(SettingConfig, self).create(vals)

    def write(self, vals):
        if 'vit_config_url' in vals:
             existing_record = self.env['setting.config'].search([('vit_config_url', '=', vals['vit_config_url'])])
             if existing_record:
                 raise UserError(_("URL already exists"))
        
        if vals.get('vit_config_server_name'):
             existing_record = self.env['setting.config'].search([('vit_config_server_name', '=', vals['vit_config_server_name'])])
             if existing_record:
                 raise UserError(_("Server Name already exists"))
             
        if vals:
            try:
                for record in self:
                # URL dan parameter koneksi API Odoo
                    url = record.vit_config_url
                    db = record.vit_config_db
                    username = record.vit_config_username
                    password = record.vit_config_password
                    
                    url = vals.get('vit_config_url') if vals.get('vit_config_url') is not None else record.vit_config_url
                    db = vals.get('vit_config_db') if vals.get('vit_config_db') is not None else record.vit_config_db
                    username = vals.get('vit_config_username') if vals.get('vit_config_username') is not None else record.vit_config_username
                    password = vals.get('vit_config_password') if vals.get('vit_config_password') is not None else record.vit_config_password

                    # raise ValidationError(_(f"{url}, {db}, {username}, {password}")) # buat check debug ya
                    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
                    uid = common.authenticate(db, username, password, {})

                    if uid:
                        vals['vit_linked_server'] = True
                        vals['vit_state'] = 'success'
                    if not uid: 
                        vals['vit_linked_server'] = False
                        vals['vit_state'] = 'failed'
            except Exception as e:
                vals['vit_linked_server'] = False
                vals['vit_state'] = 'failed'
            
        super(SettingConfig, self).write(vals)
    
    def action_test_connect_button(self):
        for record in self:
            try:
                # URL dan parameter koneksi API Odoo
                url = record.vit_config_url
                db = record.vit_config_db
                username = record.vit_config_username
                password = record.vit_config_password

                # Autentikasi ke instance Odoo menggunakan xmlrpc.client
                common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
                uid = common.authenticate(db, username, password, {})
                
                if uid:
                    # Jika koneksi berhasil, set vit_linked_server menjadi True dan kirim notifikasi
                    # record.write({'vit_linked_server': True})
                    # record.write({'vit_state': 'success'})
                    # return True
                
                    message = _("Connection success for %s." % record.vit_config_server_name)
                    return {'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _('Success'),
                                'message': message,
                                'type': 'info',  # types: success, warning, info, danger
                                'sticky': False,  # True/False will display for few seconds if false
                            }}

                if not uid:
                    # Jika koneksi gagal
                    # record.write({'vit_linked_server': False})
                    # record.write({'vit_state': 'failed'})
                    # return True
                
                    message = _("Connection failed for %s. Please check your credentials." % record.vit_config_server_name)
                    return {'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _('Warning'),
                                'message': message,
                                'type': 'warning',  # types: success, warning, info, danger
                                'sticky': False,  # True/False will display for few seconds if false
                            }}
                
            except Exception as e:
                # Jika terjadi error lainnya
                # record.write({'vit_linked_server': False})
                # record.write({'vit_state': 'failed'})
                # return True
            
                message = _("Connection failed for %s. Please check your credentials." % record.vit_config_server_name)
                return {'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': _('Warning'),
                                'message': message,
                                'type': 'warning',  # types: success, warning, info, danger
                                'sticky': False,  # True/False will display for few seconds if false
                            }}
    
    @api.onchange('vit_config_server')
    def _onchange_vit_config_server(self):
        if self.vit_config_server == 'mc':
            self.vit_config_server_name = 'MC'
        if self.vit_config_server == 'ss':
            self.vit_config_server_name = ''