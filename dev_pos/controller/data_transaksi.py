import time
from datetime import datetime, timedelta
import pytz
import re
import concurrent.futures

# kalau ada case store nya beda zona waktu gimana
class DataTransaksi:
    def __init__(self, source_client, target_client):
        self.source_client = source_client
        self.target_client = target_client
        self.set_log_mc = SetLogMC(self.source_client)
        self.set_log_ss = SetLogSS(self.target_client)

    # Master Console --> Store Server
    # Store Server --> Master Console
    
    def transfer_pos_order_invoice_ss_to_mc(self, model_name, fields, description, date_from, date_to):
        try:
            # Fetching the data
            transaksi_posorder_invoice = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    model_name, 'search_read',
                                                                    [[['state', '=', 'invoiced'], ['is_integrated', '=', False], ['create_date', '>=', date_from], ['create_date', '<=', date_to]]],
                                                                    {'fields': fields})

            if not transaksi_posorder_invoice:
                print("Semua transaksi telah diproses.")
                return

            # Pre-fetch all necessary data
            partner_ids = [record.get('partner_id')[0] if isinstance(record.get('partner_id'), list) else record.get('partner_id') for record in transaksi_posorder_invoice]
            session_ids = [record.get('session_id')[0] if isinstance(record.get('session_id'), list) else record.get('session_id') for record in transaksi_posorder_invoice]
            employee_ids = [record.get('employee_id')[0] if isinstance(record.get('employee_id'), list) else record.get('employee_id') for record in transaksi_posorder_invoice]
            pricelist_id = [record.get('pricelist_id')[0] if isinstance(record.get('pricelist_id'), list) else record.get('pricelist_id') for record in transaksi_posorder_invoice]

            # Fetch partners
            partners_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'res.partner', 'search_read',
                                                        [[['id', 'in', partner_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            partners_source_dict = {partner['id']: partner['id_mc'] for partner in partners_source}

            # Fetch sessions
            sessions_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'pos.session', 'search_read',
                                                        [[['id', 'in', session_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            sessions_source_dict = {session['id']: session['id_mc'] for session in sessions_source}

            # Fetch employees
            employees_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            'hr.employee', 'search_read',
                                                            [[['id', 'in', employee_ids]]],
                                                            {'fields': ['id', 'id_mc']})
            employees_source_dict = {employee['id']: employee['id_mc'] for employee in employees_source}

            # Fetch pricelist
            pricelist_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            'product.pricelist', 'search_read',
                                                            [[['id', 'in', pricelist_id]]],
                                                            {'fields': ['id', 'id_mc']})
            pricelist_source_dict = {pricelist['id']: pricelist['id_mc'] for pricelist in pricelist_source}

            # Pre-fetch all pos.order.line and pos.payment data
            order_ids = [record['id'] for record in transaksi_posorder_invoice]
            pos_order_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'pos.order.line', 'search_read',
                                                        [[['order_id', 'in', order_ids]]],
                                                        {'fields': ['order_id', 'product_id', 'full_product_name', 'qty', 'price_unit', 'tax_ids_after_fiscal_position', 'tax_ids', 'discount', 'price_subtotal', 'price_subtotal_incl']})
            pos_payments = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'pos.payment', 'search_read',
                                                        [[['pos_order_id', 'in', order_ids]]],
                                                        {'fields': ['pos_order_id', 'amount', 'payment_date', 'payment_method_id']})

            # Create dictionaries for quick lookup
            pos_order_lines_dict = {}
            for line in pos_order_lines:
                order_id = line['order_id'][0]
                if order_id not in pos_order_lines_dict:
                    pos_order_lines_dict[order_id] = []
                pos_order_lines_dict[order_id].append(line)

            pos_payments_dict = {}
            for payment in pos_payments:
                order_id = payment['pos_order_id'][0]
                if order_id not in pos_payments_dict:
                    pos_payments_dict[order_id] = []
                pos_payments_dict[order_id].append(payment)

            # Pre-fetch existing pos orders in target
            existing_pos_order_invoice_dict = {}
            for record in transaksi_posorder_invoice:
                existing_pos_order_invoice = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                        self.target_client.uid, self.target_client.password,
                                                                        'pos.order', 'search_read',
                                                                        [[['vit_trxid', '=', record.get('name')], ['vit_id', '=', record.get('id')]]],
                                                                        {'fields': ['id'], 'limit': 1})
                if existing_pos_order_invoice:
                    existing_pos_order_invoice_dict[record['id']] = existing_pos_order_invoice[0]['id']

            # Pre-fetch product and tax data
            product_ids = [line['product_id'][0] for line in pos_order_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'product_tmpl_id']})
            product_source_dict = {product['id']: product['product_tmpl_id'][0] for product in product_source}

            product_template_ids = list(product_source_dict.values())

            # Lakukan search_read pada product.template dengan id dari product_source_dict
            product_template_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'product.template', 'search_read',
                                                                [[['id', 'in', product_template_ids]]],
                                                                {'fields': ['id', 'id_mc', 'name', 'default_code']})

            # Membuat dictionary dengan key id dari product.template dan value id_mc
            product_template_dict = {product['id']: product['id_mc'] for product in product_template_source}
            default_code_dict = {product['id']: product['default_code'] for product in product_template_source}

            tax_ids = [tax_id for product in pos_order_lines for tax_id in product.get('tax_ids', [])]
            source_taxes = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'account.tax', 'search_read',
                                                        [[['id', 'in', tax_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            source_taxes_dict = {tax['id']: tax['id_mc'] for tax in source_taxes}

            # Pre-fetch payment methods
            payment_method_ids = [payment['payment_method_id'][0] for payment in pos_payments if payment.get('payment_method_id')]
            payment_method_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'pos.payment.method', 'search_read',
                                                                [[['id', 'in', payment_method_ids]]],
                                                                {'fields': ['id', 'id_mc', 'name']})
            payment_method_source_dict = {payment['id']: payment['id_mc'] for payment in payment_method_source}
            pos_order_ids = []
            # Function to process each record
            def process_record(record):
                # if record['id'] in existing_pos_order_invoice_dict:
                #     print(f"Pos order {record['id']} already exists in target system. Skipping.")
                #     return

                pos_order_invoice_lines = pos_order_lines_dict.get(record['id'], [])
                pos_order_invoice_line_ids = []
                pos_order_payment_ids = []
                missing_products = []

                # Check if all products exist in the target database
                for line in pos_order_invoice_lines:
                    product_id = product_template_dict.get(line.get('product_id')[0] if isinstance(line.get('product_id'), list) else line.get('product_id'))
                    default_code = default_code_dict.get(line.get('product_id')[0] if isinstance(line.get('product_id'), list) else line.get('product_id'), None)

                    if default_code is None:
                        print(f"Product {line.get('product_id')} is missing a default_code.")
                        continue

                    tax_ids_mc = [source_taxes_dict.get(tax_id) for tax_id in line.get('tax_ids', []) if tax_id in source_taxes_dict]

                    # First check if product exists in target system using id_mc
                    if product_id:
                        product_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'product.product', 'search_read',
                                                                    [[['product_tmpl_id', '=', product_id], ['active', 'in', [True, False]]]],
                                                                    {'fields': ['id', 'active'], 'limit': 1})
                        
                        if product_target:
                            if not product_target[0]['active']:
                                # If product exists but is archived, add to missing products
                                missing_products.append(default_code)
                                continue
                            product_id = product_target[0]['id']
                        else:
                            # If product doesn't exist by id_mc, try searching by default_code
                            product_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                        self.target_client.uid, self.target_client.password,
                                                                        'product.product', 'search_read',
                                                                        [[['default_code', '=', default_code], ['active', '=', True]]],
                                                                        {'fields': ['id'], 'limit': 1})
                            if product_target:
                                product_id = product_target[0]['id']
                            else:
                                missing_products.append(default_code)
                                continue

                    if missing_products:
                        missing_products_str = ", ".join(map(str, missing_products))
                        message = f"Terdapat produk tidak aktif dalam invoice: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'Invoice', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'Invoice', message, write_date)
                        return

                    pos_order_line_data = {
                        'product_id': int(product_id),
                        'name': line.get('full_product_name'),
                        'discount': line.get('discount'),
                        'full_product_name': line.get('full_product_name'),
                        'qty': line.get('qty'),
                        'price_unit': line.get('price_unit'),
                        'price_subtotal': line.get('price_subtotal'),
                        'price_subtotal_incl': line.get('price_subtotal_incl'),
                        'tax_ids': [(6, 0, tax_ids_mc)],
                    }
                    pos_order_invoice_line_ids.append((0, 0, pos_order_line_data))

                    # print(pos_order_invoice_line_ids)

                    if missing_products:
                        missing_products_str = ", ".join(map(str, missing_products))
                        message = f"Terdapat produk tidak aktif dalam invoice: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'Invoice', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'Invoice', message, write_date)
                        return

                # # # Fetch and process payments
                pos_order_payments = pos_payments_dict.get(record['id'], [])
                amount_paid = 0
                for payment in pos_order_payments:
                    amount_paid += payment.get('amount')
                    payment_method_id = payment_method_source_dict.get(payment.get('payment_method_id')[0] if isinstance(payment.get('payment_method_id'), list) else payment.get('payment_method_id'))
                    pos_order_payment_data = {
                        'amount': payment.get('amount'),
                        'payment_date': payment.get('payment_date'),
                        'payment_method_id': int(payment_method_id),
                    }
                    pos_order_payment_ids.append((0, 0, pos_order_payment_data))

                if not pos_order_payment_ids:
                    print(f"Tidak ada pembayaran untuk transaksi dengan ID {record.get('id')}. Tidak membuat dokumen.")
                    message_payment = f"Transaksi tidak memiliki metode pembayaran: {record.get('name')}."
                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_failed(record, 'Invoice', message_payment, write_date)
                    self.set_log_ss.create_log_note_failed(record, 'Invoice', message_payment, write_date)
                    return

                partner_id = partners_source_dict.get(record.get('partner_id')[0] if isinstance(record.get('partner_id'), list) else record.get('partner_id'))
                session_id = sessions_source_dict.get(record.get('session_id')[0] if isinstance(record.get('session_id'), list) else record.get('session_id'))
                employee_id = employees_source_dict.get(record.get('employee_id')[0] if isinstance(record.get('employee_id'), list) else record.get('employee_id'))
                pricelist_id = pricelist_source_dict.get(record.get('pricelist_id')[0] if isinstance(record.get('pricelist_id'), list) else record.get('pricelist_id'), [])

                print(partner_id, session_id, employee_id, pricelist_id)
                

                pos_order_data = {
                    'name': record.get('name'),
                    'pos_reference': record.get('pos_reference'),
                    'pricelist_id': int(pricelist_id) if pricelist_id is not [] else [],  # Set to None if pricelist_id is None
                    'vit_trxid': record.get('name'),
                    'vit_id': record.get('id'),
                    'partner_id': int(partner_id),
                    'session_id': int(session_id),
                    'employee_id': int(employee_id),
                    'date_order': record.get('date_order', False),
                    'amount_tax': record.get('amount_tax'),
                    'amount_total': amount_paid,
                    'amount_paid': amount_paid,
                    'amount_return': record.get('amount_return'),
                    'tracking_number': record.get('tracking_number'),
                    'margin': record.get('margin'),
                    'state': 'paid',
                    'is_integrated': True,
                    'lines': pos_order_invoice_line_ids,
                    'payment_ids': pos_order_payment_ids,
                }

                print(pos_order_data)

                try:
                    start_time = time.time()
                    new_pos_order_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'pos.order', 'create',
                                                                    [pos_order_data])

                    print(f"Pos Order baru telah dibuat dengan ID: {new_pos_order_id}")

                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'pos.order', 'write',
                        [[record['id']], {'is_integrated': True, 'id_mc': new_pos_order_id}]
                    )

                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Invoice', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Invoice', write_date)
                except Exception as e:
                    message_exception = f"Terjadi kesalahan saat membuat invoice: {e}"
                    self.set_log_mc.create_log_note_failed(record, 'Invoice', message_exception, write_date)
                    self.set_log_ss.create_log_note_failed(record, 'Invoice', message_exception, write_date)

            # Use ThreadPoolExecutor to process records in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_record, record) for record in transaksi_posorder_invoice]
                concurrent.futures.wait(futures)

        except Exception as e:
            print(f"Error during processing: {e}")

    def transfer_pos_order_invoice_session_closed(self, model_name, fields, description, date_from, date_to):
        try:
            # Fetching the data
            transaksi_posorder_invoice = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    model_name, 'search_read',
                                                                    [[['state', '=', 'invoiced'], ['is_integrated', '=', False], ['create_date', '>=', date_from], ['create_date', '<=', date_to]]],
                                                                    {'fields': fields})

            if not transaksi_posorder_invoice:
                print("Semua transaksi telah diproses.")
                return

            # Pre-fetch all necessary data
            partner_ids = [record.get('partner_id')[0] if isinstance(record.get('partner_id'), list) else record.get('partner_id') for record in transaksi_posorder_invoice]
            session_ids = [record.get('session_id')[0] if isinstance(record.get('session_id'), list) else record.get('session_id') for record in transaksi_posorder_invoice]
            employee_ids = [record.get('employee_id')[0] if isinstance(record.get('employee_id'), list) else record.get('employee_id') for record in transaksi_posorder_invoice]
            pricelist_id = [record.get('pricelist_id')[0] if isinstance(record.get('pricelist_id'), list) else record.get('pricelist_id') for record in transaksi_posorder_invoice]

            # Fetch partners
            partners_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'res.partner', 'search_read',
                                                        [[['id', 'in', partner_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            partners_source_dict = {partner['id']: partner['id_mc'] for partner in partners_source}

            # Fetch sessions
            sessions_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'pos.session', 'search_read',
                                                        [[['id', 'in', session_ids], ['state', '=', 'closed']]],
                                                        {'fields': ['id', 'id_mc']})
            sessions_source_dict = {session['id']: session['id_mc'] for session in sessions_source}

            # Fetch employees
            employees_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            'hr.employee', 'search_read',
                                                            [[['id', 'in', employee_ids]]],
                                                            {'fields': ['id', 'id_mc']})
            employees_source_dict = {employee['id']: employee['id_mc'] for employee in employees_source}

            # Fetch pricelist
            pricelist_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            'product.pricelist', 'search_read',
                                                            [[['id', 'in', pricelist_id]]],
                                                            {'fields': ['id', 'id_mc']})
            pricelist_source_dict = {pricelist['id']: pricelist['id_mc'] for pricelist in pricelist_source}

            # Pre-fetch all pos.order.line and pos.payment data
            order_ids = [record['id'] for record in transaksi_posorder_invoice]
            pos_order_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'pos.order.line', 'search_read',
                                                        [[['order_id', 'in', order_ids]]],
                                                        {'fields': ['order_id', 'product_id', 'full_product_name', 'qty', 'price_unit', 'tax_ids_after_fiscal_position', 'tax_ids', 'discount', 'price_subtotal', 'price_subtotal_incl']})
            pos_payments = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'pos.payment', 'search_read',
                                                        [[['pos_order_id', 'in', order_ids]]],
                                                        {'fields': ['pos_order_id', 'amount', 'payment_date', 'payment_method_id']})

            # Create dictionaries for quick lookup
            pos_order_lines_dict = {}
            for line in pos_order_lines:
                order_id = line['order_id'][0]
                if order_id not in pos_order_lines_dict:
                    pos_order_lines_dict[order_id] = []
                pos_order_lines_dict[order_id].append(line)

            pos_payments_dict = {}
            for payment in pos_payments:
                order_id = payment['pos_order_id'][0]
                if order_id not in pos_payments_dict:
                    pos_payments_dict[order_id] = []
                pos_payments_dict[order_id].append(payment)

            # Pre-fetch existing pos orders in target
            existing_pos_order_invoice_dict = {}
            for record in transaksi_posorder_invoice:
                existing_pos_order_invoice = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                        self.target_client.uid, self.target_client.password,
                                                                        'pos.order', 'search_read',
                                                                        [[['vit_trxid', '=', record.get('name')], ['vit_id', '=', record.get('id')]]],
                                                                        {'fields': ['id'], 'limit': 1})
                if existing_pos_order_invoice:
                    existing_pos_order_invoice_dict[record['id']] = existing_pos_order_invoice[0]['id']

            # Pre-fetch product and tax data
            product_ids = [line['product_id'][0] for line in pos_order_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'product_tmpl_id']})
            product_source_dict = {product['id']: product['product_tmpl_id'][0] for product in product_source}

            product_template_ids = list(product_source_dict.values())

            # Lakukan search_read pada product.template dengan id dari product_source_dict
            product_template_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'product.template', 'search_read',
                                                                [[['id', 'in', product_template_ids]]],
                                                                {'fields': ['id', 'id_mc', 'name', 'default_code']})

            # Membuat dictionary dengan key id dari product.template dan value id_mc
            product_template_dict = {product['id']: product['id_mc'] for product in product_template_source}
            default_code_dict = {product['id']: product['default_code'] for product in product_template_source}

            tax_ids = [tax_id for product in pos_order_lines for tax_id in product.get('tax_ids', [])]
            source_taxes = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'account.tax', 'search_read',
                                                        [[['id', 'in', tax_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            source_taxes_dict = {tax['id']: tax['id_mc'] for tax in source_taxes}

            # Pre-fetch payment methods
            payment_method_ids = [payment['payment_method_id'][0] for payment in pos_payments if payment.get('payment_method_id')]
            payment_method_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'pos.payment.method', 'search_read',
                                                                [[['id', 'in', payment_method_ids]]],
                                                                {'fields': ['id', 'id_mc', 'name']})
            payment_method_source_dict = {payment['id']: payment['id_mc'] for payment in payment_method_source}
            pos_order_ids = []
            # Function to process each record
            def process_record(record):
                if record['id'] in existing_pos_order_invoice_dict:
                    print(f"Pos order {record['id']} already exists in target system. Skipping.")
                    return

                pos_order_invoice_lines = pos_order_lines_dict.get(record['id'], [])
                pos_order_invoice_line_ids = []
                pos_order_payment_ids = []
                missing_products = []

                # Check if all products exist in the target database
                for line in pos_order_invoice_lines:
                    product_id = product_template_dict.get(line.get('product_id')[0] if isinstance(line.get('product_id'), list) else line.get('product_id'))
                    default_code = default_code_dict.get(line.get('product_id')[0] if isinstance(line.get('product_id'), list) else line.get('product_id'), None)

                    if default_code is None:
                        print(f"Product {line.get('product_id')} is missing a default_code.")
                        continue  # or handle the missing default_code in another way

                    tax_ids_mc = [source_taxes_dict.get(tax_id) for tax_id in line.get('tax_ids', []) if tax_id in source_taxes_dict]

                    if not product_id:
                        product_name = line.get('full_product_name')  # Assuming 'full_product_name' is the product's name
                        product_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'product.product', 'search_read',
                                                                    [[['name', '=', product_name], ['detailed_type', '=', 'service']]],
                                                                    {'fields': ['id'], 'limit': 1})

                        if product_target:
                            product_id = product_target[0]['id']

                    # Check if the product is active in the target system
                    product_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['default_code', '=', default_code], ['active', '=', True]]],
                                                                {'fields': ['id'], 'limit': 1})

                    if not product_target:
                        missing_products.append(default_code)
                        continue

                    pos_order_line_data = {
                        'product_id': int(product_id),
                        'discount': line.get('discount'),
                        'full_product_name': line.get('full_product_name'),
                        'qty': line.get('qty'),
                        'price_unit': line.get('price_unit'),
                        'price_subtotal': line.get('price_subtotal'),
                        'price_subtotal_incl': line.get('price_subtotal_incl'),
                        'tax_ids': [(6, 0, tax_ids_mc)],
                    }
                    pos_order_invoice_line_ids.append((0, 0, pos_order_line_data))

                    if missing_products:
                        missing_products_str = ", ".join(map(str, missing_products))
                        message = f"Terdapat produk tidak aktif dalam invoice: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'Invoice', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'Invoice', message, write_date)
                        return

                # # # Fetch and process payments
                pos_order_payments = pos_payments_dict.get(record['id'], [])
                amount_paid = 0
                for payment in pos_order_payments:
                    amount_paid += payment.get('amount')
                    payment_method_id = payment_method_source_dict.get(payment.get('payment_method_id')[0] if isinstance(payment.get('payment_method_id'), list) else payment.get('payment_method_id'))
                    pos_order_payment_data = {
                        'amount': payment.get('amount'),
                        'payment_date': payment.get('payment_date'),
                        'payment_method_id': int(payment_method_id),
                    }
                    pos_order_payment_ids.append((0, 0, pos_order_payment_data))

                if not pos_order_payment_ids:
                    print(f"Tidak ada pembayaran untuk transaksi dengan ID {record.get('id')}. Tidak membuat dokumen.")
                    message_payment = f"Transaksi tidak memiliki metode pembayaran: {record.get('name')}."
                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_failed(record, 'Invoice', message_payment, write_date)
                    self.set_log_ss.create_log_note_failed(record, 'Invoice', message_payment, write_date)
                    return

                partner_id = partners_source_dict.get(record.get('partner_id')[0] if isinstance(record.get('partner_id'), list) else record.get('partner_id'))
                session_id = sessions_source_dict.get(record.get('session_id')[0] if isinstance(record.get('session_id'), list) else record.get('session_id'))
                employee_id = employees_source_dict.get(record.get('employee_id')[0] if isinstance(record.get('employee_id'), list) else record.get('employee_id'))
                pricelist_id = pricelist_source_dict.get(record.get('pricelist_id')[0] if isinstance(record.get('pricelist_id'), list) else record.get('pricelist_id'), None)

                # print(partner_id, session_id, employee_id, pricelist_id)
                if partner_id is None or session_id is None or employee_id is None:
                    print(f"Data tidak lengkap untuk transaksi dengan ID {record.get('id')}. Tidak membuat dokumen.")
                    return

                pos_order_data = {
                    'name': record.get('name'),
                    'pos_reference': record.get('pos_reference'),
                    'pricelist_id': int(pricelist_id) if pricelist_id is not None else None,  # Set to None if pricelist_id is None
                    'vit_trxid': record.get('name'),
                    'vit_id': record.get('id'),
                    'partner_id': int(partner_id),
                    'session_id': int(session_id),
                    'employee_id': int(employee_id),
                    'date_order': record.get('date_order', False),
                    'amount_tax': record.get('amount_tax'),
                    'amount_total': amount_paid,
                    'amount_paid': amount_paid,
                    'amount_return': record.get('amount_return'),
                    'tracking_number': record.get('tracking_number'),
                    'margin': record.get('margin'),
                    'state': 'paid',
                    'is_integrated': True,
                    'lines': pos_order_invoice_line_ids,
                    'payment_ids': pos_order_payment_ids,
                }

                try:
                    start_time = time.time()
                    new_pos_order_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'pos.order', 'create',
                                                                    [pos_order_data])

                    print(f"Pos Order baru telah dibuat dengan ID: {new_pos_order_id}")

                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'pos.order', 'write',
                        [[record['id']], {'is_integrated': True, 'id_mc': new_pos_order_id}]
                    )

                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Invoice', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Invoice', write_date)
                except Exception as e:
                    message_exception = f"Terjadi kesalahan saat membuat invoice: {e}"
                    self.set_log_mc.create_log_note_failed(record, 'Invoice', message_exception, write_date)
                    self.set_log_ss.create_log_note_failed(record, 'Invoice', message_exception, write_date)

            # Use ThreadPoolExecutor to process records in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_record, record) for record in transaksi_posorder_invoice]
                concurrent.futures.wait(futures)

        except Exception as e:
            print(f"Error during processing: {e}")

    def transfer_pos_order_session(self, model_name, fields, description, date_from, date_to):
        try:
            # Ambil data dari sumber dengan offset dan limit
            transaksi_posorder_session = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    model_name, 'search_read',
                                                                    [[['is_updated', '=', False]]],
                                                                    {'fields': fields})

            if not transaksi_posorder_session:
                print("Semua transaksi telah diproses.")
                return

            # Pre-fetch all necessary data
            config_ids = [record.get('config_id')[0] if isinstance(record.get('config_id'), list) else record.get('config_id') for record in transaksi_posorder_session]
            user_ids = [record.get('user_id')[0] if isinstance(record.get('user_id'), list) else record.get('user_id') for record in transaksi_posorder_session]

            # Fetch pos.config
            config_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'pos.config', 'search_read',
                                                        [[['id', 'in', config_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            config_source_dict = {config['id']: config['id_mc'] for config in config_source}

            # Fetch res.users
            user_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'res.users', 'search_read',
                                                        [[['id', 'in', user_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            user_source_dict = {user['id']: user['id_mc'] for user in user_source}

            # Pre-fetch existing pos sessions in target
            existing_pos_order_session_dict = {}
            for record in transaksi_posorder_session:
                existing_pos_order_session = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                        self.target_client.uid, self.target_client.password,
                                                                        'pos.session', 'search_read',
                                                                        [[['name_session_pos', '=', record.get('name')]]],
                                                                        {'fields': ['id'], 'limit': 1})
                if existing_pos_order_session:
                    existing_pos_order_session_dict[record['id']] = existing_pos_order_session[0]['id']

            def process_record(record):
                if record['id'] in existing_pos_order_session_dict:
                    return

                cash_register_balance_start = record.get('cash_register_balance_start')
                cash_register_balance_end_real = record.get('cash_register_balance_end_real')

                # Debugging prints
                print(f"Cash Register Balance Start: {cash_register_balance_start}")
                print(f"Cash Register Balance End Real: {cash_register_balance_end_real}")

                # Ensure monetary values are properly handled
                cash_register_balance_start = float(cash_register_balance_start) if cash_register_balance_start else 0.0
                cash_register_balance_end_real = float(cash_register_balance_end_real) if cash_register_balance_end_real else 0.0

                config_id = config_source_dict.get(record.get('config_id')[0] if isinstance(record.get('config_id'), list) else record.get('config_id'))
                user_id = user_source_dict.get(record.get('user_id')[0] if isinstance(record.get('user_id'), list) else record.get('user_id'))

                if config_id is None or user_id is None:
                    print(f"Data tidak lengkap untuk transaksi dengan ID {record.get('id')}. Tidak membuat dokumen.")
                    return

                pos_session_data = {
                    'name_session_pos': record.get('name'),
                    'config_id': int(config_id),
                    'user_id': 2,
                    'start_at': record.get('start_at'),
                    'stop_at': record.get('stop_at'),
                    'cash_register_balance_start': cash_register_balance_start,
                    'cash_register_balance_end_real': cash_register_balance_end_real,
                    'state': record.get('state'),
                }

                try:
                    start_time = time.time()
                    new_session_pos_order_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                            self.target_client.uid, self.target_client.password,
                                                                            'pos.session', 'create',
                                                                            [pos_session_data])
                    print(f"Pos Order Session baru telah dibuat dengan ID: {new_session_pos_order_id}")
                    
                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'pos.session', 'write',
                        [[record['id']], {'id_mc': new_session_pos_order_id}]
                    )
                    
                    end_time = time.time()
                    duration = end_time - start_time

                    # write_date = self.get_write_date(model_name, record['id'])
                    # self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'POS Session', write_date)
                    # self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'POS Session', write_date)

                except Exception as e:
                    message_exception = f"Terjadi kesalahan saat membuat pos order baru: {e}"
                    # self.set_log_mc.create_log_note_failed(record, 'POS Session', message_exception, write_date)
                    # self.set_log_ss.create_log_note_failed(record, 'POS Session', message_exception, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_record, record) for record in transaksi_posorder_session]
                concurrent.futures.wait(futures)

        except Exception as e:
            print(f"Terjadi kesalahan saat memproses batch: {e}")
            return

    def transfer_warehouse_master(self, model_name, fields, description, date_from, date_to):
        # Ambil data dari sumber
        transaksi_warehouse = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        model_name, 'search_read',
                                                        [[]],
                                                        {'fields': fields})
        
        # print(transaksi_warehouse)

        if not transaksi_warehouse:
            print("Tidak ada master yang ditemukan untuk ditransfer.")
            return
        
        location_transit_ids = [record.get('location_transit')[0] if isinstance(record.get('location_transit'), list) else record.get('location_transit') for record in transaksi_warehouse]
        # print(location_ids)

        location_transit = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        'stock.location', 'search_read',
                                                        [[['id', 'in', location_transit_ids]]],
                                                        {'fields': ['id', 'complete_name']})
        
        location_transit_name_dict = {record['id']: record['complete_name'] for record in location_transit}
        location_transit_id_dict = {record['id']: record['id'] for record in location_transit}
        
        lot_stock_ids = [record.get('lot_stock_id')[0] if isinstance(record.get('lot_stock_id'), list) else record.get('lot_stock_id') for record in transaksi_warehouse]
        lot_stock_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        'stock.location', 'search_read',
                                                        [[['id', 'in', lot_stock_ids]]],
                                                        {'fields': ['id','complete_name']})
        
        lot_stock_source_dict = {record['id']: record['complete_name'] for record in lot_stock_source}
        lot_stock_id_dict = {record['id']: record['id'] for record in lot_stock_source}

        # # Kirim data ke target
        for record in transaksi_warehouse:
            warehouse_name = record.get('name', False)
            warehouse_code = record.get('complete_name', False)
            
            existing_master_warehouse = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                            self.source_client.uid, self.source_client.password,
                                                                            'master.warehouse', 'search_read',
                                                                            [[['warehouse_name', '=', warehouse_name]]],
                                                                            {'fields': ['id'], 'limit': 1})
            if not existing_master_warehouse:
                existing_warehouse = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                                self.source_client.uid, self.source_client.password,
                                                                                'stock.warehouse', 'search_read',
                                                                                [[['name', '=', warehouse_name]]],
                                                                                {'fields': ['id'], 'limit': 1})
                if existing_warehouse:
                    print(f"Warehouse dengan nama {warehouse_name} sudah ada di master.warehouse.")
                    continue

                location_id = location_transit_name_dict.get(record.get('location_transit')[0] if isinstance(record.get('location_transit'), list) else record.get('location_transit'), False)
                lot_transit = location_transit_id_dict.get(record.get('location_transit')[0] if isinstance(record.get('location_transit'), list) else record.get('location_transit'), False)
                lot_stock_id = lot_stock_source_dict.get(record.get('lot_stock_id')[0] if isinstance(record.get('lot_stock_id'), list) else record.get('lot_stock_id'), False)
                lot_id = lot_stock_id_dict.get(record.get('lot_stock_id')[0] if isinstance(record.get('lot_stock_id'), list) else record.get('lot_stock_id'), False)

                warehouse_data = {
                    'warehouse_name': warehouse_name,
                    'warehouse_code': str(lot_stock_id),
                    'warehouse_transit': str(location_id),
                    'id_mc_location': str(lot_id),
                    'id_mc_transit': str(lot_transit),
                    # 'warehouse_company': [(6, 0, [1])]  # Many2many relation expects a list of IDs
                }
                try:
                    start_time = time.time()
                    new_master_warehouse = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'master.warehouse', 'create',
                                                                        [warehouse_data])
                    print(f"Warehouse baru telah dibuat dengan ID: {new_master_warehouse}")

                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Warehouse UDT', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Warehouse UDT', write_date)
                except Exception as e:
                    message_exception = f"An error occurred while creating warehouse: {e}"
                    self.set_log_mc.create_log_note_failed(record, 'Warehouse UDT', message_exception, write_date)
                    self.set_log_ss.create_log_note_failed(record, 'Warehouse UDT', message_exception, write_date)

    def transfer_TSOUT_NEW(self, model_name, fields, description, date_from, date_to):
        try:
            # Ambil data dari sumber
            Ts_Out_data_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            model_name, 'search_read',
                                                            [[['picking_type_id.name', '=', 'TS Out'], ['is_integrated', '=', False], ['state', '=', 'done'], ['create_date', '>=', date_from], ['create_date', '<=', date_to]]],
                                                            {'fields': fields})

            if not Ts_Out_data_source:
                print("Semua transaksi telah diproses.")
                return

            target_location_ids = [record.get('target_location')[0] if isinstance(record.get('target_location'), list) else record.get('target_location') for record in Ts_Out_data_source]
            location_ids = [record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id') for record in Ts_Out_data_source]
            picking_type_ids = [record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id') for record in Ts_Out_data_source]

            target_location_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'master.warehouse', 'search_read',
                                                                [[['id', 'in', target_location_ids]]],
                                                                {'fields': ['id', 'id_mc_location', 'id_mc_transit', 'warehouse_name', 'warehouse_code', 'warehouse_transit'], 'limit': 1})
            target_location_source_dict = {target['id']: target['id_mc_location'] for target in target_location_source}
            transit_location_id_dict = {target['id']: target['id_mc_transit'] for target in target_location_source}
            target_location_name_dict = {target['id']: target['warehouse_name'] for target in target_location_source}
            
            location_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'stock.location', 'search_read',
                                                        [[['id', 'in', location_ids]]],
                                                        {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_source_dict = {location['id']: location['id_mc'] for location in location_source}

            picking_type_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            'stock.picking.type', 'search_read',
                                                            [[['id', 'in', picking_type_ids]]],
                                                            {'fields': ['id', 'id_mc'] , 'limit': 1})
            picking_type_source_dict = {type['id']: type['id_mc'] for type in picking_type_source}

            picking_ids = [record['id'] for record in Ts_Out_data_source]
            tsout_transfer_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'stock.move', 'search_read',
                                                                        [[['picking_id', 'in', picking_ids]]],
                                                                        {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

            existing_ts_out_invoice_dict = {}
            for record in Ts_Out_data_source:
                existing_ts_out = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'stock.picking', 'search_read',
                                                            [[['vit_trxid', '=', record.get('name')]]],
                                                            {'fields': ['id'], 'limit': 1})
                if existing_ts_out:
                    existing_ts_out_invoice_dict[record['id']] = existing_ts_out[0]['id']

            tsout_transfer_inventory_lines_dict = {}
            for line in tsout_transfer_inventory_lines:
                if 'picking_id' in line:
                    picking_id = line['picking_id'][0]
                    if picking_id not in tsout_transfer_inventory_lines_dict:
                        tsout_transfer_inventory_lines_dict[picking_id] = []
                    tsout_transfer_inventory_lines_dict[picking_id].append(line)

            product_ids = [line['product_id'][0] for line in tsout_transfer_inventory_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'product_tmpl_id']})
            product_source_dict = {product['id']: product['product_tmpl_id'][0] for product in product_source}

            product_template_ids = list(product_source_dict.values())

            # Lakukan search_read pada product.template dengan id dari product_source_dict
            product_template_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'product.template', 'search_read',
                                                                [[['id', 'in', product_template_ids]]],
                                                                {'fields': ['id', 'id_mc', 'name', 'default_code']})

            # Membuat dictionary dengan key id dari product.template dan value id_mc
            product_template_dict = {product['id']: product['id_mc'] for product in product_template_source}

            def process_record(record):
                try:
                    if record['id'] in existing_ts_out_invoice_dict:
                        return
                
                    tsout_transfer_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                                self.source_client.uid, self.source_client.password,
                                                                                'stock.move', 'search_read',
                                                                                [[['picking_id', '=', record['id']]]],
                                                                                {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

                    location_id = location_source_dict.get(record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id'))
                    target_location = target_location_source_dict.get(record.get('target_location')[0] if isinstance(record.get('target_location'), list) else record.get('target_location'))
                    target_location_name = target_location_name_dict.get(record.get('target_location')[0] if isinstance(record.get('target_location'), list) else record.get('target_location'))
                    picking_type_id = picking_type_source_dict.get(record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id'))
                    transit_location_id = transit_location_id_dict.get(record.get('target_location')[0] if isinstance(record.get('target_location'), list) else record.get('target_location'))

                    if not location_id or not target_location or not picking_type_id or not transit_location_id:
                        print(f"Missing required data for record ID {record['id']}. Skipping.")
                        return

                    missing_products = []
                    tsout_transfer_inventory_line_ids = []
                    tsin_transfer_inventory_line_ids = []
                    for line in tsout_transfer_inventory_lines:
                        product_id = product_template_dict.get(line.get('product_id')[0] if isinstance(line.get('product_id'), list) else line.get('product_id'))

                        # Check if the product is active in the target system
                        product_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'product.product', 'search_read',
                                                                    [[['id', '=', product_id], ['active', '=', True]]],
                                                                    {'fields': ['id'], 'limit': 1})

                        if not product_target:
                            missing_products.append(product_id)
                            continue

                        tsout_transfer_inventory_line_data = {
                            'product_id': int(product_id),
                            'product_uom_qty': line.get('product_uom_qty'),
                            'name': line.get('name'),
                            'quantity': line.get('quantity'),
                            'location_dest_id': int(transit_location_id),
                            'location_id': int(location_id)
                        }
                        tsout_transfer_inventory_line_ids.append((0, 0, tsout_transfer_inventory_line_data))

                        tsin_transfer_inventory_line_data = {
                            'product_id': int(product_id),
                            'product_uom_qty': line.get('product_uom_qty'),
                            'name': line.get('name'),
                            'quantity': line.get('quantity'),
                            'location_dest_id': int(target_location),
                            'location_id': int(transit_location_id),
                        }
                        tsin_transfer_inventory_line_ids.append((0, 0, tsin_transfer_inventory_line_data))

                    if missing_products:
                        missing_products_str = ", ".join(missing_products)
                        message = f"Terdapat produk tidak aktif dalam TS Out/TS In: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'TS Out/TS In', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'TS Out/TS In', message, write_date)
                        return

                    tsout_transfer_data = {
                        'scheduled_date': record.get('scheduled_date', False),
                        'date_done': record.get('date_done', False),
                        'location_id': int(location_id),
                        'location_dest_id': int(transit_location_id),
                        'target_location': target_location_name,
                        'picking_type_id': int(picking_type_id),
                        'is_integrated': True,
                        'vit_trxid': record.get('name', False),
                        'move_ids_without_package': tsout_transfer_inventory_line_ids,
                    }

                    new_tsout_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.picking', 'create',
                                                                [tsout_transfer_data])
                    print(f"TS Out baru telah dibuat di target dengan ID: {new_tsout_id}")

                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'stock.picking', 'write',
                        [[record['id']], {'is_integrated': True, 'vit_trxid': record['name']}]
                    )

                    picking_type_name_ts_in = 'TS In'
                    picking_types_ts_in = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking.type', 'search_read',
                                                                    [[['name', '=', picking_type_name_ts_in]]],
                                                                    {'fields': ['id'], 'limit': 1})

                    if not picking_types_ts_in:
                        print(f"Tidak dapat menemukan tipe picking dengan nama '{picking_type_name_ts_in}' di database target.")
                        return

                    picking_type_id_ts_in = picking_types_ts_in[0]['id']

                    ts_in_transfer_data = {
                        'scheduled_date': record.get('scheduled_date', False),
                        'date_done': record.get('date_done', False),
                        'location_id': int(transit_location_id),
                        'location_dest_id': int(target_location),
                        'origin': record.get('name', False),
                        'picking_type_id': picking_type_id_ts_in,
                        'move_ids_without_package': tsin_transfer_inventory_line_ids,
                    }

                    # print(ts_in_transfer_data)
                    start_time = time.time()
                    new_ts_in_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.picking', 'create',
                                                                [ts_in_transfer_data])
                    print(f"TS In baru telah dibuat di target dengan ID: {new_ts_in_id}")

                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'TS Out/TS In', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'TS Out/TS In', write_date)
                except Exception as e:
                    message_exception = f"Gagal membuat atau memposting TS In di Source baru: {e}"
                    self.set_log_mc.create_log_note_failed(record, 'TS Out/TS In', message_exception, write_date)
                    self.set_log_ss.create_log_note_failed(record, 'TS Out/TS In', message_exception, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_record, record) for record in Ts_Out_data_source]
                concurrent.futures.wait(futures)
        except Exception as e:
            print(f"Gagal membuat atau memposting TS Out di Source baru: {e}")

    def validate_goods_receipts_mc(self, model_name, fields, description):
        # Retrieve TS Out records that match the specified criteria from the source database
        goods_receipts_validates = self.source_client.call_odoo(
            'object', 'execute_kw', 
            self.source_client.db, self.source_client.uid, self.source_client.password,
            'stock.picking', 'search_read',
            [[
                ['picking_type_id.name', '=', 'Goods Receipts'], 
                ['is_integrated', '=', True], 
                ['state', '=', 'assigned'],
            ]],
            {'fields': ['id', 'name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'move_ids_without_package']}
        )

        # Check if any TS Out records are found
        if not goods_receipts_validates:
            print("Tidak ada Goods Receipts yang ditemukan di source.")
            return  # Exit if no records found

        # Process only the first 100 records
        for gr in goods_receipts_validates:
            try:
                start_time = time.time()
                self.source_client.call_odoo(
                    'object', 'execute_kw',
                    self.source_client.db, self.source_client.uid, self.source_client.password,
                    'stock.picking', 'button_validate',
                    [gr['id']]
                )
                print(f"Goods Receipts with ID {gr['id']} has been validated.")
                end_time = time.time()
                duration = end_time - start_time

                write_date = self.get_write_date(model_name, gr['id'])
                self.set_log_mc.create_log_note_success(gr, start_time, end_time, duration, 'Goods Receipts', write_date)
                self.set_log_ss.create_log_note_success(gr, start_time, end_time, duration, 'Goods Receipts', write_date)
            except Exception as e:
                message_exception = f"Failed to validate Goods Receipts with ID {gr['id']}: {e}"
                self.set_log_mc.create_log_note_failed(gr, 'Goods Receipts', message_exception, write_date)
                self.set_log_ss.create_log_note_failed(gr, 'Goods Receipts', message_exception, write_date)

    def validate_goods_receipts_store(self, model_name, fields, description, date_from, date_to):
        # Retrieve TS Out records that match the specified criteria from the source database
        goods_receipts_validates = self.source_client.call_odoo(
            'object', 'execute_kw', 
            self.source_client.db, self.source_client.uid, self.source_client.password,
            'stock.picking', 'search_read',
            [[
                ['picking_type_id.name', '=', 'Goods Receipts'], 
                ['is_integrated', '=', True], 
                ['state', '=', 'assigned'],
            ]],
            {'fields': ['id', 'name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'move_ids_without_package']}
        )

        # Check if any TS Out records are found
        if not goods_receipts_validates:
            print("Tidak ada Goods Receipts yang ditemukan di source.")
        else:
            # Process in batches of 100
            for i in range(0, len(goods_receipts_validates), 100):
                batch = goods_receipts_validates[i:i + 100]
                for gr in batch:
                    try:
                        start_time = time.time()
                        self.source_client.call_odoo(
                            'object', 'execute_kw',
                            self.source_client.db, self.source_client.uid, self.source_client.password,
                            'stock.picking', 'button_validate',
                            [gr['id']]
                        )
                        print(f"Goods Receipts with ID {gr['id']} has been validated.")
                        end_time = time.time()
                        duration = end_time - start_time

                        write_date = self.get_write_date(model_name, gr['id'])
                        self.set_log_mc.create_log_note_success(gr, start_time, end_time, duration, 'Goods Receipts', write_date)
                        self.set_log_ss.create_log_note_success(gr, start_time, end_time, duration, 'Goods Receipts', write_date)
                    except Exception as e:
                        message_exception = f"Failed to validate Goods Receipts with ID {gr['id']}: {e}"
                        self.set_log_mc.create_log_note_failed(gr, 'Goods Receipts', message_exception, write_date)
                        self.set_log_ss.create_log_note_failed(gr, 'Goods Receipts', message_exception, write_date)

    def validate_goods_issue_store(self, model_name, fields, description, date_from, date_to):
        # Retrieve TS Out records that match the specified criteria from the source database
        goods_issue_validates = self.source_client.call_odoo(
            'object', 'execute_kw', 
            self.source_client.db, self.source_client.uid, self.source_client.password,
            'stock.picking', 'search_read',
            [[
                ['picking_type_id.name', '=', 'Goods Issue'], 
                ['is_integrated', '=', True], 
                ['state', '=', 'assigned'],
            ]],
            {'fields': ['id', 'name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'move_ids_without_package']}
        )

        # Check if any TS Out records are found
        if not goods_issue_validates:
            print("Tidak ada Goods Issue yang ditemukan di source.")
        else:
            # Process in batches of 100
            for i in range(0, len(goods_issue_validates), 100):
                batch = goods_issue_validates[i:i + 100]
                for gi in batch:
                    try:
                        start_time = time.time()
                        self.source_client.call_odoo(
                            'object', 'execute_kw',
                            self.source_client.db, self.source_client.uid, self.source_client.password,
                            'stock.picking', 'button_validate',
                            [gi['id']]
                        )
                        print(f"Goods Issue with ID {gi['id']} has been validated.")
                        end_time = time.time()
                        duration = end_time - start_time

                        write_date = self.get_write_date(model_name, gi['id'])
                        self.set_log_mc.create_log_note_success(gi, start_time, end_time, duration, 'Goods Issue', write_date)
                        self.set_log_ss.create_log_note_success(gi, start_time, end_time, duration, 'Goods Issue', write_date)
                    except Exception as e:
                        message_exception = f"Failed to validate Goods Issue with ID {gi['id']}: {e}"
                        self.set_log_mc.create_log_note_failed(gi, 'Goods Issue', message_exception, write_date)
                        self.set_log_ss.create_log_note_failed(gi, 'Goods Issue', message_exception, write_date)

    def validate_GRPO(self, model_name, fields, description, date_from, date_to):
        # Retrieve GRPO records that match the specified criteria from the source database
        GRPO_validates = self.source_client.call_odoo(
            'object', 'execute_kw', 
            self.source_client.db, self.source_client.uid, self.source_client.password,
            'stock.picking', 'search_read',
            [[
                ['picking_type_id.name', '=', 'GRPO'], 
                ['is_integrated', '=', True], 
                ['is_updated', '=', False],
                ['write_date', '>=', date_from], ['write_date', '<=', date_to],
                ['state', '=', 'done'],
            ]],
            {'fields': ['id', 'name', 'move_ids_without_package', 'vit_trxid']}
        )

        # Check if any GRPO records are found
        if not GRPO_validates:
            print("Tidak ada GRPO yang ditemukan di target.")
            return

        # Collect all move_ids and vit_trxids
        all_source_move_ids = []
        all_vit_trxids = []
        for res in GRPO_validates:
            all_source_move_ids.extend(res['move_ids_without_package'])
            all_vit_trxids.append(res.get('vit_trxid', False))

        # Fetch all source move lines in one call
        source_move_lines = self.source_client.call_odoo(
            'object', 'execute_kw',
            self.source_client.db, self.source_client.uid, self.source_client.password,
            'stock.move', 'read',
            [all_source_move_ids],
            {'fields': ['id', 'product_id', 'quantity']}
        )

        # Fetch all source product codes in one call
        source_product_ids = list(set([move['product_id'][0] for move in source_move_lines]))
        source_products = self.source_client.call_odoo(
            'object', 'execute_kw',
            self.source_client.db, self.source_client.uid, self.source_client.password,
            'product.product', 'search_read',
            [[('id', 'in', source_product_ids)]],
            {'fields': ['id', 'default_code']}
        )
        source_product_dict = {product['id']: product['default_code'] for product in source_products}

        # Fetch all target GRPO records that need validation
        GRPO_needs_validate = self.target_client.call_odoo(
            'object', 'execute_kw', 
            self.target_client.db, self.target_client.uid, self.target_client.password,
            'stock.picking', 'search_read',
            [[
                ['picking_type_id.name', '=', 'GRPO'], 
                ['vit_trxid', 'in', all_vit_trxids], 
                ['is_integrated', '=', False], 
                ['state', '=', 'assigned']
            ]],
            {'fields': ['id', 'move_ids_without_package', 'vit_trxid']}
        )

        # Create a dictionary to map vit_trxid to target GRPO records
        target_grpo_dict = {grpo['vit_trxid']: grpo for grpo in GRPO_needs_validate}

        for res in GRPO_validates:
            vit_trxid = res.get('vit_trxid', False)
            target_grpo = target_grpo_dict.get(vit_trxid)

            if not target_grpo:
                continue

            try:
                # Get source move lines for this GRPO
                grpo_source_move_lines = [move for move in source_move_lines if move['id'] in res['move_ids_without_package']]
                
                # Get source product codes and quantities
                source_product_info = {
                    source_product_dict.get(move['product_id'][0]): {
                        'product_id': move['product_id'][0],
                        'quantity': move['quantity']
                    }
                    for move in grpo_source_move_lines
                }
                source_codes_set = set(source_product_info.keys())

                # Get target move_ids
                target_move_ids = target_grpo['move_ids_without_package']

                # Fetch all target move lines in one call
                target_move_lines = self.target_client.call_odoo(
                    'object', 'execute_kw',
                    self.target_client.db, self.target_client.uid, self.target_client.password,
                    'stock.move', 'read',
                    [target_move_ids],
                    {'fields': ['id', 'product_id', 'quantity']}
                )

                # Fetch all target product codes in one call
                target_product_ids = [move['product_id'][0] for move in target_move_lines]
                target_products = self.target_client.call_odoo(
                    'object', 'execute_kw',
                    self.target_client.db, self.target_client.uid, self.target_client.password,
                    'product.product', 'search_read',
                    [[('id', 'in', target_product_ids)]],
                    {'fields': ['id', 'default_code']}
                )
                target_product_dict = {product['id']: product['default_code'] for product in target_products}

                moves_to_remove = []
                moves_to_update = []

                for target_move in target_move_lines:
                    target_product_id = target_move['product_id'][0]
                    target_product_code = target_product_dict.get(target_product_id)
                    
                    if target_product_code not in source_codes_set:
                        moves_to_remove.append(target_move['id'])
                    else:
                        source_quantity = source_product_info[target_product_code]['quantity']
                        target_quantity = target_move['quantity']
                        
                        if source_quantity != target_quantity:
                            moves_to_update.append((1, target_move['id'], {
                                'quantity': source_quantity
                            }))

                if moves_to_remove:
                    # Delete the target move lines for products that no longer exist in source
                    self.target_client.call_odoo(
                        'object', 'execute_kw',
                        self.target_client.db, self.target_client.uid, self.target_client.password,
                        'stock.move', 'unlink',
                        [moves_to_remove]
                    )
                    print(f"Deleted {len(moves_to_remove)} products from target_client for GRPO {target_grpo['id']}")

                if moves_to_update:
                    # Update the quantities of the target move lines
                    self.target_client.call_odoo(
                        'object', 'execute_kw',
                        self.target_client.db, self.target_client.uid, self.target_client.password,
                        'stock.picking', 'write',
                        [[target_grpo['id']], {'move_ids_without_package': moves_to_update}]
                    )
                    print(f"Updated quantities for {len(moves_to_update)} products in target_client for GRPO {target_grpo['id']}")

            
                self.target_client.call_odoo(
                    'object', 'execute_kw',
                    self.target_client.db, self.target_client.uid, self.target_client.password,
                    'stock.picking', 'write',
                    [[target_grpo['id']], {'is_integrated': True, 'is_closed': True}]
                )

                self.target_client.call_odoo(
                    'object', 'execute_kw',
                    self.target_client.db, self.target_client.uid, self.target_client.password,
                    'stock.picking', 'button_validate',
                    [[target_grpo['id']]]
                )
                print(f"Validated GRPO {target_grpo['id']} in target_client.")

                # Mark the GRPO as updated in the source system
                self.source_client.call_odoo(
                    'object', 'execute_kw',
                    self.source_client.db, self.source_client.uid, self.source_client.password,
                    'stock.picking', 'write',
                    [[res['id']], {'is_updated': True}]
                )

                message_success = f"Successfully validated and updated GRPO {target_grpo['id']}"
                self.set_log_mc.create_log_note_success(res, 'GRPO', message_success, write_date)
                self.set_log_ss.create_log_note_success(res, 'GRPO', message_success, write_date)
                write_date = self.get_write_date(model_name, res['id'])

            except Exception as e:
                message_exception = f"Failed to validate and update GRPO {target_grpo['id']}: {e}"
                # self.set_log_mc.create_log_note_failed(res, 'GRPO', message_exception, write_date)
                # self.set_log_ss.create_log_note_failed(res, 'GRPO', message_exception, write_date)

        print("GRPO validation and quantity update completed.")

    def transfer_internal_transfers(self, model_name, fields, description, date_from, date_to):
        try:
            # Ambil data dari sumber
            transaksi_internal_transfers = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            model_name, 'search_read',
                                                            [[['picking_type_id.name', '=', 'Internal Transfers'], ['is_integrated', '=', False], ['state', '=', 'done'], ['create_date', '>=', date_from], ['create_date', '<=', date_to]]],
                                                            {'fields': fields})

            if not transaksi_internal_transfers:
                print("Semua transaksi telah diproses.")
                return
            
            location_ids = [record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id') for record in transaksi_internal_transfers]
            location_dest_id = [record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id') for record in transaksi_internal_transfers]
            picking_type_ids = [record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id') for record in transaksi_internal_transfers]

            location_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id', 'in', location_ids]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_source_dict = {location['id']: location['id_mc'] for location in location_source}

            location_dest_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id', 'in', location_dest_id]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_dest_source_dict = {location_dest['id']: location_dest['id_mc'] for location_dest in location_dest_source}

            picking_type_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    'stock.picking.type', 'search_read',
                                                                    [[['id', 'in', picking_type_ids]]],
                                                                    {'fields': ['id', 'id_mc'] , 'limit': 1})
            picking_type_source_dict = {type['id']: type['id_mc'] for type in picking_type_source}

            picking_ids = [record['id'] for record in transaksi_internal_transfers]
            internal_transfer_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'stock.move', 'search_read',
                                                                        [[['picking_id', 'in', picking_ids]]],
                                                                        {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

            existing_internal_transfer_dict = {}
            for record in transaksi_internal_transfers:
                existing_it = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'stock.picking', 'search_read',
                                                            [[['vit_trxid', '=', record.get('name')]]],
                                                            {'fields': ['id'], 'limit': 1})
                if existing_it:
                    existing_internal_transfer_dict[record['id']] = existing_it[0]['id']

            internal_transfer_lines_dict = {}
            for line in internal_transfer_inventory_lines:
                if 'picking_id' in line:
                    picking_id = line['picking_id'][0]
                    if picking_id not in internal_transfer_lines_dict:
                        internal_transfer_lines_dict[picking_id] = []
                    internal_transfer_lines_dict[picking_id].append(line)

            product_ids = [line['product_id'][0] for line in internal_transfer_inventory_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'product_tmpl_id']})
            product_source_dict = {product['id']: product['product_tmpl_id'][0] for product in product_source}

            product_template_ids = list(product_source_dict.values())

            # Lakukan search_read pada product.template dengan id dari product_source_dict
            product_template_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'product.template', 'search_read',
                                                                [[['id', 'in', product_template_ids]]],
                                                                {'fields': ['id', 'id_mc', 'name', 'default_code']})

            # Membuat dictionary dengan key id dari product.template dan value id_mc
            product_template_dict = {product['id']: product['id_mc'] for product in product_template_source}
            
            new_internal_transfer_ids = []
            def proces_internal_transfer_record(record):
                if record['id'] in existing_internal_transfer_dict:
                    return
                
                internal_transfer_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'stock.move', 'search_read',
                                                                        [[['picking_id', '=', record['id']]]],
                                                                        {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})
                
                location_id = location_source_dict.get(record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id'))
                location_dest_id = location_dest_source_dict.get(record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id'))
                picking_type_id = picking_type_source_dict.get(record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id'))
                
                if location_id is None or location_dest_id is None or picking_type_id is None:
                    print(f"Data tidak lengkap untuk transaksi dengan ID {record.get('id')}. Tidak membuat dokumen.")
                    return
                
                internal_transfers_inventory_line_ids = []
                missing_products = []
                for line in internal_transfer_inventory_lines:
                    product_id = product_source_dict.get(line.get('product_id')[0] if isinstance(line.get('product_id'), list) else line.get('product_id'))

                    # Check if the product is active in the target system
                    product_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['id', '=', product_id], ['active', '=', True]]],
                                                                {'fields': ['id'], 'limit': 1})

                    if not product_target:
                        missing_products.append(product_id)
                        continue

                    internal_transfers_inventory_line_data = {
                        'product_id': int(product_id),
                        'product_uom_qty': line.get('product_uom_qty'),
                        'name': line.get('name'),
                        'quantity': line.get('quantity'),
                        'location_dest_id': int(location_dest_id),
                        'location_id': int(location_id),
                    }
                    internal_transfers_inventory_line_ids.append((0, 0, internal_transfers_inventory_line_data))

                    if missing_products:
                        missing_products_str = ", ".join(missing_products)
                        message = f"Terdapat produk tidak aktif dalam Internal Transfers: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'Internal Transfers', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'Internal Transfers', message, write_date)

                internal_transfer_data = {
                    # 'name': record.get('name', False) + ' - ' + datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%Y-%m-%d %H:%M:%S"),
                    # 'partner_id': customer_target_id,
                    'scheduled_date': record.get('scheduled_date', False),
                    'date_done': record.get('date_done', False),
                    'vit_trxid': record.get('name', False),
                    'is_integrated': True,
                    'location_id': int(location_id) if location_id else location_id,
                    'location_dest_id': int(location_dest_id) if location_dest_id else location_dest_id,
                    'picking_type_id': int(picking_type_id) if picking_type_id else picking_type_id,
                    'move_ids_without_package': internal_transfers_inventory_line_ids,
                }

                try:
                    new_internal_transfers = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking', 'create',
                                                                    [internal_transfer_data])
                    print(f"Internal Transfers baru telah dibuat dengan ID: {new_internal_transfers}")

                    start_time = time.time()
                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'stock.picking', 'write',
                        [[record['id']], {'is_integrated': True, 'vit_trxid': record['name']}]
                    )
                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Internal Transfers', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Internal Transfers', write_date)
                except Exception as e:
                    message_exception = f"Gagal membuat atau memposting Goods Receipt baru: {e}"
                    self.set_log_mc.create_log_note_failed(record, 'Internal Transfers', message_exception, write_date)    
                    self.set_log_ss.create_log_note_failed(record, 'Internal Transfers', message_exception, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(proces_internal_transfer_record, record) for record in transaksi_internal_transfers]
                concurrent.futures.wait(futures)
        except Exception as e:
            print(f"Gagal membuat atau memposting Internal Transfer di Source baru: {e}")
            
    def transfer_goods_receipt(self, model_name, fields, description, date_from, date_to):
        try:
            # Ambil data dari sumber
            transaksi_goods_receipt = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                model_name, 'search_read',
                                                                [[['picking_type_id.name', '=', 'Goods Receipts'],
                                                                    ['is_integrated', '=', False], ['state', '=', 'done'],
                                                                    ['create_date', '>=', date_from], ['create_date', '<=', date_to]
                                                                    ]],
                                                                {'fields': fields})

            if not transaksi_goods_receipt:
                print("Semua transaksi telah diproses.")
                return

            # Persiapan dictionary untuk id source
            location_ids = [record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id') for record in transaksi_goods_receipt]
            location_dest_id = [record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id') for record in transaksi_goods_receipt]
            picking_type_ids = [record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id') for record in transaksi_goods_receipt]

            # Proses data lokasi
            location_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'stock.location', 'search_read',
                                                        [[['id', 'in', location_ids]]],
                                                        {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_source_dict = {location['id']: location['id_mc'] for location in location_source}

            location_dest_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id', 'in', location_dest_id]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_dest_source_dict = {location_dest['id']: location_dest['id_mc'] for location_dest in location_dest_source}

            # Proses picking type
            picking_type_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            'stock.picking.type', 'search_read',
                                                            [[['id', 'in', picking_type_ids]]],
                                                            {'fields': ['id', 'id_mc'] , 'limit': 1})
            picking_type_source_dict = {type['id']: type['id_mc'] for type in picking_type_source}

            # Dapatkan data stock move (inventory lines)
            picking_ids = [record['id'] for record in transaksi_goods_receipt]
            goods_receipt_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'stock.move', 'search_read',
                                                                        [[['picking_id', 'in', picking_ids]]],
                                                                        {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

            existing_goods_receipts_dict = {}
            for record in transaksi_goods_receipt:
                existing_gr = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        'stock.picking', 'search_read',
                                                        [[['vit_trxid', '=', record.get('name')]]],
                                                        {'fields': ['id'], 'limit': 1})
                if existing_gr:
                    existing_goods_receipts_dict[record['id']] = existing_gr[0]['id']

            # Dictionary untuk goods_receipts_lines
            goods_receipts_lines_dict = {}
            for line in goods_receipt_inventory_lines:
                if 'picking_id' in line:
                    picking_id = line['picking_id'][0]
                    if picking_id not in goods_receipts_lines_dict:
                        goods_receipts_lines_dict[picking_id] = []
                    goods_receipts_lines_dict[picking_id].append(line)

            # Ambil data produk
            product_ids = [line['product_id'][0] for line in goods_receipt_inventory_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'product_tmpl_id']})
            product_source_dict = {product['id']: product['product_tmpl_id'][0] for product in product_source}

            product_template_ids = list(product_source_dict.values())

            # Lakukan search_read pada product.template dengan id dari product_source_dict
            product_template_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'product.template', 'search_read',
                                                                [[['id', 'in', product_template_ids]]],
                                                                {'fields': ['id', 'id_mc', 'name', 'default_code']})

            # Membuat dictionary dengan key id dari product.template dan value id_mc
            product_template_dict = {product['id']: product['id_mc'] for product in product_template_source}

            # Kumpulan ID untuk batch validate
            new_goods_receipts_ids = []

            def proces_goods_receipts_record(record):
                if record['id'] in existing_goods_receipts_dict:
                    return

                goods_receipt_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                            self.source_client.uid, self.source_client.password,
                                                                            'stock.move', 'search_read',
                                                                            [[['picking_id', '=', record['id']]]],
                                                                            {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

                # Check lokasi dan picking_type
                location_id = location_source_dict.get(record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id'))
                location_dest_id = location_dest_source_dict.get(record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id'))
                picking_type_id = picking_type_source_dict.get(record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id'))

                if location_id is None or location_dest_id is None or picking_type_id is None:
                    print(f"Data tidak lengkap untuk transaksi dengan ID {record.get('id')}. Tidak membuat dokumen.")
                    return

                missing_products = []
                goods_receipt_inventory_line_ids = []
                for line in goods_receipt_inventory_lines:
                    product_id = product_template_dict.get(line.get('product_id')[0] if isinstance(line.get('product_id'), list) else line.get('product_id'))

                    product_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['id', '=', product_id], ['active', '=', True]]],
                                                                {'fields': ['id'], 'limit': 1})

                    if not product_target:
                        missing_products.append(product_id)
                        continue

                    goods_receipt_inventory_line_data = {
                        'product_id': int(product_id),
                        'product_uom_qty': line.get('product_uom_qty'),
                        'name': line.get('name'),
                        'quantity': line.get('quantity'),
                        'location_dest_id': int(location_dest_id),
                        'location_id': int(location_id),
                    }
                    goods_receipt_inventory_line_ids.append((0, 0, goods_receipt_inventory_line_data))

                if missing_products:
                    missing_products_str = ", ".join(missing_products)
                    message = f"Terdapat produk tidak aktif dalam Goods Receipt: {missing_products_str}"
                    print(message)
                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_failed(record, 'Goods Receipts', message, write_date)
                    self.set_log_ss.create_log_note_failed(record, 'Goods Receipts', message, write_date)

                goods_receipts_transfer_data = {
                    'scheduled_date': record.get('scheduled_date', False),
                    'date_done': record.get('date_done', False),
                    'vit_trxid': record.get('name', False),
                    'origin': record.get('vit_trxid', False),
                    'is_integrated': True,
                    'location_id': int(location_id),
                    'location_dest_id': int(location_dest_id),
                    'picking_type_id': int(picking_type_id),
                    'move_ids_without_package': goods_receipt_inventory_line_ids,
                }

                try:
                    start_time = time.time()
                    # Buat Goods Receipt
                    new_goods_receipts_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                        self.target_client.uid, self.target_client.password,
                                                                        'stock.picking', 'create',
                                                                        [goods_receipts_transfer_data])
                    print(f"Goods Receipt baru telah dibuat dengan ID: {new_goods_receipts_id}")

                    self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                self.source_client.uid, self.source_client.password,
                                                'stock.picking', 'write',
                                                [[record['id']], {'is_integrated': True, 'vit_trxid': record['name']}])
                

                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Goods Receipts', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Goods Receipts', write_date)
                except Exception as e:
                    message_exception = f"Gagal membuat atau memposting Goods Receipt baru: {e}"
                    self.set_log_mc.create_log_note_failed(record, 'Goods Receipts', message_exception, write_date)    
                    self.set_log_ss.create_log_note_failed(record, 'Goods Receipts', message_exception, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(proces_goods_receipts_record, record) for record in transaksi_goods_receipt]
                concurrent.futures.wait(futures)

        except Exception as e:
            print(f"Gagal membuat atau memposting Goods Receipts di Source baru: {e}")

    def transfer_receipts_ss(self, model_name, fields, description, date_from, date_to):
        try:
            # Ambil data dari sumber
            transaksi_receipt = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            model_name, 'search_read',
                                                            [[['picking_type_id.name', '=', 'GRPO'], ['is_integrated', '=', False], ['state', '=', 'done'], ['create_date', '>=', date_from], ['create_date', '<=', date_to]]],
                                                            {'fields': fields})

            if not transaksi_receipt:
                print("Semua transaksi telah diproses.")
                return

            location_ids = [record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id') for record in transaksi_receipt]
            location_dest_id = [record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id') for record in transaksi_receipt]
            picking_type_ids = [record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id') for record in transaksi_receipt]

            location_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id', 'in', location_ids]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_source_dict = {location['id']: location['id_mc'] for location in location_source}

            location_dest_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id', 'in', location_dest_id]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_dest_source_dict = {location_dest['id']: location_dest['id_mc'] for location_dest in location_dest_source}

            picking_type_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    'stock.picking.type', 'search_read',
                                                                    [[['id', 'in', picking_type_ids]]],
                                                                    {'fields': ['id', 'id_mc'] , 'limit': 1})
            picking_type_source_dict = {type['id']: type['id_mc'] for type in picking_type_source}

            picking_ids = [record['id'] for record in transaksi_receipt]
            transfer_grpo_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'stock.move', 'search_read',
                                                                        [[['picking_id', 'in', picking_ids]]],
                                                                        {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

            transfer_grpo_dict = {}
            for record in transaksi_receipt:
                existing_grpo = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'stock.picking', 'search_read',
                                                            [[['vit_trxid', '=', record.get('name')]]],
                                                            {'fields': ['id'], 'limit': 1})
                if existing_grpo:
                    transfer_grpo_dict[record['id']] = existing_grpo[0]['id']

            transfer_grpo_lines_dict = {}
            for line in transfer_grpo_inventory_lines:
                if 'picking_id' in line:
                    picking_id = line['picking_id'][0]
                    if picking_id not in transfer_grpo_lines_dict:
                        transfer_grpo_lines_dict[picking_id] = []
                    transfer_grpo_lines_dict[picking_id].append(line)

            product_ids = [line['product_id'][0] for line in transfer_grpo_inventory_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'product_tmpl_id']})
            product_source_dict = {product['id']: product['product_tmpl_id'][0] for product in product_source}

            product_template_ids = list(product_source_dict.values())

            # Lakukan search_read pada product.template dengan id dari product_source_dict
            product_template_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'product.template', 'search_read',
                                                                [[['id', 'in', product_template_ids]]],
                                                                {'fields': ['id', 'id_mc', 'name', 'default_code']})

            # Membuat dictionary dengan key id dari product.template dan value id_mc
            product_template_dict = {product['id']: product['id_mc'] for product in product_template_source}

            new_grpo_ids = []
            def proces_grpo_record(record):
                if record['id'] in transfer_grpo_dict:
                    return
                
                transfer_grpo_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'stock.move', 'search_read',
                                                                        [[['picking_id', '=', record['id']]]],
                                                                        {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

                location_id = location_source_dict.get(record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id'))
                location_dest_id = location_dest_source_dict.get(record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id'))
                picking_type_id = picking_type_source_dict.get(record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id'))
                
                if location_id is None or location_dest_id is None or picking_type_id is None:
                    print(f"Data tidak lengkap untuk transaksi dengan ID {record.get('id')}. Tidak membuat dokumen.")
                    return
            
                missing_products = []
                receipt_inventory_line_ids = []
                for line in transfer_grpo_inventory_lines:
                    product_id = product_template_dict.get(line.get('product_id')[0] if isinstance(line.get('product_id'), list) else line.get('product_id'))

                    # Check if the product is active in the target system
                    product_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['id', '=', product_id], ['active', '=', True]]],
                                                                {'fields': ['id'], 'limit': 1})

                    if not product_target:
                        missing_products.append(product_id)
                        continue

                    receipt_inventory_line_data = {
                        'product_id': int(product_id),
                        'product_uom_qty': line.get('product_uom_qty'),
                        'name': line.get('name'),
                        'quantity': line.get('quantity'),
                        'location_dest_id': int(location_dest_id),
                        'location_id': int(location_id),
                    }
                    receipt_inventory_line_ids.append((0, 0, receipt_inventory_line_data))

                    if missing_products:
                        missing_products_str = ", ".join(missing_products)
                        message = f"Terdapat produk tidak aktif dalam Receipt: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'Receipts', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'Receipts', message, write_date)


                receipts_transfer_data = {
                    # 'name': record.get('name', False) + ' - ' + datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%Y-%m-%d %H:%M:%S"),
                    # 'partner_id': customer_target_id,
                    'scheduled_date': record.get('scheduled_date', False),
                    'date_done': record.get('date_done', False),
                    'vit_trxid': record.get('name', False),
                    'is_integrated': True,
                    'location_id': int(location_id),
                    'location_dest_id': int(location_dest_id),
                    'picking_type_id': int(picking_type_id),
                    'move_ids_without_package': receipt_inventory_line_ids,
                }

                try:
                    new_receipts_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking', 'create',
                                                                    [receipts_transfer_data])
                    print(f"Receipt baru telah dibuat dengan ID: {new_receipts_id}")

                    start_time = time.time()
                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'stock.picking', 'write',
                        [[record['id']], {'is_integrated': True, 'vit_trxid': record['name']}]
                    )
                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Receipts', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Receipts', write_date)
                except Exception as e:
                    message_exception = f"Gagal membuat atau memposting Receipt baru: {e}"
                    self.set_log_mc.create_log_note_failed(record, 'Receipts', message_exception, write_date)    
                    self.set_log_ss.create_log_note_failed(record, 'Receipts', message_exception, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(proces_grpo_record, record) for record in transaksi_receipt]
                concurrent.futures.wait(futures)
            
        except Exception as e:
            print(f"Gagal membuat atau memposting GRPO di Source baru: {e}")

    def transfer_goods_issue(self, model_name, fields, description, date_from, date_to):
        try:
            # Ambil data dari sumber
            transaksi_goods_issue = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            model_name, 'search_read',
                                                            [[['picking_type_id.name', '=', 'Goods Issue'], ['is_integrated', '=', False], ['state', '=', 'done'], ['create_date', '>=', date_from], ['create_date', '<=', date_to]]],
                                                            {'fields': fields})

            if not transaksi_goods_issue:
                print("Semua transaksi telah diproses.")
                return

            location_ids = [record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id') for record in transaksi_goods_issue]
            location_dest_id = [record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id') for record in transaksi_goods_issue]
            picking_type_ids = [record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id') for record in transaksi_goods_issue]

            location_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id', 'in', location_ids]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_source_dict = {location['id']: location['id_mc'] for location in location_source}

            location_dest_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id', 'in', location_dest_id]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_dest_source_dict = {location_dest['id']: location_dest['id_mc'] for location_dest in location_dest_source}

            picking_type_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    'stock.picking.type', 'search_read',
                                                                    [[['id', 'in', picking_type_ids]]],
                                                                    {'fields': ['id', 'id_mc'] , 'limit': 1})
            picking_type_source_dict = {type['id']: type['id_mc'] for type in picking_type_source}

            picking_ids = [record['id'] for record in transaksi_goods_issue]
            goods_issue_transfer_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'stock.move', 'search_read',
                                                                        [[['picking_id', 'in', picking_ids]]],
                                                                        {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

            existing_goods_issue_dict = {}
            for record in transaksi_goods_issue:
                existing_gi = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'stock.picking', 'search_read',
                                                            [[['vit_trxid', '=', record.get('name')]]],
                                                            {'fields': ['id'], 'limit': 1})
                if existing_gi:
                    existing_goods_issue_dict[record['id']] = existing_gi[0]['id']

            goods_issue_lines_dict = {}
            for line in goods_issue_transfer_lines:
                if 'picking_id' in line:
                    picking_id = line['picking_id'][0]
                    if picking_id not in goods_issue_lines_dict:
                        goods_issue_lines_dict[picking_id] = []
                    goods_issue_lines_dict[picking_id].append(line)

            product_ids = [line['product_id'][0] for line in goods_issue_transfer_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'product_tmpl_id']})
            product_source_dict = {product['id']: product['product_tmpl_id'][0] for product in product_source}

            product_template_ids = list(product_source_dict.values())

            # Lakukan search_read pada product.template dengan id dari product_source_dict
            product_template_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'product.template', 'search_read',
                                                                [[['id', 'in', product_template_ids]]],
                                                                {'fields': ['id', 'id_mc', 'name', 'default_code']})

            # Membuat dictionary dengan key id dari product.template dan value id_mc
            product_template_dict = {product['id']: product['id_mc'] for product in product_template_source}
            
            new_goods_issues_ids = []
            def proces_goods_issue_record(record):
                if record['id'] in existing_goods_issue_dict:
                    return
                
                goods_issue_transfer_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'stock.move', 'search_read',
                                                                        [[['picking_id', '=', record['id']]]],
                                                                        {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})
                
                location_id = location_source_dict.get(record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id'))
                location_dest_id = location_dest_source_dict.get(record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id'))
                picking_type_id = picking_type_source_dict.get(record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id'))

                if location_id is None or location_dest_id is None or picking_type_id is None:
                    print(f"Data tidak lengkap untuk transaksi dengan ID {record.get('id')}. Tidak membuat dokumen.")
                    return

                missing_products = []
                goods_issue_inventory_line_ids = []
                for line in goods_issue_transfer_lines:
                    product_id = product_template_dict.get(line.get('product_id')[0] if isinstance(line.get('product_id'), list) else line.get('product_id'))

                    # Check if the product is active in the target system
                    product_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['id', '=', product_id], ['active', '=', True]]],
                                                                {'fields': ['id'], 'limit': 1})

                    if not product_target:
                        missing_products.append(product_id)
                        continue

                    goods_issue_inventory_line_data = {
                        'product_id': int(product_id),
                        'product_uom_qty': line.get('product_uom_qty'),
                        'name': line.get('name'),
                        'quantity': line.get('quantity'),
                        'location_dest_id': int(location_dest_id),
                        'location_id': int(location_id),
                    }
                    goods_issue_inventory_line_ids.append((0, 0, goods_issue_inventory_line_data))

                    if missing_products:
                        missing_products_str = ", ".join(missing_products)
                        message = f"Terdapat produk tidak aktif dalam Goods Issue: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'Goods Issue', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'Goods Issue', message, write_date)

                internal_transfer_data = {
                    # 'name': record.get('name', False) + ' - ' + datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%Y-%m-%d %H:%M:%S"),
                    # 'partner_id': customer_target_id,
                    'scheduled_date': record.get('scheduled_date', False),
                    'date_done': record.get('date_done', False),
                    'vit_trxid': record.get('name', False),
                    'origin': record.get('vit_trxid', False),
                    'is_integrated': True,
                    'location_id': int(location_id),
                    'location_dest_id': int(location_dest_id),
                    'picking_type_id': int(picking_type_id),
                    'move_ids_without_package': goods_issue_inventory_line_ids,
                }

                try:
                    new_goods_issue_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking', 'create',
                                                                    [internal_transfer_data])
                    print(f"Goods Issue baru telah dibuat dengan ID: {new_goods_issue_id}")

                    start_time = time.time()
                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'stock.picking', 'write',
                        [[record['id']], {'is_integrated': True, 'vit_trxid': record['name']}]
                    )
                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Goods Issue', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Goods Issue', write_date)
                except Exception as e:
                    print(f"Gagal membuat atau memposting Goods Issue baru: {e}")
                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_failed(record, 'Goods Issue', message, write_date)
                    self.set_log_ss.create_log_note_failed(record, 'Goods Issue', message, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(proces_goods_issue_record, record) for record in transaksi_goods_issue]
                concurrent.futures.wait(futures)

        except Exception as e:
            print(f"Gagal membuat atau memposting Goods Issue di Source baru: {e}")

    def transfer_stock_adjustment(self, model_name, fields, description, date_from, date_to):
        try:
            # Mendapatkan data stock adjustment dari sumber
            transaksi_stock_adjustment = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                model_name, 'search_read',
                [[['reference', '=', 'Product Quantity Updated'], ['is_integrated', '=', False], ['state', '=', 'done']]],
                {'fields': fields}
            )

            if not transaksi_stock_adjustment:
                print("Tidak ada transaksi yang ditemukan untuk ditransfer.")
                return
            
            product_ids = [record.get('product_id')[0] if isinstance(record.get('product_id'), list) else record.get('product_id') for record in transaksi_stock_adjustment]
            location_ids = [record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id') for record in transaksi_stock_adjustment]
            location_dest_id = [record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id') for record in transaksi_stock_adjustment]

            location_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    'stock.location', 'search_read',
                                                                    [[['id', 'in', location_ids]]],
                                                                    {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_source_dict = {location['id']: location['id_mc'] for location in location_source}

            location_dest_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id', 'in', location_ids]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_dest_source_dict = {location_dest['id']: location_dest['id_mc'] for location_dest in location_dest_source}

            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    'product.product', 'search_read',
                                                                    [[['id', 'in', product_ids]]],
                                                                    {'fields': ['id', 'id_mc'] , 'limit': 1})
            product_source_dict = {product['id']: product['id_mc'] for product in product_source}

            for record in transaksi_stock_adjustment:
                inventory_quantity = record.get('quantity')
                location_id = location_source_dict.get(record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id'))
                location_dest_id = location_dest_source_dict.get(record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id'))
                product_id = product_source_dict.get(record.get('product_id')[0] if isinstance(record.get('product_id'), list) else record.get('product_id'))

                # Mencari stock.quant yang sesuai di target
                stock_quant_target = self.target_client.call_odoo(
                    'object', 'execute_kw', self.target_client.db,
                    self.target_client.uid, self.target_client.password,
                    'stock.quant', 'search_read',
                    [[
                        ['product_id', '=', product_id],
                        '|',
                        ['location_id', '=', location_id],
                        ['location_id', '=', location_dest_id]
                    ]],
                    {'fields': ['id', 'inventory_quantity'], 'limit': 1}
                )

                if not stock_quant_target:
                    new_stock_quant = self.target_client.call_odoo(
                        'object', 'execute_kw', self.target_client.db,
                        self.target_client.uid, self.target_client.password,
                        'stock.quant', 'create',
                        [{'product_id': product_id, 'inventory_quantity': inventory_quantity, 'location_id': location_id}]
                    )
                    print(f"Produk dengan default_code {product_id} telah ditambahkan ke stock.quant baru dengan ID {new_stock_quant}.")
                    self.target_client.call_odoo(
                        'object', 'execute_kw', self.target_client.db,
                        self.target_client.uid, self.target_client.password,
                        'stock.quant', 'action_apply_inventory',
                        [new_stock_quant]
                    )
                    print(f"Produk dengan default_code {product_id} telah ditambahkan ke stock.quant dengan ID {new_stock_quant}.")
                    continue

                stock_quant_id = stock_quant_target[0]['id']

                # Update inventory_quantity di stock.quant
                self.target_client.call_odoo(
                    'object', 'execute_kw', self.target_client.db,
                    self.target_client.uid, self.target_client.password,
                    'stock.quant', 'write',
                    [[stock_quant_id], {'inventory_quantity': inventory_quantity}]
                )

                print(f"Inventory quantity untuk stock.quant ID {stock_quant_id} telah diperbarui menjadi {inventory_quantity}.")

                # Menandai transaksi di sumber sebagai telah diintegrasikan
                self.source_client.call_odoo(
                    'object', 'execute_kw', self.source_client.db,
                    self.source_client.uid, self.source_client.password,
                    model_name, 'write',
                    [[record['id']], {'is_integrated': True}]
                )
                print(f"Transaksi dengan ID {record['id']} di database sumber telah ditandai sebagai diintegrasikan.")

                # Menjalankan tombol action_apply_inventory
                try:
                    start_time = time.time()
                    self.target_client.call_odoo(
                        'object', 'execute_kw', self.target_client.db,
                        self.target_client.uid, self.target_client.password,
                        'stock.quant', 'action_apply_inventory',
                        [stock_quant_id]
                    )
                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Inventory Adjustment', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Inventory Adjustment', write_date)

                    message_success = f"Action apply inventory telah dijalankan untuk stock.quant ID {stock_quant_id}."
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Inventory Adjustment', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Inventory Adjustment', write_date)
                    print(message_success)
                except Exception as e:
                    message_exception = (f"Error: {str(e)}")
                    self.set_log_mc.create_log_note_failed(record, 'Inventory Adjustment', message_exception, write_date)    
                    self.set_log_ss.create_log_note_failed(record, 'Inventory Adjustment', message_exception, write_date)

        except Exception as e:
            print(f"Terjadi kesalahan: {str(e)}")
            return False  # Atau sesuai dengan kebutuhan Anda

    def update_session_status(self, model_name, fields, description, date_from, date_to):
        pos_sessions = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            model_name, 'search_read',
                            [[['write_date', '>=', date_from], ['write_date', '<=', date_to]]],
                            {'fields': fields})

        if not pos_sessions:
            print("Tidak ada sesi yang ditemukan untuk ditransfer.")
            return

        for sessions in pos_sessions:
            name = sessions.get('name')
            state = sessions.get('state')
            start_at = sessions.get('start_at')
            stop_at = sessions.get('stop_at')

            cash_register_balance_start = sessions.get('cash_register_balance_start')
            cash_register_balance_end_real = sessions.get('cash_register_balance_end_real')

            # Debugging prints
            print(f"Cash Register Balance Start: {cash_register_balance_start}")
            print(f"Cash Register Balance End Real: {cash_register_balance_end_real}")

            # Ensure monetary values are properly handled
            cash_register_balance_start = float(cash_register_balance_start) if cash_register_balance_start else 0.0
            cash_register_balance_end_real = float(cash_register_balance_end_real) if cash_register_balance_end_real else 0.0

            if not state:
                print(f"Status sesi {name} tidak valid.")
                continue

            # Fetch the corresponding session on the source client based on the session name
            source_session = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        model_name, 'search_read',
                                                        [[['name_session_pos', '=', name]]],
                                                        {'fields': ['state'], 'limit': 1})

            if not source_session:
                print(f"Sesi dengan nama {name} tidak ditemukan di sumber.")
                continue

            # Update the state on the target client
            session_id = source_session[0]['id']

            update_result = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                            self.target_client.uid, self.target_client.password,
                                            model_name, 'write',
                                            [[session_id], {'state': state, 'start_at': start_at, 'stop_at': stop_at, 'cash_register_balance_start': cash_register_balance_start, 'cash_register_balance_end_real': cash_register_balance_end_real, 'is_updated': True}])
            
            self.source_client.call_odoo(
                    'object', 'execute_kw', self.source_client.db,
                    self.source_client.uid, self.source_client.password,
                    'pos.session', 'write',
                    [[sessions['id']], {'is_updated': True}]
            )

            # if update_result:
            #     message_succes = f"Berhasil mengupdate sesi {name} dengan status {state}."
            #     self.set_log_mc.create_log_note_success(sessions, 'Update Session', message_succes, sessions['write_date'])
            #     self.set_log_ss.create_log_note_success(sessions, 'Update Session', message_succes, sessions['write_date'])
            # else:
            #     message_exception = f"Gagal mengupdate sesi {name}."
            #     self.set_log_mc.create_log_note_failed(sessions, 'Update Session', message_exception, sessions['write_date'])
            #     self.set_log_ss.create_log_note_failed(sessions, 'Update Session', message_exception, sessions['write_date'])

    def update_loyalty_point_ss_to_mc(self, model_name, fields, description, date_from, date_to):
        id_program = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                    self.source_client.uid, self.source_client.password,
                                                    model_name, 'search_read',
                                                    [[]],
                                                    {'fields': fields})

        for res in id_program:
            programs = res.get('id', False)

            # Ambil data dari sumber
            loyalty_points = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'loyalty.card', 'search_read',
                                                        [[['program_id', '=', int(programs)]]],
                                                        {'fields': ['code', 'points_display', 'expiration_date', 'program_id', 'currency_id', 'partner_id', 'source_pos_order_id', 'points']})

            # Pre-fetch necessary data to reduce API calls
            pos_order_ids = {record.get('source_pos_order_id')[0] for record in loyalty_points if record.get('source_pos_order_id')}
            pos_orders = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                    self.source_client.uid, self.source_client.password,
                                                    'pos.order', 'search_read',
                                                    [[['id', 'in', list(pos_order_ids)]]],
                                                    {'fields': ['id', 'vit_trxid']})

            pos_order_map = {order['id']: order['vit_trxid'] for order in pos_orders}

            program_ids = {record.get('program_id')[0] for record in loyalty_points if record.get('program_id')}
            programs_data = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'loyalty.program', 'search_read',
                                                        [[['id', 'in', list(program_ids)]]],
                                                        {'fields': ['id', 'name']})

            program_map = {program['id']: program['name'] for program in programs_data}

            partner_ids = {record.get('partner_id')[0] for record in loyalty_points if record.get('partner_id')}
            partners_data = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'res.partner', 'search_read',
                                                        [[['id', 'in', list(partner_ids)]]],
                                                        {'fields': ['id', 'customer_code']})

            partner_map = {partner['id']: partner['customer_code'] for partner in partners_data}

            # Pre-fetch order references, program IDs, and partner IDs
            order_references = {}
            program_id_sets = {}
            partner_id_sets = {}

            for record in loyalty_points:
                order_ref = False
                if record.get('source_pos_order_id'):
                    order_ref = pos_order_map.get(record['source_pos_order_id'][0])

                if order_ref and order_ref not in order_references:
                    order_reference = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'pos.order', 'search_read',
                                                                    [[['name', '=', order_ref]]],
                                                                    {'fields': ['id'], 'limit': 1})
                    order_references[order_ref] = order_reference[0]['id'] if order_reference else False

                program_id = record.get('program_id')
                if program_id and program_id[0] not in program_id_sets:
                    program_id_new = program_map.get(program_id[0])
                    program_id_set = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'loyalty.program', 'search_read',
                                                                    [[['name', '=', program_id_new]]],
                                                                    {'fields': ['id'], 'limit': 1})
                    program_id_sets[program_id[0]] = program_id_set[0]['id'] if program_id_set else False

                partner_id = record.get('partner_id')
                if partner_id and partner_id[0] not in partner_id_sets:
                    partner_id_new = partner_map.get(partner_id[0])
                    partner_id_set = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'res.partner', 'search_read',
                                                                    [[['customer_code', '=', partner_id_new]]],
                                                                    {'fields': ['id'], 'limit': 1})
                    partner_id_sets[partner_id[0]] = partner_id_set[0]['id'] if partner_id_set else False

            def process_loyalty_point(record):
                existing_loyalty_points_mc = self.target_client.call_odoo(
                    'object', 'execute_kw', self.target_client.db,
                    self.target_client.uid, self.target_client.password,
                    'loyalty.card', 'search_read',
                    [[['code', '=', record['code']]]],
                    {'fields': ['id']}
                )

                if existing_loyalty_points_mc:
                    loyalty_id = existing_loyalty_points_mc[0]['id']
                    code = record.get('code')
                    expiration_date = record.get('expiration_date')
                    points = record.get('points')
                    points_display = record.get('points_display')

                    order_id = order_references.get(record.get('source_pos_order_id')[0], False) if record.get('source_pos_order_id') else False
                    program_id = program_id_sets.get(record.get('program_id')[0], False) if record.get('program_id') else False
                    partner_id = partner_id_sets.get(record.get('partner_id')[0], False) if record.get('partner_id') else False

                    data_loyalty_mc = {
                        'code': code,
                        'expiration_date': expiration_date,
                        'points': points,
                        'points_display': points_display,
                        'source_pos_order_id': order_id,
                        'program_id': program_id,
                        'partner_id': partner_id
                    }

                    try:
                        # Menggunakan `write` untuk memperbarui data yang sudah ada
                        self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                    self.target_client.uid, self.target_client.password,
                                                    'loyalty.card', 'write',
                                                    [[loyalty_id], data_loyalty_mc])
                        print(f"Loyalty dengan ID {loyalty_id} telah diperbarui di target_client.")
                    except Exception as e:
                        print(f"Terjadi kesalahan saat memperbarui loyalty: {e}")

            # Process loyalty points in batches of 100
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                for i in range(0, len(loyalty_points), 100):
                    batch = loyalty_points[i:i + 100]
                    executor.map(process_loyalty_point, batch)
    
    def validate_tsin_tsout(self, model_name, fields, description, date_from, date_to):
        # Retrieve TS In records that match the specified criteria from the source database
        TS_in_validates = self.source_client.call_odoo(
            'object', 'execute_kw', 
            self.source_client.db, self.source_client.uid, self.source_client.password,
            'stock.picking', 'search_read',
            [[
                ['picking_type_id.name', '=', 'TS In'], 
                ['is_integrated', '=', True], 
                ['is_updated', '=', False],
                ['state', '=', 'done'],
                ['write_date', '>=', date_from],
                ['write_date', '<=', date_to],
            ]],
            {'fields': ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'move_ids_without_package']}
        )

        # Check if any TS In records are found
        if not TS_in_validates:
            print("Tidak ada TS In yang ditemukan di target.")
        else:
            # Process in batches of 100
            for i in range(0, len(TS_in_validates), 100):
                batch = TS_in_validates[i:i + 100]
                for ts in batch:
                    vit_trxid = ts.get('vit_trxid', False)

                    # Retrieve TS In records that need validation from the target database
                    TS_in_needs_validate = self.target_client.call_odoo(
                        'object', 'execute_kw', 
                        self.target_client.db, self.target_client.uid, self.target_client.password,
                        'stock.picking', 'search_read',
                        [[
                            ['picking_type_id.name', '=', 'TS In'], 
                            ['name', '=', vit_trxid], 
                            ['is_integrated', '=', True], 
                            ['state', '=', 'assigned']
                        ]],
                        {'fields': ['id', 'name']}
                    )

                    # Validate each TS In record
                    for ts_in in TS_in_needs_validate:
                        ts_in_id = ts_in['id']
                        try:
                            start_time = time.time()
                            self.target_client.call_odoo(
                                'object', 'execute_kw',
                                self.target_client.db, self.target_client.uid, self.target_client.password,
                                'stock.picking', 'button_validate',
                                [ts_in_id]
                            )
                            self.source_client.call_odoo(
                                'object', 'execute_kw', self.source_client.db,
                                self.source_client.uid, self.source_client.password,
                                'stock.picking', 'write',
                                [[ts['id']], {'is_updated': True}]
                            )

                            print(f"TS In with ID {ts_in_id} has been validated.")
                            end_time = time.time()
                            duration = end_time - start_time

                            write_date = self.get_write_date(model_name, ts_in['id'])
                            self.set_log_mc.create_log_note_success(ts_in, start_time, end_time, duration, 'TS Out/TS In', write_date)
                            self.set_log_ss.create_log_note_success(ts_in, start_time, end_time, duration, 'TS Out/TS In', write_date)
                        except Exception as e:
                            message_exception = f"Failed to validate TS In with ID {ts_in_id}: {e}"
                            self.set_log_mc.create_log_note_failed(ts_in, 'TS Out/TS In', message_exception, write_date)    
                            self.set_log_ss.create_log_note_failed(ts_in, 'TS Out/TS In', message_exception, write_date)

    def transfer_end_shift_from_store(self, model_name, fields, description):
        try:
            # Fetching the data
            end_shift_store = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    model_name, 'search_read',
                                                                    [[['state', '=', 'finished'], ['is_integrated', '=', False]]],
                                                                    {'fields': fields})

            if not end_shift_store:
                print("Semua shift telah diproses.")
                return
            
            cashier_ids = [record.get('cashier_id')[0] if isinstance(record.get('cashier_id'), list) else record.get('cashier_id') for record in end_shift_store]
            session_ids = [record.get('session_id')[0] if isinstance(record.get('session_id'), list) else record.get('session_id') for record in end_shift_store]

            cashier_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'hr.employee', 'search_read',
                                                        [[['id', 'in', cashier_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            cashier_source_dict = {employee['id']: employee['id_mc'] for employee in cashier_source}

            # Fetch sessions
            sessions_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'pos.session', 'search_read',
                                                        [[['id', 'in', session_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            sessions_source_dict = {session['id']: session['id_mc'] for session in sessions_source}

            end_shift_ids = [record['id'] for record in end_shift_store]
            end_shift_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'end.shift.line', 'search_read',
                                                        [[['end_shift_id', 'in', end_shift_ids]]],
                                                        {'fields': ['end_shift_id', 'payment_date', 'payment_method_id', 'amount', 'expected_amount', 'amount_difference']})

            # Create dictionaries for quick lookup
            end_shift_lines_dict = {}
            for line in end_shift_lines:
                end_shift_id = line['end_shift_id'][0]
                if end_shift_id not in end_shift_lines_dict:
                    end_shift_lines_dict[end_shift_id] = []
                end_shift_lines_dict[end_shift_id].append(line)

            # Pre-fetch existing end shifts in target
            existing_end_shift_dict = {}
            for record in end_shift_store:
                existing_end_shift = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                        self.target_client.uid, self.target_client.password,
                                                                        'end.shift', 'search_read',
                                                                        [[['doc_num', '=', record.get('doc_num')]]],
                                                                        {'fields': ['id'], 'limit': 1})
                if existing_end_shift:
                    existing_end_shift_dict[record['id']] = existing_end_shift[0]['id']

            payment_method_ids = [payment['payment_method_id'][0] for payment in end_shift_lines if payment.get('payment_method_id')]
            payment_method_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'pos.payment.method', 'search_read',
                                                                [[['id', 'in', payment_method_ids]]],
                                                                {'fields': ['id', 'id_mc', 'name']})
            payment_method_source_dict = {payment['id']: payment['id_mc'] for payment in payment_method_source}

            def process_record_endshift(record):
                if record['id'] in existing_end_shift_dict:
                    print(f"End Shift {record['doc_num']} sudah diproses.")
                    return
                
                end_shift_lines = end_shift_lines_dict.get(record['id'], [])
                end_shift_line_ids = []
                missing_payment_methods = []

                # Check if all payment methods exist in the target database
                for line in end_shift_lines:
                    payment_date = line.get('payment_date')
                    amount = line.get('amount')
                    expected_amount = line.get('expected_amount')

                    payment_method_id = payment_method_source_dict.get(line.get('payment_method_id')[0] if isinstance(line.get('payment_method_id'), list) else line.get('payment_method_id'))  

                    if payment_method_id is None:
                        print(f"Payment method {line.get('payment_method_id')} is missing a id_mc.")
                        continue

                    if not payment_method_id:
                        missing_payment_methods.append(line.get('payment_method_id'))
                        continue

                    end_shift_line_data = {
                        'payment_date': payment_date,
                        'payment_method_id': int(payment_method_id),
                        'amount': amount,
                        'expected_amount': expected_amount
                    }
                    end_shift_line_ids.append((0, 0, end_shift_line_data))

                if missing_payment_methods:
                    missing_payment_methods_str = ", ".join(map(str, missing_payment_methods))
                    message = f"Terdapat metode pembayaran tidak aktif dalam end shift: {missing_payment_methods_str}"
                    print(message)
                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_failed(record, 'End Shift', message, write_date)
                    self.set_log_ss.create_log_note_failed(record, 'End Shift', message, write_date)
                    return

                cashier_id = cashier_source_dict.get(record.get('cashier_id')[0] if isinstance(record.get('cashier_id'), list) else record.get('cashier_id'))
                session_id = sessions_source_dict.get(record.get('session_id')[0] if isinstance(record.get('session_id'), list) else record.get('session_id'))

                if not cashier_id or not session_id:
                    print(f"Data tidak lengkap untuk shift dengan ID {record.get('id')}. Tidak membuat dokumen.")
                    return

                end_shift_data = {
                    'doc_num': record.get('doc_num'),
                    'cashier_id': int(cashier_id),
                    'session_id': int(session_id),
                    'start_date': record.get('start_date'),
                    'end_date': record.get('end_date'),
                    'line_ids': end_shift_line_ids,
                }

                try:
                    start_time = time.time()
                    print(f"Attempting to create end shift with data: {end_shift_data}")
                    new_end_shift_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'end.shift', 'create',
                                                                    [end_shift_data])

                    if not new_end_shift_id:
                        raise Exception("Failed to create new end shift. No ID returned.")

                    print(f"Shift baru telah dibuat dengan ID: {new_end_shift_id}")

                    print(f"Attempting to close end shift with ID: {new_end_shift_id}")

                    close_result = self.target_client.call_odoo(
                        'object', 'execute_kw',
                        self.target_client.db, self.target_client.uid, self.target_client.password,
                        'end.shift', 'action_close',
                        [[new_end_shift_id]]
                    )
                    print(f"Close result: {close_result}")

                    print(f"Marking source end shift as integrated. ID: {record['id']}")
                    # write_result = self.source_client.call_odoo(
                    #     'object', 'execute_kw', self.source_client.db,
                    #     self.source_client.uid, self.source_client.password,
                    #     'end.shift', 'write',
                    #     [[record['id']], {'is_integrated': True}]
                    # )
                    # print(f"Write result: {write_result}")

                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'End Shift', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'End Shift', write_date)
                except Exception as e:
                    print(f"Terjadi kesalahan saat membuat end shift: {str(e)}")
                    write_date = self.get_write_date(model_name, record['id'])
                    error_message = f"Gagal membuat end shift: {str(e)}"
                    self.set_log_mc.create_log_note_failed(record, 'End Shift', error_message, write_date)
                    self.set_log_ss.create_log_note_failed(record, 'End Shift', error_message, write_date)

            # Use ThreadPoolExecutor to process records in parallel
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_record_endshift, record) for record in end_shift_store]
                concurrent.futures.wait(futures)

        except Exception as e:
            print(f"Error during processing: {e}")

    def debug_taxes(self, model_name, fields, description):
        tax_source = self.source_client.call_odoo(
            'object', 'execute_kw', self.source_client.db,
            self.source_client.uid, self.source_client.password,
            model_name, 'search_read',
            [[]],
            {'fields': fields}
        )

        tax_ids = []
        for rec in tax_source:
            name = rec.get('name')
            print(name)
    
            tax_target = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'account.tax', 'search_read',
                [[['name', '=', name]]],
                {'fields': ['id']}
            )

            if tax_target:  # Check if the list is not empty
                tax_ids.append(tax_target[0]['id'])

                print(tax_ids)
        
    def debug_operatin_type(self, model_name, fields, description):
        operatin_type_source = self.source_client.call_odoo(
            'object', 'execute_kw', self.source_client.db,
            self.source_client.uid, self.source_client.password,
            model_name, 'search_read',
            [[['complete_name', '=', "JB/Stock"]]],
            {'fields': fields}
        )

        print(operatin_type_source)

    def update_integrated(self, model_name, fields, description):
        # Mengambil data dari Odoo
        config_source =  self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        model_name, 'search_read',
                                                        [[['is_integrated', '=', False]]],
                                                        {'fields': fields})

        # Mengambil ID dari data yang didapat
        ids_to_update = [record['id'] for record in config_source]

        # Memperbarui is_integrated menjadi True untuk semua ID yang didapat
        if ids_to_update:
            update_result = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'pos.session', 'write',
                                                        [ids_to_update, {'is_integrated': True}])

            if update_result:
                print("Update successful for IDs:", ids_to_update)
            else:
                print("Failed to update records.")
        else:
            print("No records found to update.")

    def update_status_order_pos(self, model_name, fields, description):
        # Mengambil data dari Odoo
        config_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                    self.target_client.uid, self.target_client.password,
                                                    model_name, 'search_read',
                                                    [[['state', '=', 'paid']]],
                                                    {'fields': fields})

        # Mengambil ID dari data yang didapat
        ids_to_update = [record['id'] for record in config_source]

        # Memperbarui is_integrated menjadi True untuk semua ID yang didapat
        if ids_to_update:
            # Loop through each ID to update
            for order_id in ids_to_update:
                try:
                    update_result = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'pos.order', 'action_pos_order_invoice',
                                                                [[order_id]])

                    if update_result:
                        print(f"Update successful for ID: {order_id}")
                    else:
                        print(f"Failed to update record with ID: {order_id}")
                except Exception as e:
                    print(f"Error updating record with ID {order_id}: {e}")
        else:
            print("No records found to update.")

    def create_data_transaksi(self, model, record, modul):
        try:
            record['invoice_line_ids'] = self.transfer_invoice_lines(record['id'], 'account.move.line')
            start_time = time.time()
            self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                         self.source_client.password, model, 'create', [record])
            end_time = time.time()
            duration = end_time - start_time

            self.set_log_mc.create_log_note_success(record, modul)
            self.set_log_mc.create_log_runtime_odoo(start_time, end_time, duration, modul)  # masih ngelooping belum dikeluarin
            self.set_log_ss.create_log_note_success(record, modul)
            self.set_log_ss.create_log_runtime_odoo(start_time, end_time, duration, modul)
        except Exception as e:
            sync_status = f"An error occurred while create data transaksi: {e}"
            print(sync_status)

    def get_write_uid_data(self, model):
        try:
            write_uid_data = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password, model,
                                                        'search_read', [[]], {'fields': ['write_uid']})
            return write_uid_data
        except Exception as e:
            print(f"An error occured while get write uid data: {e}")
            return None

    def get_write_date(self, model, id):
        try:
            write_date = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password, model,
                                                        'search_read', [[['id', '=', id]]], {'fields': ['write_date']})
            if write_date:
                write_date_value = write_date[0]['write_date']
                return write_date_value
        except Exception as e:
            print(f"Error occurred when get write date: {e}")

class SetLogMC:
    def __init__(self, source_client):
        self.source_client = source_client

    def log_record_success(self, record, start_time, end_time, duration, modul, write_date):
        gmt_7_now = datetime.now() - timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        gmt_7_start_time = datetime.fromtimestamp(start_time) - timedelta(hours=7)
        gmt_7_end_time = datetime.fromtimestamp(end_time) - timedelta(hours=7)
        record_log_success = {
            'vit_doc_type': modul,
            'vit_trx_key': record.get('name'),
            'vit_trx_date': write_date,
            'vit_sync_date': gmt_7_now.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_sync_status': 'Success',
            'vit_sync_desc': f"Data yang masuk: {record}",
            'vit_start_sync': gmt_7_start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_end_sync': gmt_7_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_duration' : f"{duration:.2f} second"
        }
        return record_log_success
    
    def log_update_record_success(self, record, record_id, updated_fields, start_time, end_time, duration, modul, write_date):
        gmt_7_now = datetime.now() - timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        gmt_7_start_time = datetime.fromtimestamp(start_time) - timedelta(hours=7)
        gmt_7_end_time = datetime.fromtimestamp(end_time) - timedelta(hours=7)
        record_log_success = {
            'vit_doc_type': f"Update: {modul}",
            'vit_trx_key': record.get('name'),
            'vit_trx_date': write_date,
            'vit_sync_date': gmt_7_now.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_sync_status': 'Success',
            'vit_sync_desc': f"Data yang diupdate: id {record_id},  {updated_fields}",
            'vit_start_sync': gmt_7_start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_end_sync': gmt_7_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_duration' : f"{duration:.2f} second"
        }
        return record_log_success
    
    def log_record_failed(self, record, modul, sync_status, write_date):
        gmt_7_now = datetime.now() - timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        
        if isinstance(sync_status, str) is False:
            sync_status = sync_status.args[0]
            sync_status = sync_status['data']['message']

        record_log_failed = {
            'vit_doc_type': modul,
            'vit_trx_key': record.get('name'),
            'vit_trx_date': write_date,
            'vit_sync_date': gmt_7_now.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_sync_status': 'Failed',
            'vit_sync_desc': sync_status
        }
        return record_log_failed

    def delete_data_log(self):
        try:
            filter_domain = [['vit_code_type', '=', 'Master']]
            data_logruntime = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                           self.source_client.uid, self.source_client.password,
                                                           'log.code.runtime', 'search_read', [filter_domain],
                                                           {'fields': ['id'], 'limit': 1})
            for record in data_logruntime:
                record_id = record['id']
                self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                             self.source_client.password, 'log.code.runtime', 'unlink', [[record_id]])
                print(f"Deleted record with ID: {record_id}")
        except Exception as e:
            print(f"An error occurred while deleting data: {e}")

    def create_log_note_success(self, record, start_time, end_time, duration, modul, write_date):
        try:
            log_record = self.log_record_success(record, start_time, end_time, duration, modul, write_date)
            self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                         self.source_client.password, 'log.note', 'create', [log_record])
            print(f"Data log note yang masuk: {log_record}")
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def create_log_note_update_success(self, record, record_id, updated_fields, start_time, end_time, duration, modul, write_date):
        try:
            log_record = self.log_update_record_success(record, record_id, updated_fields, start_time, end_time, duration, modul, write_date)
            self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                         self.source_client.password, 'log.note', 'create', [log_record])
            print(f"Data log note yang masuk: {log_record}")
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def create_log_note_failed(self, record, modul, sync_status, write_date):
        try:
            log_record = self.log_record_failed(record, modul, sync_status, write_date)
            log_record_existing = self.get_log_note_failed(log_record['vit_trx_key'], log_record['vit_sync_desc'])
            if not log_record_existing:
                self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                            self.source_client.password, 'log.note', 'create', [log_record])
                print(f"Data log note yang masuk: {log_record}")
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def get_log_note_failed(self, key, desc):
        log_note_failed = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password, 'log.note',
                                                        'search_read', [[['vit_trx_key', '=', key], ['vit_sync_desc', '=', desc] , ['vit_sync_status', '=', 'Failed']]])
        return log_note_failed

class SetLogSS:
    def __init__(self, target_client):
        self.target_client = target_client

    def log_record_success(self, record, start_time, end_time, duration, modul, write_date):
        gmt_7_now = datetime.now() - timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        gmt_7_start_time = datetime.fromtimestamp(start_time) - timedelta(hours=7)
        gmt_7_end_time = datetime.fromtimestamp(end_time) - timedelta(hours=7)
        record_log_success = {
            'vit_doc_type': modul,
            'vit_trx_key': record.get('name'),
            'vit_trx_date': write_date,
            'vit_sync_date': gmt_7_now.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_sync_status': 'Success',
            'vit_sync_desc': f"Data yang masuk: {record}",
            'vit_start_sync': gmt_7_start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_end_sync': gmt_7_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_duration' : f"{duration:.2f} second"
        }
        return record_log_success
    
    def log_update_record_success(self, record, record_id, updated_fields, start_time, end_time, duration, modul, write_date):
        gmt_7_now = datetime.now() - timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        gmt_7_start_time = datetime.fromtimestamp(start_time) - timedelta(hours=7)
        gmt_7_end_time = datetime.fromtimestamp(end_time) - timedelta(hours=7)
        record_log_success = {
            'vit_doc_type': f"Update: {modul}",
            'vit_trx_key': record.get('name'),
            'vit_trx_date': write_date,
            'vit_sync_date': gmt_7_now.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_sync_status': 'Success',
            'vit_sync_desc': f"Data yang diupdate: id {record_id},  {updated_fields}",
            'vit_start_sync': gmt_7_start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_end_sync': gmt_7_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_duration' : f"{duration:.2f} second"
        }
        return record_log_success
    
    def log_record_failed(self, record, modul, sync_status, write_date):
        gmt_7_now = datetime.now() - timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        
        if isinstance(sync_status, str) is False:
            sync_status = sync_status.args[0]
            sync_status = sync_status['data']['message']

        record_log_failed = {
            'vit_doc_type': modul,
            'vit_trx_key': record.get('name'),
            'vit_trx_date': write_date,
            'vit_sync_date': gmt_7_now.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_sync_status': 'Failed',
            'vit_sync_desc': sync_status
        }
        return record_log_failed

    def delete_data_log(self):
        try:
            filter_domain = [['vit_code_type', '=', 'Master']]
            data_logruntime = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                           self.target_client.uid, self.target_client.password,
                                                           'log.code.runtime', 'search_read', [filter_domain],
                                                           {'fields': ['id'], 'limit': 1})
            for record in data_logruntime:
                record_id = record['id']
                self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                             self.target_client.password, 'log.code.runtime', 'unlink', [[record_id]])
                print(f"Deleted record with ID: {record_id}")
        except Exception as e:
            print(f"An error occurred while deleting data: {e}")

    def create_log_note_success(self, record, start_time, end_time, duration, modul, write_date):
        try:
            log_record = self.log_record_success(record, start_time, end_time, duration, modul, write_date)
            self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                         self.target_client.password, 'log.note', 'create', [log_record])
            print(f"Data log note yang masuk: {log_record}")
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def create_log_note_update_success(self, record, record_id, updated_fields, start_time, end_time, duration, modul, write_date):
        try:
            log_record = self.log_update_record_success(record, record_id, updated_fields, start_time, end_time, duration, modul, write_date)
            self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                         self.target_client.password, 'log.note', 'create', [log_record])
            print(f"Data log note yang masuk: {log_record}")
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def create_log_note_failed(self, record, modul, sync_status, write_date):
        try:
            log_record = self.log_record_failed(record, modul, sync_status, write_date)
            log_record_existing = self.get_log_note_failed(log_record['vit_trx_key'], log_record['vit_sync_desc'])
            if not log_record_existing:
                self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                            self.target_client.password, 'log.note', 'create', [log_record])
                print(f"Data log note yang masuk: {log_record}")
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def get_log_note_failed(self, key, desc):
        log_note_failed = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password, 'log.note',
                                                        'search_read', [[['vit_trx_key', '=', key], ['vit_sync_desc', '=', desc] , ['vit_sync_status', '=', 'Failed']]])
        return log_note_failed
