import time
from datetime import datetime, timedelta
import pytz
import re
import concurrent.futures

# kalau ada case store nya beda zona waktu gimana
class DataTransaksiMCtoSS:
    def __init__(self, source_client, target_client):
        self.source_client = source_client
        self.target_client = target_client
        self.set_log_mc = SetLogMC(self.source_client)
        self.set_log_ss = SetLogSS(self.target_client)

    # Master Console --> Store Server
    # Store Server --> Master Console
    def update_loyalty_point_mc_to_ss(self, model_name, fields, description, date_from, date_to):
        if isinstance(date_from, datetime):
            date_from = date_from.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(date_to, datetime):
            date_to = date_to.strftime('%Y-%m-%d %H:%M:%S')
            
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
                                                        [[['program_id', '=', int(programs)], ['is_updated', '=', True]]],
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

    # Master Console --> Store Server
    # Store Server --> Master Console
    def transfer_discount_loyalty(self, model_name, fields, description, date_from, date_to):
        try:
            # Ambil data dari sumber
            discount_loyalty = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            model_name, 'search_read',
                                                            [[['active', '=', True], ['is_integrated', '=', False]]],
                                                            {'fields': fields})
            if not discount_loyalty:
                print("Tidak ada discount/loyalty yang ditemukan untuk ditransfer.")
                return

            # Fetch existing discount/loyalty programs in target
            discount_names = [record['name'] for record in discount_loyalty]
            existing_discount_loyalty = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'loyalty.program', 'search_read',
                [[['vit_trxid', 'in', discount_names], ['active', '=', True]]],
                {'fields': ['id', 'vit_trxid']}
            )
            existing_discount_dict = {record['vit_trxid']: record['id'] for record in existing_discount_loyalty}

            order_ids = [record['id'] for record in discount_loyalty]
            # Fetch all reward and rule lines for all programs at once
            reward_ids_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            'loyalty.reward', 'search_read',
                                                            [[['program_id', 'in', order_ids]]],
                                                            {'fields': ['reward_type', 'discount', 'discount_applicability', 'discount_max_amount', 'required_points', 'description', 'discount_mode', 'discount_product_domain', 'discount_product_ids', 'discount_product_category_id', 'vit_trxid', 'program_id']})

            rule_ids_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'loyalty.rule', 'search_read',
                                                        [[['program_id', 'in', order_ids]]],
                                                        {'fields': ['minimum_qty', 'minimum_amount', 'reward_point_amount', 'reward_point_mode', 'product_domain', 'product_ids', 'product_category_id', 'minimum_amount_tax_mode', 'vit_trxid', 'program_id']})

            # Collect all product and category IDs
            product_ids_reward = [product_id for product in reward_ids_lines for product_id in product.get('discount_product_ids', [])]
            product_ids_rule = [product_id for product in rule_ids_lines for product_id in product.get('product_ids', [])]
            category_ids_reward = [record.get('discount_product_category_id')[0] if isinstance(record.get('discount_product_category_id'), list) else record.get('discount_product_category_id') for record in reward_ids_lines if record.get('discount_product_category_id')]
            category_ids_rule = [record.get('product_category_id')[0] if isinstance(record.get('product_category_id'), list) else record.get('product_category_id') for record in rule_ids_lines if record.get('product_category_id')]

            currency_ids = [record.get('currency_id')[0] if isinstance(record.get('currency_id'), list) else record.get('currency_id') for record in discount_loyalty if record.get('currency_id')]
            pricelist_ids = [pricelist_id for record in discount_loyalty for pricelist_id in record.get('pricelist_ids', [])]
            pos_config_ids = [config_id for record in discount_loyalty for config_id in record.get('pos_config_ids', [])]

            products_source_reward = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'product.product', 'search_read',
                [[['id', 'in', product_ids_reward]]],
                {'fields': ['id', 'default_code']}
            )
            products_source_rule = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'product.product', 'search_read',
                [[['id', 'in', product_ids_rule]]],
                {'fields': ['id', 'default_code']}
            )
            categories_source_reward = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'product.category', 'search_read',
                [[['id', 'in', category_ids_reward]]],
                {'fields': ['id', 'complete_name']}
            )
            categories_source_rule = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'product.category', 'search_read',
                [[['id', 'in', category_ids_rule]]],
                {'fields': ['id', 'complete_name']}
            )
            currencies_source = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'res.currency', 'search_read',
                [[['id', 'in', currency_ids]]],
                {'fields': ['id', 'name']}
            )
            pricelists_source = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'product.pricelist', 'search_read',
                [[['id', 'in', pricelist_ids]]],
                {'fields': ['id', 'name']}
            )
            pos_configs_source = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'pos.config', 'search_read',
                [[['id', 'in', pos_config_ids]]],
                {'fields': ['id', 'name']}
            )
            # Fetch corresponding data from target
            products_target_reward = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'product.product', 'search_read',
                [[['default_code', 'in', [product['default_code'] for product in products_source_reward]]]],
                {'fields': ['id', 'default_code']}
            )
            products_target_rule = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'product.product', 'search_read',
                [[['default_code', 'in', [product['default_code'] for product in products_source_rule]]]],
                {'fields': ['id', 'default_code']}
            )
            categories_target_reward = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'product.category', 'search_read',
                [[['complete_name', 'in', [category['complete_name'] for category in categories_source_reward]]]],
                {'fields': ['id', 'complete_name']}
            )
            categories_target_rule = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'product.category', 'search_read',
                [[['complete_name', 'in', [category['complete_name'] for category in categories_source_rule]]]],
                {'fields': ['id', 'complete_name']}
            )
            currencies_target = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'res.currency', 'search_read',
                [[['name', 'in', [currency['name'] for currency in currencies_source]]]],
                {'fields': ['id', 'name']}
            )
            pricelists_target = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'product.pricelist', 'search_read',
                [[['name', 'in', [pricelist['name'] for pricelist in pricelists_source]]]],
                {'fields': ['id', 'name']}
            )
            pos_configs_target = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'pos.config', 'search_read',
                [[['name', 'in', [pos_config['name'] for pos_config in pos_configs_source]]]],
                {'fields': ['id', 'name']}
            )

            product_dict_reward = {product['default_code']: product['id'] for product in products_target_reward}
            product_dict_rule = {product['default_code']: product['id'] for product in products_target_rule}
            category_dict_reward = {category['complete_name']: category['id'] for category in categories_target_reward}
            category_dict_rule = {category['complete_name']: category['id'] for category in categories_target_rule}
            currency_dict = {currency['name']: currency['id'] for currency in currencies_target}
            pricelist_dict = {pricelist['name']: pricelist['id'] for pricelist in pricelists_target}
            pos_config_dict = {pos_config['name']: pos_config['id'] for pos_config in pos_configs_target}

            def process_create_discount(record):
                if record['vit_trxid'] in existing_discount_dict:
                    return
                current_reward_lines = [line for line in reward_ids_lines if line['program_id'][0] == record['id']]
                current_rule_lines = [line for line in rule_ids_lines if line['program_id'][0] == record['id']]

                discount_loyalty_line_ids = []
                for line in current_reward_lines:
                    if isinstance(line, dict):
                        reward_product_ids = line.get('discount_product_ids', [])
                        reward_target_product_ids = [product_dict_reward.get(product['default_code']) for product in products_source_reward if product['id'] in reward_product_ids]

                        reward_source_category_id = line.get('discount_product_category_id')
                        if isinstance(reward_source_category_id, list) and len(reward_source_category_id) == 2:
                            reward_source_category_name = reward_source_category_id[1]
                        else:
                            reward_source_category_name = next((category['complete_name'] for category in categories_source_reward if category['id'] == reward_source_category_id), None)

                        reward_target_category_id = category_dict_reward.get(reward_source_category_name)

                    discount_line_data = {
                        'reward_type': line.get('reward_type'),
                        'discount': line.get('discount'),
                        'discount_applicability': line.get('discount_applicability'),
                        'discount_max_amount': line.get('discount_max_amount'),
                        'required_points': line.get('required_points'),
                        'description': line.get('description'),
                        'discount_mode': line.get('discount_mode'),
                        'discount_product_ids': [(6, 0, reward_target_product_ids)],
                        'discount_product_category_id': reward_target_category_id,
                        'vit_trxid': record.get('name')
                    }
                    discount_loyalty_line_ids.append((0, 0, discount_line_data))

                rule_ids = []
                for rule in current_rule_lines:
                    if isinstance(rule, dict):
                        rule_product_ids = rule.get('product_ids', [])
                        rule_target_product_ids = [product_dict_rule.get(product['default_code']) for product in products_source_rule if product['id'] in rule_product_ids]

                        rule_source_category_id = rule.get('product_category_id')
                        if isinstance(rule_source_category_id, list) and len(rule_source_category_id) == 2:
                            rule_source_category_name = rule_source_category_id[1]
                        else:
                            rule_source_category_name = next((category['complete_name'] for category in categories_source_rule if category['id'] == rule_source_category_id), None)

                        rule_target_category_id = category_dict_rule.get(rule_source_category_name)

                    rule_data = {
                        'minimum_qty': rule.get('minimum_qty'),
                        'minimum_amount': rule.get('minimum_amount'),
                        'reward_point_amount': rule.get('reward_point_amount'),
                        'reward_point_mode': rule.get('reward_point_mode'),
                        'product_domain': rule.get('product_domain'),
                        'product_ids': rule_target_product_ids,
                        'minimum_amount_tax_mode': rule.get('minimum_amount_tax_mode'),
                        'product_category_id': rule_target_category_id,
                        'vit_trxid': record.get('name'),
                    }
                    rule_ids.append((0, 0, rule_data))

                currency_id = record.get('currency_id')
                currency_id = currency_id[0] if isinstance(currency_id, list) else currency_id
                currency_name = next((currency['name'] for currency in currencies_source if currency['id'] == currency_id), None)
                currency_target_id = currency_dict.get(currency_name)

                source_pricelist_ids = record.get('pricelist_ids', [])
                target_pricelist_ids = [pricelist_dict.get(pricelist['name']) for pricelist in pricelists_source if pricelist['id'] in source_pricelist_ids]

                source_pos_config_ids = record.get('pos_config_ids', [])
                target_pos_config_ids = [pos_config_dict.get(pos_config['name']) for pos_config in pos_configs_source if pos_config['id'] in source_pos_config_ids]

                # Siapkan data untuk loyalty.program di target_client
                discount_data = {
                    'name': record.get('name'),
                    'program_type': record.get('program_type'),
                    'currency_id': currency_target_id,
                    'portal_point_name': record.get('portal_point_name'),
                    'portal_visible': record.get('portal_visible'),
                    'trigger': record.get('trigger'),
                    'applies_on': record.get('applies_on'),
                    'date_from': record.get('date_from'),
                    'date_to': record.get('date_to'),
                    'vit_trxid': record.get('name'),
                    'id_mc': record.get('id'),
                    'pricelist_ids': target_pricelist_ids,
                    'limit_usage': record.get('limit_usage'),
                    'is_integrated': True,
                    'pos_ok': record.get('pos_ok'),
                    'sale_ok': record.get('sale_ok'),
                    'pos_config_ids': target_pos_config_ids,
                    'reward_ids': discount_loyalty_line_ids,
                    'rule_ids': rule_ids,
                }
                try:
                    start_time = time.time()
                    # Buat loyalty.program baru di target_client
                    new_discount_data = self.target_client.call_odoo(
                        'object', 'execute_kw', self.target_client.db,
                        self.target_client.uid, self.target_client.password,
                        'loyalty.program', 'create',
                        [discount_data]
                    )
                    index_store_ids = record.get('index_store', [])
                    # Set the index_store field with setting.config IDs
                    setting_config_ids = self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'setting.config', 'search_read',
                        [[['vit_config_server', '=', 'ss'], ['vit_linked_server', '=', True]]],
                        {'fields': ['id']}
                    )
                    setting_config_ids = [config['id'] for config in setting_config_ids]
                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'loyalty.program', 'write',
                        [[record['id']], {'vit_trxid': record['name'],
                                          'index_store': [(6, 0, setting_config_ids)],
                                          'reward_ids': [(1, line['id'], {'vit_trxid': record['name']}) for line in current_reward_lines],
                                          'rule_ids': [(1, rule['id'], {'vit_trxid': record['name']}) for rule in current_rule_lines],}]
                    )
                    print(f"Field is_integrated set to True for loyalty program ID {record['id']}.")

                    if len(index_store_ids) == len(setting_config_ids):
                        self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'loyalty.program', 'write',
                        [[record['id']], {'is_integrated': True, 'is_updated': False, 'index_store': [(5, 0, 0)]}])

                    else:
                        self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'loyalty.program', 'write',
                        [[record['id']], {'is_integrated': False}])

                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])

                    message_succes = f"Discount baru telah dibuat dengan ID: {new_discount_data}"
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Discount/Loyalty', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Discount/Loyalty', write_date)
                except Exception as e:
                    message_exception = f"Terjadi kesalahan saat membuat discount baru: {e}"
                    self.set_log_ss.create_log_note_failed(record, 'Discount/Loyalty', message_exception, write_date)
            
            batch_size = 100
            for i in range(0, len(discount_loyalty), batch_size):
                batch = discount_loyalty[i:i + batch_size]
                with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                    futures = [executor.submit(process_create_discount, record) for record in batch]
                results = concurrent.futures.wait(futures)

        except Exception as e:
            print(f"Error during processing: {e}")
        
    def update_discount_loyalty(self, model_name, fields, description, date_from, date_to):
        try:
            # Ambil data dari sumber
            discount_loyalty = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            model_name, 'search_read',
                                                            [[['is_integrated', '=', False], ['is_updated', '=', True], ['active', '=', True]]],
                                                            {'fields': fields})
            if not discount_loyalty:
                print("Tidak ada discount/loyalty yang ditemukan untuk ditransfer.")
                return

            # Fetch existing discount/loyalty programs in target
            discount_names = [record['vit_trxid'] for record in discount_loyalty]
            existing_discount_loyalty = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'loyalty.program', 'search_read',
                [[['vit_trxid', 'in', discount_names]]],
                {'fields': ['id', 'vit_trxid']}
            )
            existing_discount_dict = {record['vit_trxid']: record['id'] for record in existing_discount_loyalty}

            order_ids = [record['id'] for record in discount_loyalty]

            # Fetch all reward and rule lines for all programs at once
            reward_ids_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                            self.source_client.uid, self.source_client.password,
                                                            'loyalty.reward', 'search_read',
                                                            [[['program_id', 'in', order_ids]]],
                                                            {'fields': ['reward_type', 'discount', 'discount_applicability', 'discount_max_amount', 'required_points', 'description', 'discount_mode', 'discount_product_domain', 'discount_product_ids', 'discount_product_category_id', 'vit_trxid', 'program_id']})

            rule_ids_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'loyalty.rule', 'search_read',
                                                        [[['program_id', 'in', order_ids]]],
                                                        {'fields': ['minimum_qty', 'minimum_amount', 'reward_point_amount', 'reward_point_mode', 'product_domain', 'product_ids', 'product_category_id', 'minimum_amount_tax_mode', 'vit_trxid', 'program_id']})

            # Collect all product and category IDs
            product_ids_reward = [product_id for product in reward_ids_lines for product_id in product.get('discount_product_ids', [])]
            product_ids_rule = [product_id for product in rule_ids_lines for product_id in product.get('product_ids', [])]
            category_ids_reward = [record.get('discount_product_category_id')[0] if isinstance(record.get('discount_product_category_id'), list) else record.get('discount_product_category_id') for record in reward_ids_lines if record.get('discount_product_category_id')]
            category_ids_rule = [record.get('product_category_id')[0] if isinstance(record.get('product_category_id'), list) else record.get('product_category_id') for record in rule_ids_lines if record.get('product_category_id')]

            currency_ids = [record.get('currency_id')[0] if isinstance(record.get('currency_id'), list) else record.get('currency_id') for record in discount_loyalty if record.get('currency_id')]
            pricelist_ids = [pricelist_id for record in discount_loyalty for pricelist_id in record.get('pricelist_ids', [])]
            pos_config_ids = [config_id for record in discount_loyalty for config_id in record.get('pos_config_ids', [])]
            # Fetch all necessary data from source
            products_source_reward = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'product.product', 'search_read',
                [[['id', 'in', product_ids_reward]]],
                {'fields': ['id', 'default_code']}
            )

            products_source_rule = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'product.product', 'search_read',
                [[['id', 'in', product_ids_rule]]],
                {'fields': ['id', 'default_code']}
            )

            categories_source_reward = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'product.category', 'search_read',
                [[['id', 'in', category_ids_reward]]],
                {'fields': ['id', 'complete_name']}
            )

            categories_source_rule = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'product.category', 'search_read',
                [[['id', 'in', category_ids_rule]]],
                {'fields': ['id', 'complete_name']}
            )

            currencies_source = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'res.currency', 'search_read',
                [[['id', 'in', currency_ids]]],
                {'fields': ['id', 'name']}
            )
            pricelists_source = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'product.pricelist', 'search_read',
                [[['id', 'in', pricelist_ids]]],
                {'fields': ['id', 'name']}
            )

            pos_configs_source = self.source_client.call_odoo(
                'object', 'execute_kw', self.source_client.db,
                self.source_client.uid, self.source_client.password,
                'pos.config', 'search_read',
                [[['id', 'in', pos_config_ids]]],
                {'fields': ['id', 'name']}
            )
            # Fetch corresponding data from target
            products_target_reward = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'product.product', 'search_read',
                [[['default_code', 'in', [product['default_code'] for product in products_source_reward]]]],
                {'fields': ['id', 'default_code']}
            )

            products_target_rule = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'product.product', 'search_read',
                [[['default_code', 'in', [product['default_code'] for product in products_source_rule]]]],
                {'fields': ['id', 'default_code']}
            )

            categories_target_reward = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'product.category', 'search_read',
                [[['complete_name', 'in', [category['complete_name'] for category in categories_source_reward]]]],
                {'fields': ['id', 'complete_name']}
            )

            categories_target_rule = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'product.category', 'search_read',
                [[['complete_name', 'in', [category['complete_name'] for category in categories_source_rule]]]],
                {'fields': ['id', 'complete_name']}
            )

            currencies_target = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'res.currency', 'search_read',
                [[['name', 'in', [currency['name'] for currency in currencies_source]]]],
                {'fields': ['id', 'name']}
            )

            pricelists_target = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'product.pricelist', 'search_read',
                [[['name', 'in', [pricelist['name'] for pricelist in pricelists_source]]]],
                {'fields': ['id', 'name']}
            )

            pos_configs_target = self.target_client.call_odoo(
                'object', 'execute_kw', self.target_client.db,
                self.target_client.uid, self.target_client.password,
                'pos.config', 'search_read',
                [[['name', 'in', [pos_config['name'] for pos_config in pos_configs_source]]]],
                {'fields': ['id', 'name']}
            )

            # Create mapping dictionaries
            product_dict_reward = {product['default_code']: product['id'] for product in products_target_reward}
            product_dict_rule = {product['default_code']: product['id'] for product in products_target_rule}
            category_dict_reward = {category['complete_name']: category['id'] for category in categories_target_reward}
            category_dict_rule = {category['complete_name']: category['id'] for category in categories_target_rule}
            currency_dict = {currency['name']: currency['id'] for currency in currencies_target}
            pricelist_dict = {pricelist['name']: pricelist['id'] for pricelist in pricelists_target}
            pos_config_dict = {pos_config['name']: pos_config['id'] for pos_config in pos_configs_target}

            def process_update_discount(record):
                program_id = existing_discount_dict[record['vit_trxid']]

                existing_reward_lines = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'loyalty.reward', 'search_read',
                                                                    [[['program_id', '=', program_id]]],
                                                                    {'fields': ['id', 'reward_type', 'discount', 'discount_applicability', 'discount_max_amount', 'required_points', 'description', 'discount_product_ids', 'discount_product_category_id', 'vit_trxid']})
                existing_rule_lines = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'loyalty.rule', 'search_read',
                                                                [[['program_id', '=', program_id]]],
                                                                {'fields': ['id', 'minimum_qty', 'minimum_amount', 'reward_point_amount', 'reward_point_mode', 'product_domain', 'product_ids', 'product_category_id', 'vit_trxid']})

                # Filter reward_ids_lines and rule_ids_lines for the current record
                current_reward_lines = [line for line in reward_ids_lines if line['program_id'][0] == record['id']]
                current_rule_lines = [line for line in rule_ids_lines if line['program_id'][0] == record['id']]

                discount_loyalty_line_ids = []
                for line in current_reward_lines:
                    if isinstance(line, dict):
                        reward_product_ids = line.get('discount_product_ids', [])
                        reward_target_product_ids = [product_dict_reward.get(product['default_code']) for product in products_source_reward if product['id'] in reward_product_ids]

                        reward_source_category_id = line.get('product_category_id')
                        if isinstance(reward_source_category_id, list) and len(reward_source_category_id) == 2:
                            reward_source_category_name = reward_source_category_id[1]
                        else:
                            reward_source_category_name = next((category['complete_name'] for category in categories_source_reward if category['id'] == reward_source_category_id), None)

                        reward_target_category_id = category_dict_reward.get(reward_source_category_name)

                        existing_line = next((x for x in existing_reward_lines if x['vit_trxid'] == line['vit_trxid']), None)
                        if existing_line:
                            if (existing_line['reward_type'] != line['reward_type'] or
                                existing_line['discount'] != line['discount'] or
                                existing_line['discount_applicability'] != line['discount_applicability'] or
                                existing_line['discount_max_amount'] != line['discount_max_amount'] or
                                existing_line['required_points'] != line['required_points'] or
                                existing_line['description'] != line['description'] or
                                existing_line['discount_product_ids'] != [(6, 0, reward_target_product_ids)] or
                                existing_line['discount_product_category_id'] != reward_target_category_id):
                                discount_line_data = (1, existing_line['id'], {
                                    'reward_type': line.get('reward_type'),
                                    'discount': line.get('discount'),
                                    'discount_applicability': line.get('discount_applicability'),
                                    'discount_max_amount': line.get('discount_max_amount'),
                                    'required_points': line.get('required_points'),
                                    'description': line.get('description'),
                                    'vit_trxid': record.get('name'),
                                    'discount_mode': line.get('discount_mode'),
                                    'discount_product_ids': [(6, 0, reward_target_product_ids)],
                                    'discount_product_category_id': reward_target_category_id,
                                })
                                discount_loyalty_line_ids.append(discount_line_data)
                        else:
                            discount_line_data = (0, 0, {
                                'reward_type': line.get('reward_type'),
                                'discount': line.get('discount'),
                                'discount_applicability': line.get('discount_applicability'),
                                'discount_max_amount': line.get('discount_max_amount'),
                                'required_points': line.get('required_points'),
                                'description': line.get('description'),
                                'vit_trxid': record.get('name'),
                                'discount_mode': line.get('discount_mode'),
                                'discount_product_ids': [(6, 0, reward_target_product_ids)],
                                'discount_product_category_id': reward_target_category_id,
                            })
                            discount_loyalty_line_ids.append(discount_line_data)

                rule_ids = []
                for rule in current_rule_lines:
                    if isinstance(rule, dict):
                        rule_product_ids = rule.get('product_ids', [])
                        rule_target_product_ids = [product_dict_rule.get(product['default_code']) for product in products_source_rule if product['id'] in rule_product_ids]

                        rule_source_category_id = rule.get('product_category_id')
                        if isinstance(rule_source_category_id, list) and len(rule_source_category_id) == 2:
                            rule_source_category_name = rule_source_category_id[1]
                        else:
                            rule_source_category_name = next((category['complete_name'] for category in categories_source_rule if category['id'] == rule_source_category_id), None)

                        rule_target_category_id = category_dict_rule.get(rule_source_category_name)

                        existing_rule_line = next((x for x in existing_rule_lines if x['vit_trxid'] == rule['vit_trxid']), None)
                        if existing_rule_line:
                            if (existing_rule_line['minimum_qty'] != rule['minimum_qty'] or
                                existing_rule_line['minimum_amount'] != rule['minimum_amount'] or
                                existing_rule_line['reward_point_amount'] != rule['reward_point_amount'] or
                                existing_rule_line['reward_point_mode'] != rule['reward_point_mode'] or
                                existing_rule_line['product_domain'] != rule['product_domain'] or
                                existing_rule_line['product_ids'] != rule_target_product_ids or
                                existing_rule_line['product_category_id'] != rule_target_category_id):
                                rule_data = (1, existing_rule_line['id'], {
                                    'minimum_qty': rule.get('minimum_qty'),
                                    'minimum_amount': rule.get('minimum_amount'),
                                    'reward_point_amount': rule.get('reward_point_amount'),
                                    'reward_point_mode': rule.get('reward_point_mode'),
                                    'product_domain': rule.get('product_domain'),
                                    'product_ids': rule_target_product_ids,
                                    'vit_trxid': record.get('name'),
                                    'minimum_amount_tax_mode': rule.get('minimum_amount_tax_mode'),
                                    'product_category_id': rule_target_category_id,
                                })
                                rule_ids.append(rule_data)
                        else:
                            rule_data = (0, 0, {
                                'minimum_qty': rule.get('minimum_qty'),
                                'minimum_amount': rule.get('minimum_amount'),
                                'reward_point_amount': rule.get('reward_point_amount'),
                                'reward_point_mode': rule.get('reward_point_mode'),
                                'product_domain': rule.get('product_domain'),
                                'product_ids': rule_target_product_ids,
                                'vit_trxid': record.get('name'),
                                'minimum_amount_tax_mode': rule.get('minimum_amount_tax_mode'),
                                'product_category_id': rule_target_category_id,
                            })
                            rule_ids.append(rule_data)

                currency_id = record.get('currency_id')
                currency_id = currency_id[0] if isinstance(currency_id, list) else currency_id
                currency_name = next((currency['name'] for currency in currencies_source if currency['id'] == currency_id), None)
                currency_target_id = currency_dict.get(currency_name)

                source_pricelist_ids = record.get('pricelist_ids', [])
                target_pricelist_ids = [pricelist_dict.get(pricelist['name']) for pricelist in pricelists_source if pricelist['id'] in source_pricelist_ids]

                source_pos_config_ids = record.get('pos_config_ids', [])
                target_pos_config_ids = [pos_config_dict.get(pos_config['name']) for pos_config in pos_configs_source if pos_config['id'] in source_pos_config_ids]

                update_values = {
                    'name': record.get('name'),
                    'program_type': record.get('program_type'),
                    'currency_id': currency_target_id,
                    'portal_point_name': record.get('portal_point_name'),
                    'portal_visible': record.get('portal_visible'),
                    'trigger': record.get('trigger'),
                    'applies_on': record.get('applies_on'),
                    'date_from': record.get('date_from'),
                    'date_to': record.get('date_to'),
                    'vit_trxid': record.get('vit_trxid'),
                    'id_mc': record.get('id'),
                    'pricelist_ids': target_pricelist_ids,
                    'limit_usage': record.get('limit_usage'),
                    'is_integrated': True,
                    'pos_config_ids': target_pos_config_ids,
                    'pos_ok': record.get('pos_ok'),
                    'sale_ok': record.get('sale_ok'),
                    'reward_ids': discount_loyalty_line_ids,
                    'rule_ids': rule_ids,
                }

                try:
                    self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                self.target_client.uid, self.target_client.password,
                                                model_name, 'write',
                                                [[program_id], update_values])
                    print(f"Record dengan ID {record['id']} telah diupdate.")

                    index_store_ids = record.get('index_store', [])
                    # Set the index_store field with setting.config IDs
                    setting_config_ids = self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'setting.config', 'search_read',
                        [[['vit_config_server', '=', 'ss'], ['vit_linked_server', '=', True]]],
                        {'fields': ['id']}
                    )
                    setting_config_ids = [config['id'] for config in setting_config_ids]
                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'loyalty.program', 'write',
                        [[record['id']], {'vit_trxid': record['name'],
                                          'index_store': [(6, 0, setting_config_ids)],
                                          'reward_ids': [(1, line['id'], {'vit_trxid': record['name']}) for line in current_reward_lines],
                                          'rule_ids': [(1, rule['id'], {'vit_trxid': record['name']}) for rule in current_rule_lines],}]
                    )
                    print(f"Field is_integrated set to True for loyalty program ID {record['id']}.")

                    if len(index_store_ids) == len(setting_config_ids):
                        self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'loyalty.program', 'write',
                        [[record['id']], {'is_integrated': True, 'is_updated': True, 'index_store': [(5, 0, 0)]}])

                    else:
                        self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'loyalty.program', 'write',
                        [[record['id']], {'is_integrated': False}])

                    write_date = self.get_write_date(model_name, gr['id'])

                    # self.source_client.call_odoo(
                    #     'object', 'execute_kw', self.source_client.db,
                    #     self.source_client.uid, self.source_client.password,
                    #     'loyalty.program', 'write',
                    #     [[record['id']], {'vit_trxid': record.get('name')}]
                    # )

                    print(f"Discount baru telah dibuat diupdate: {record['name']}")
                except Exception as e:
                    message_exception = f"Terjadi kesalahan saat membuat discount baru: {e}"
                    self.set_log_ss.create_log_note_failed(record, 'Master Discount & Promo', message_exception, write_date)
                    self.set_log_mc.create_log_note_failed(record, 'Master Discount & Promo', message_exception, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(process_update_discount, record) for record in discount_loyalty]
                concurrent.futures.wait(futures)

        except Exception as e:
            print(f"Error during processing: {e}")

    def transfer_loyalty_point_mc_to_ss(self, model_name, fields, description, date_from, date_to):
        if isinstance(date_from, datetime):
            date_from = date_from.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(date_to, datetime):
            date_to = date_to.strftime('%Y-%m-%d %H:%M:%S')
                                   
        id_program = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                    self.source_client.uid, self.source_client.password,
                                                    model_name, 'search_read',
                                                    [[['active', '=', True], ['is_integrated', '=', True], ['program_type', '=', 'coupons']]],
                                                    {'fields': fields})
        
        if not id_program:
            print("Tidak ada promo")
            return

        for res in id_program:
            programs = res.get('id', False)

            # Ambil data dari sumber
            loyalty_points = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'loyalty.card', 'search_read',
                                                        [[['program_id', '=', programs]]],
                                                        {'fields': ['code', 'points_display', 'expiration_date', 'program_id', 'currency_id', 'partner_id', 'source_pos_order_id', 'points']})
            # if not loyalty_points:
            #     print("Tidak ada discount/loyalty yang ditemukan untuk ditransfer.")
            #     return

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
                order_ref = pos_order_map.get(record.get('source_pos_order_id')[0]) if record.get('source_pos_order_id') else False
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
                existing_loyalty_points = self.target_client.call_odoo(
                    'object', 'execute_kw', self.target_client.db,
                    self.target_client.uid, self.target_client.password,
                    'loyalty.card', 'search_read',
                    [[['code', '=', record['code']]]],
                    {'fields': ['id']}
                )

                if not existing_loyalty_points:
                    code = record.get('code')
                    expiration_date = record.get('expiration_date')
                    points = record.get('points')

                    source_pos_order_id = record.get('source_pos_order_id')
                    order_id = order_references.get(source_pos_order_id[0]) if source_pos_order_id else False

                    program_id = record.get('program_id')
                    program_id_new = program_id_sets.get(program_id[0]) if program_id else False

                    partner_id = record.get('partner_id')
                    partner_id_list_new = partner_id_sets.get(partner_id[0]) if partner_id else False

                    data_loyalty = {
                        'code': code,
                        'expiration_date': expiration_date,
                        'points': points,
                        'source_pos_order_id': order_id,
                        'program_id': program_id_new,
                        'partner_id': partner_id_list_new
                    }

                    try:
                        new_loyalty_data = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                        self.target_client.uid, self.target_client.password,
                                                                        'loyalty.card', 'create',
                                                                        [data_loyalty])
                        print(f"Loyalty telah dibuat dengan ID: {new_loyalty_data}")

                        index_store_ids = record.get('index_store', [])
                        # Set the index_store field with setting.config IDs
                        setting_config_ids = self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'setting.config', 'search_read',
                            [[['vit_config_server', '=', 'ss'], ['vit_linked_server', '=', True]]],
                            {'fields': ['id']}
                        )
                        setting_config_ids = [config['id'] for config in setting_config_ids]
                        self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'loyalty.card', 'write',
                            [[record['id']], {'vit_trxid': record['name'],
                                            'index_store': [(6, 0, setting_config_ids)]}]
                        )
                        print(f"Field is_integrated set to True for loyalty card ID {record['id']}.")

                        if len(index_store_ids) == len(setting_config_ids):
                            self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'loyalty.card', 'write',
                            [[record['id']], {'is_integrated': True, 'is_updated': False, 'index_store': [(5, 0, 0)]}])

                        else:
                            self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'loyalty.card', 'write',
                            [[record['id']], {'is_integrated': False}])
                    except Exception as e:
                        print(f"Terjadi kesalahan saat membuat loyalty baru: {e}")

            # Process loyalty points in batches of 100
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                for i in range(0, len(loyalty_points), 100):
                    batch = loyalty_points[i:i + 100]
                    executor.map(process_loyalty_point, batch)

    def update_loyalty_point_mc_to_ss(self, model_name, fields, description, date_from, date_to):
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
                                                        [[['program_id', '=', int(programs)], ['is_updated', '=', True]]],
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

                        index_store_ids = record.get('index_store', [])
                        # Set the index_store field with setting.config IDs
                        setting_config_ids = self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'setting.config', 'search_read',
                            [[['vit_config_server', '=', 'ss'], ['vit_linked_server', '=', True]]],
                            {'fields': ['id']}
                        )
                        setting_config_ids = [config['id'] for config in setting_config_ids]
                        self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'loyalty.card', 'write',
                            [[record['id']], {'vit_trxid': record['name'],
                                            'index_store': [(6, 0, setting_config_ids)]}]
                        )
                        print(f"Field is_integrated set to True for loyalty program ID {record['id']}.")

                        if len(index_store_ids) == len(setting_config_ids):
                            self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'loyalty.card', 'write',
                            [[record['id']], {'is_updated': True, 'index_store': [(5, 0, 0)]}])

                        else:
                            self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'loyalty.card', 'write',
                            [[record['id']], {'is_updated': False}])
                    except Exception as e:
                        print(f"Terjadi kesalahan saat memperbarui loyalty: {e}")

            # Process loyalty points in batches of 100
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                for i in range(0, len(loyalty_points), 100):
                    batch = loyalty_points[i:i + 100]
                    executor.map(process_loyalty_point, batch)

    def ts_in_from_mc(self, model_name, fields, description, date_from, date_to):
        try:
            transaksi_ts_in = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                model_name, 'search_read',
                                                                [[['picking_type_id.name', '=', 'TS In'], ['is_integrated', '=', False], ['state', '=', 'assigned'], ['create_date', '>=', date_from], ['create_date', '<=', date_to]]],
                                                                {'fields': fields})
            
            # print(transaksi_goods_receipt)

            if not transaksi_ts_in:
                print("Semua transaksi telah diproses.")
                return

            location_dest_id = [str(record.get('location_dest_id')[0]) if isinstance(record.get('location_dest_id'), list) else str(record.get('location_dest_id')) for record in transaksi_ts_in]
            location_dest_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id_mc', 'in', location_dest_id]]],
                                                                {'fields': ['id', 'id_mc', 'complete_name'] , 'limit': 1})
            location_dest_source_dict = {location_dest['id_mc']: location_dest['id_mc'] for location_dest in location_dest_source}

            picking_type_ids = [str(record.get('picking_type_id')[0]) if isinstance(record.get('picking_type_id'), list) else str(record.get('picking_type_id')) for record in transaksi_ts_in]

            picking_type_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking.type', 'search_read',
                                                                    [[['id', 'in', picking_type_ids]]],
                                                                    {'fields': ['id', 'id_mc'] , 'limit': 1})
            picking_type_source_dict = {type['id_mc']: type['id_mc'] for type in picking_type_source}

            picking_ids = [record['id'] for record in transaksi_ts_in]
            ts_in_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'stock.move', 'search_read',
                                                                [[['picking_id', 'in', picking_ids]]],
                                                                {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

            tsin_transfer_inventory_lines_dict = {}
            for line in ts_in_inventory_lines:
                if 'picking_id' in line:
                    picking_id = line['picking_id'][0]
                    if picking_id not in tsin_transfer_inventory_lines_dict:
                        tsin_transfer_inventory_lines_dict[picking_id] = []
                    tsin_transfer_inventory_lines_dict[picking_id].append(line)

            product_ids = [line['product_id'][0] for line in ts_in_inventory_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'name', 'taxes_id', 'default_code']})
            product_source_dict = {product['id']: product for product in product_source}


            # Pre-fetch products in target by default_code
            default_codes = [product['default_code'] for product in product_source if product.get('default_code')]
            target_products_by_code = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['default_code', 'in', default_codes], ['active', '=', True]]],
                                                                {'fields': ['id', 'default_code']})
            target_products_by_code_dict = {product['default_code']: product['id'] for product in target_products_by_code}
            
            existing_ts_in_dict = {}
            for record in transaksi_ts_in:
                existing_ts_in = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'stock.picking', 'search_read',
                                                            [[['vit_trxid', '=', record.get('name')]]],
                                                            {'fields': ['id'], 'limit': 1})
                if existing_ts_in:
                    existing_ts_in_dict[record['id']] = existing_ts_in[0]['id']

            def process_ts_in_record(record):
                if record['id'] in existing_ts_in_dict:
                    return
                ts_in_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'stock.move', 'search_read',
                                                                [[['picking_id', '=', record['id']]]],
                                                                {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})
                
                location_id = "Partners/Vendors"
                location_id_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.location', 'search_read',
                                                                    [[['complete_name', '=', location_id ]]],
                                                                    {'fields': ['id'], 'limit': 1})
                
                location_id = location_id_source[0]['id']
                location_dest_id = location_dest_source_dict.get(str(record.get('location_dest_id')[0]) if isinstance(record.get('location_dest_id'), list) else str(record.get('location_dest_id')))
                
                picking_type_id = picking_type_source_dict.get(str(record.get('picking_type_id')[0]) if isinstance(record.get('picking_type_id'), list) else str(record.get('picking_type_id')))

                missing_products = []
                ts_in_inventory_line_ids = []
                for line in ts_in_inventory_lines:
                    product_id_info = line.get('product_id')
                    if product_id_info:
                        product_id = product_id_info[0]  # Get the id part
                        product = product_source_dict.get(product_id)
                        if product:
                            default_code = product.get('default_code')
                            product_target_id = None
                            if default_code:
                                product_target_id = target_products_by_code_dict.get(default_code)
                            if not product_target_id:
                                missing_products.append(product['name'])

                        ts_in_inventory_line_data = {
                            'product_id': product_id,
                            'product_uom_qty': line.get('product_uom_qty'),
                            'name': line.get('name'),
                            'quantity': line.get('quantity'),
                            'location_dest_id': int(location_dest_id),
                            'location_id': int(location_id)
                        }
                        ts_in_inventory_line_ids.append((0, 0, ts_in_inventory_line_data))

                    if missing_products:
                        missing_products_str = ", ".join(missing_products)
                        message = f"Terdapat produk tidak aktif dalam Goods Receipt: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'Goods Receipts', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'Goods Receipts', message, write_date)

                target_location = record.get('target_location')

                ts_in_transfer_data = {
                    # 'name': record.get('name', False) + ' - ' + datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%Y-%m-%d %H:%M:%S"),
                    # 'partner_id': customer_target_id,
                    'scheduled_date': record.get('scheduled_date', False),
                    'date_done': record.get('date_done', False),
                    'vit_trxid': record.get('name', False),
                    'is_integrated': True,
                    'origin': record.get('origin', False),
                    'location_id': int(location_id),
                    'location_dest_id': int(location_dest_id),
                    'targets': target_location,
                    'picking_type_id': int(picking_type_id),
                    'move_ids_without_package': ts_in_inventory_line_ids,
                }

                print(ts_in_transfer_data)

                try:
                    new_ts_in_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking', 'create',
                                                                    [ts_in_transfer_data])
                    print(f"Goods Receipt baru telah dibuat dengan ID: {new_ts_in_id}")

                    new_ts_in_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'stock.picking', 'read',
                                                            [new_ts_in_id, ['name']])

                    if new_ts_in_id:
                        vit_trxid = new_ts_in_id[0]['name']

                        start_time = time.time()
                        self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'stock.picking', 'write',
                            [[record['id']], {'is_integrated': True, 'vit_trxid': vit_trxid}]
                        )
                        end_time = time.time()
                        duration = end_time - start_time

                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'TS Out/TS In', write_date)
                        self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'TS Out/TS In', write_date)
                    else:
                        print(f"Tidak dapat mengambil 'vit_trxid' untuk stock.picking ID {new_ts_in_id}")
                    
                except Exception as e:
                    print(f"Gagal membuat atau memposting TS In baru: {e}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_ts_in_record, record) for record in transaksi_ts_in]
                concurrent.futures.wait(futures)

        except Exception as e:
            print(f"Gagal membuat atau memposting TS In di Source: {e}")

    def validate_tsout_mc(self, model_name, fields, description, date_from, date_to):
        # Retrieve TS Out records that match the specified criteria from the source database
        TS_out_validates = self.source_client.call_odoo(
            'object', 'execute_kw', 
            self.source_client.db, self.source_client.uid, self.source_client.password,
            'stock.picking', 'search_read',
            [[
                ['picking_type_id.name', '=', 'TS Out'], 
                ['is_integrated', '=', True], 
                ['state', '=', 'assigned'],
                ['write_date', '>=', date_from], 
                ['write_date', '<=', date_to]
            ]],
            {'fields': ['id', 'name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'move_ids_without_package']}
        )

        # Check if any TS Out records are found
        if not TS_out_validates:
            print("Tidak ada TS Out yang ditemukan di target.")
        else:
            # Process in batches of 100
            for i in range(0, len(TS_out_validates), 100):
                batch = TS_out_validates[i:i + 100]
                for ts in batch:
                    try:
                        start_time = time.time()
                        self.source_client.call_odoo(
                            'object', 'execute_kw',
                            self.source_client.db, self.source_client.uid, self.source_client.password,
                            'stock.picking', 'button_validate',
                            [ts['id']]
                        )
                        print(f"TS Out with ID {ts['id']} has been validated.")
                        end_time = time.time()
                        duration = end_time - start_time

                        write_date = self.get_write_date(model_name, ts['id'])
                        self.set_log_mc.create_log_note_success(ts, start_time, end_time, duration, 'TS Out/TS In', write_date)
                        self.set_log_ss.create_log_note_success(ts, start_time, end_time, duration, 'TS Out/TS In', write_date)
                    except Exception as e:
                        message_exception = f"Failed to validate TS Out with ID {ts['id']}: {e}"
                        self.set_log_ss.create_log_note_failed(ts, 'TS Out/TS In', message_exception, write_date)
                        self.set_log_mc.create_log_note_failed(ts, 'TS Out/TS In', message_exception, write_date)

    def validate_goods_receipts_mc(self, model_name, fields, description, date_from, date_to):
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
                        self.set_log_ss.create_log_note_failed(gr, 'Goods Receipts', message_exception, write_date)
                        self.set_log_mc.create_log_note_failed(gr, 'Goods Receipts', message_exception, write_date)

    def validate_goods_issue_mc(self, model_name, fields, description, date_from, date_to):
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
                        self.set_log_ss.create_log_note_failed(gi, 'Goods Issue', message_exception, write_date)
                        self.set_log_mc.create_log_note_failed(gi, 'Goods Issue', message_exception, write_date)

    def validate_invoice(self, model_name, fields, description, date_from, date_to):
        # Retrieve TS In records that match the specified criteria from the source database
        invoice_validates = self.source_client.call_odoo(
            'object', 'execute_kw', 
            self.source_client.db, self.source_client.uid, self.source_client.password,
            'pos.order', 'search_read',
            [[
                ['is_integrated', '=', True], 
                ['state', '=', 'paid']
            ]],
            {'fields': ['id']}
        )
        for record in invoice_validates:
            try:
                start_time = time.time()
                self.source_client.call_odoo(
                    'object', 'execute_kw',
                    self.source_client.db, self.source_client.uid, self.source_client.password,
                    'pos.order', 'action_pos_order_invoice',
                    [[record['id']]]  # Corrected to wrap record['id'] in a list
                )
                print(f"PoS Order with ID {record['id']} has been invoiced.")
                end_time = time.time()
                duration = end_time - start_time

                write_date = self.get_write_date(model_name, record['id'])
                self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Invoice', write_date)  # Added record
                self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Invoice', write_date)  # Added record
            except Exception as e:
                message_exception = f"Failed to validate POS Order In with ID {record['id']}: {e}"
                self.set_log_ss.create_log_note_failed(record, 'Invoice', message_exception, write_date)
                self.set_log_mc.create_log_note_failed(record, 'Invoice', message_exception, write_date)

    def validate_GRPO(self, model_name, fields, description, date_from, date_to):
        # Retrieve TS In records that match the specified criteria from the source database
        GRPO_validates = self.source_client.call_odoo(
            'object', 'execute_kw', 
            self.source_client.db, self.source_client.uid, self.source_client.password,
            'stock.picking', 'search_read',
            [[
                ['picking_type_id.name', '=', 'GRPO'], 
                ['is_integrated', '=', True], 
                ['is_updated', '=', False],
                ['state', '=', 'done'],
                ['create_date', '>=', date_from],
                ['create_date', '<=', date_to]
            ]],
            {'fields': ['name', 'partner_id', 'location_id', 'picking_type_id', 'location_dest_id', 'scheduled_date', 'date_done', 'origin', 'vit_trxid', 'move_ids_without_package']}
        )

        # Check if any TS In records are found
        if not GRPO_validates:
            print("Tidak ada GRPO yang ditemukan di target.")
        else:
            for res in GRPO_validates:
                vit_trxid = res.get('vit_trxid', False)

                # Retrieve TS In records that need validation from the target database
                GRPO_needs_validate = self.target_client.call_odoo(
                    'object', 'execute_kw', 
                    self.target_client.db, self.target_client.uid, self.target_client.password,
                    'stock.picking', 'search_read',
                    [[
                        ['picking_type_id.name', '=', 'GRPO'], 
                        ['vit_trxid', '=', vit_trxid], 
                        ['is_integrated', '=', True], 
                        ['state', '=', 'assigned']
                    ]],
                    {'fields': ['name']}
                )
                
                write_date = False
                # Validate each TS In record
                for rec in GRPO_needs_validate:
                    grpo_id = rec['id']
                    try:
                        start_time = time.time()
                        self.target_client.call_odoo(
                            'object', 'execute_kw',
                            self.target_client.db, self.target_client.uid, self.target_client.password,
                            'stock.picking', 'button_validate',
                            [grpo_id]
                        )
                        self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'stock.picking', 'write',
                            [[rec['id']], {'is_updated': True}]
                        )

                        print(f"GRPO In with ID {grpo_id} has been validated.")
                        end_time = time.time()
                        duration = end_time - start_time

                        write_date = self.get_write_date(model_name, rec['id'])
                        self.set_log_mc.create_log_note_success(rec, start_time, end_time, duration, 'GRPO', write_date)
                        self.set_log_ss.create_log_note_success(rec, start_time, end_time, duration, 'GRPO', write_date)
                    except Exception as e:
                        print(f"Failed to validate GRPO with ID {grpo_id}: {e}")
                        # self.set_log_ss.create_log_note_failed(rec, 'GRPO', message_exception, write_date)
                        # self.set_log_mc.create_log_note_failed(rec, 'GRPO', message_exception, write_date)

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
            
            location_ids = [record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id') for record in transaksi_goods_receipt]
            location_dest_id = [record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id') for record in transaksi_goods_receipt]
            picking_type_ids = [record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id') for record in transaksi_goods_receipt]


            location_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id_mc', 'in', location_ids]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_source_dict = {location['id']: location['id'] for location in location_source}

            location_dest_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id_mc', 'in', location_dest_id]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_dest_source_dict = {location_dest['id']: location_dest['id'] for location_dest in location_dest_source}

            picking_type_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking.type', 'search_read',
                                                                    [[['id_mc', 'in', picking_type_ids]]],
                                                                    {'fields': ['id', 'id_mc'] , 'limit': 1})
            picking_type_source_dict = {type['id']: type['id'] for type in picking_type_source}

            picking_ids = [record['id'] for record in transaksi_internal_transfers]
            internal_transfers_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'stock.move', 'search_read',
                                                                        [[['picking_id', 'in', picking_ids]]],
                                                                        {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})
            
            existing_internal_transfers_dict = {}
            for record in transaksi_internal_transfers:
                existing_it = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'stock.picking', 'search_read',
                                                            [[['vit_trxid', '=', record.get('name')]]],
                                                            {'fields': ['id'], 'limit': 1})
                if existing_it:
                    existing_internal_transfers_dict[record['id']] = existing_it[0]['id']

            internal_transfer_lines_dict = {}
            for line in internal_transfers_inventory_lines:
                if 'picking_id' in line:
                    picking_id = line['picking_id'][0]
                    if picking_id not in internal_transfer_lines_dict:
                        internal_transfer_lines_dict[picking_id] = []
                    internal_transfer_lines_dict[picking_id].append(line)

            product_ids = [line['product_id'][0] for line in internal_transfers_inventory_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'name', 'taxes_id', 'default_code']})
            product_source_dict = {product['id']: product for product in product_source}

            # Pre-fetch products in target by default_code
            default_codes = [product['default_code'] for product in product_source if product.get('default_code')]
            target_products_by_code = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['default_code', 'in', default_codes], ['active', '=', True]]],
                                                                {'fields': ['id', 'default_code']})
            target_products_by_code_dict = {product['default_code']: product['id'] for product in target_products_by_code}

            new_internal_transfer_ids = []
            def proces_internal_transfer_record_from_mc(record):
                if record['id'] in existing_internal_transfers_dict:
                    return
        
                internal_transfers_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
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
                internal_transfers_inventory_line_ids = []
                for line in internal_transfers_inventory_lines:    
                    product_id_info = line.get('product_id')
                    if product_id_info:
                        product_id = product_id_info[0]  # Get the id part
                        product = product_source_dict.get(product_id)
                        if product:
                            default_code = product.get('default_code')
                            product_target_id = None
                            if default_code:
                                product_target_id = target_products_by_code_dict.get(default_code)

                            if not product_target_id:
                                missing_products.append(product['name'])

                        internal_transfers_inventory_line_data = {
                            'product_id': int(product_id),
                            'product_uom_qty': line.get('product_uom_qty'),
                            'name': line.get('name'),
                            'quantity': line.get('quantity'),
                            'location_dest_id': int(location_dest_id),
                            'location_id': int(location_id)
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
                    'location_id': int(location_id),
                    'location_dest_id': int(location_dest_id),
                    'picking_type_id': picking_type_id,
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
                    self.set_log_ss.create_log_note_failed(record, 'Internal Transfer', message_exception, write_date)
                    self.set_log_mc.create_log_note_failed(record, 'Internal Transfer', message_exception, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit([proces_internal_transfer_record_from_mc], record) for record in transaksi_internal_transfers]
                concurrent.futures.wait(futures)
        except Exception as e:
            print(f"Gagal membuat atau memposting Internal Transfer di Source baru: {e}")

    def transfer_goods_receipt(self, model_name, fields, description, date_from, date_to):
        try:
            # Ambil data dari sumber
            transaksi_goods_receipt = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                model_name, 'search_read',
                                                                [[['picking_type_id.name', '=', 'Goods Receipts'], ['is_integrated', '=', False], ['state', '=', 'done'], ['create_date', '>=', date_from], ['create_date', '<=', date_to]]],
                                                                {'fields': fields})

            if not transaksi_goods_receipt:
                print("Semua transaksi telah diproses.")
                return
            
            location_ids = [str(record.get('location_id')[0]) if isinstance(record.get('location_id'), list) else str(record.get('location_id')) for record in transaksi_goods_receipt]
            location_dest_id = [str(record.get('location_dest_id')[0]) if isinstance(record.get('location_dest_id'), list) else str(record.get('location_dest_id')) for record in transaksi_goods_receipt]
            picking_type_ids = [str(record.get('picking_type_id')[0]) if isinstance(record.get('picking_type_id'), list) else str(record.get('picking_type_id')) for record in transaksi_goods_receipt]


            location_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id_mc', 'in', location_ids]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_source_dict = {location['id_mc']: location['id'] for location in location_source}

            location_dest_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id_mc', 'in', location_dest_id]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_dest_source_dict = {location_dest['id_mc']: location_dest['id'] for location_dest in location_dest_source}

            picking_type_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking.type', 'search_read',
                                                                    [[['id_mc', 'in', picking_type_ids]]],
                                                                    {'fields': ['id', 'id_mc'] , 'limit': 1})
            picking_type_source_dict = {type['id_mc']: type['id'] for type in picking_type_source}

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

            goods_receipts_lines_dict = {}
            for line in goods_receipt_inventory_lines:
                if 'picking_id' in line:
                    picking_id = line['picking_id'][0]
                    if picking_id not in goods_receipts_lines_dict:
                        goods_receipts_lines_dict[picking_id] = []
                    goods_receipts_lines_dict[picking_id].append(line)

            product_ids = [line['product_id'][0] for line in goods_receipt_inventory_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'name', 'taxes_id', 'default_code']})
            product_source_dict = {product['id']: product for product in product_source}


            # Pre-fetch products in target by default_code
            default_codes = [product['default_code'] for product in product_source if product.get('default_code')]
            target_products_by_code = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['default_code', 'in', default_codes], ['active', '=', True]]],
                                                                {'fields': ['id', 'default_code']})
            target_products_by_code_dict = {product['default_code']: product['id'] for product in target_products_by_code}
            
            new_goods_receipts_ids = []
            def proces_goods_receipts_record_from_mc(record):
                if record['id'] in existing_goods_receipts_dict:
                    return
                
                # # Ambil invoice line items dari sumber
                goods_receipt_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                                self.source_client.uid, self.source_client.password,
                                                                                'stock.move', 'search_read',
                                                                                [[['picking_id', '=', record['id']]]],
                                                                                {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})
                
                # print(goods_receipt_inventory_lines)
                location_id = location_source_dict.get(str(record.get('location_id')[0]) if isinstance(record.get('location_id'), list) else str(record.get('location_id')))
                location_dest_id = location_dest_source_dict.get(str(record.get('location_dest_id')[0]) if isinstance(record.get('location_dest_id'), list) else str(record.get('location_dest_id')))
                picking_type_id = picking_type_source_dict.get(str(record.get('picking_type_id')[0]) if isinstance(record.get('picking_type_id'), list) else str(record.get('picking_type_id')))
                
                if location_id is None or location_dest_id is None or picking_type_id is None:
                    print(f"Data tidak lengkap untuk transaksi dengan ID {record.get('id')}. Tidak membuat dokumen.")
                    return

                missing_products = []
                goods_receipt_inventory_line_ids = []
                for line in goods_receipt_inventory_lines:
                    product_id_info = line.get('product_id')
                    if product_id_info:
                        product_id = product_id_info[0]  # Get the id part
                        product = product_source_dict.get(product_id)
                        if product:
                            default_code = product.get('default_code')
                            product_target_id = None
                            if default_code:
                                product_target_id = target_products_by_code_dict.get(default_code)
                                print(product_target_id)
                            if not product_target_id:
                                missing_products.append(product['name'])

                        goods_receipt_inventory_line_data = {
                            'product_id': product_target_id,
                            'product_uom_qty': line.get('product_uom_qty'),
                            'name': line.get('name'),
                            'quantity': line.get('quantity'),
                            'location_dest_id': int(location_id),
                            'location_id': int(location_dest_id)
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
                    # 'name': record.get('name', False) + ' - ' + datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%Y-%m-%d %H:%M:%S"),
                    # 'partner_id': customer_target_id,
                    'scheduled_date': record.get('scheduled_date', False),
                    'date_done': record.get('date_done', False),
                    'vit_trxid': record.get('name', False),
                    'is_integrated': True,
                    'origin': record.get('vit_trxid', False),
                    'location_id': int(location_dest_id),
                    'location_dest_id': int(location_id),
                    'picking_type_id': int(picking_type_id),
                    'move_ids_without_package': goods_receipt_inventory_line_ids,
                }

                try:
                    new_gr_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking', 'create',
                                                                    [goods_receipts_transfer_data])
                    print(f"Goods Receipt baru telah dibuat dengan ID: {new_gr_id}")

                    start_time = time.time()
                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'stock.picking', 'write',
                        [[record['id']], {'is_integrated': True}]
                    )
                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Goods Receipts', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Goods Receipts', write_date)
                except Exception as e:
                    message_exception = f"Gagal membuat atau memposting Goods Receipt baru: {e}"
                    self.set_log_ss.create_log_note_failed(record, 'Goods Receipts', message_exception, write_date)
                    self.set_log_mc.create_log_note_failed(record, 'Goods Receipts', message_exception, write_date)
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(proces_goods_receipts_record_from_mc, record) for record in transaksi_goods_receipt]
                concurrent.futures.wait(futures)
        except Exception as e:
            print(f"Gagal membuat atau memposting Goods Receipts di Source baru: {e}")

    def transfer_receipts(self, model_name, fields, description, date_from, date_to):
        try:
            # Ambil data dari sumber
            transaksi_receipt = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                model_name, 'search_read',
                                                                [[['picking_type_id.name', '=', 'GRPO'], ['is_integrated', '=', False], ['state', '=', 'assigned'], ['create_date', '>=', date_from], ['create_date', '<=', date_to]]],
                                                                {'fields': fields})

            if not transaksi_receipt:
                print("Semua transaksi telah diproses.")
                return

            location_ids = [record.get('location_id')[0] if isinstance(record.get('location_id'), list) else record.get('location_id') for record in transaksi_receipt]
            location_dest_id = [record.get('location_dest_id')[0] if isinstance(record.get('location_dest_id'), list) else record.get('location_dest_id') for record in transaksi_receipt]
            picking_type_ids = [record.get('picking_type_id')[0] if isinstance(record.get('picking_type_id'), list) else record.get('picking_type_id') for record in transaksi_receipt]


            location_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id_mc', 'in', location_ids]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_source_dict = {location['id']: location['id'] for location in location_source}

            location_dest_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id_mc', 'in', location_dest_id]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            location_dest_source_dict = {location_dest['id']: location_dest['id'] for location_dest in location_dest_source}

            picking_type_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking.type', 'search_read',
                                                                    [[['id_mc', 'in', picking_type_ids]]],
                                                                    {'fields': ['id', 'id_mc'] , 'limit': 1})
            picking_type_source_dict = {type['id']: type['id'] for type in picking_type_source}

            picking_ids = [record['id'] for record in transaksi_receipt]

            receipt_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    'stock.move', 'search_read',
                                                                    [[['picking_id', '=', picking_ids]]],
                                                                    {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

            existing_grpo_dict = {}
            for record in transaksi_receipt:
                existing_grpo = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'stock.picking', 'search_read',
                                                            [[['vit_trxid', '=', record.get('name')]]],
                                                            {'fields': ['id'], 'limit': 1})
                if existing_grpo:
                    existing_grpo_dict[record['id']] = existing_grpo[0]['id']

            grpo_lines_dict = {}
            for line in receipt_inventory_lines:
                if 'picking_id' in line:
                    picking_id = line['picking_id'][0]
                    if picking_id not in grpo_lines_dict:
                        grpo_lines_dict[picking_id] = []
                    grpo_lines_dict[picking_id].append(line)

            product_ids = [line['product_id'][0] for line in receipt_inventory_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'name', 'taxes_id', 'default_code']})
            product_source_dict = {product['id']: product for product in product_source}

            # Pre-fetch products in target by default_code
            default_codes = [product['default_code'] for product in product_source if product.get('default_code')]
            target_products_by_code = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['default_code', 'in', default_codes], ['active', '=', True]]],
                                                                {'fields': ['id', 'default_code']})
            target_products_by_code_dict = {product['default_code']: product['id'] for product in target_products_by_code}
            
            new_grpo_ids = []
            def proces_receipts_record_from_mc(record):
                if record['id'] in existing_grpo_dict:
                    return
                receipt_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
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
                for line in receipt_inventory_lines:
                    product_id_info = line.get('product_id')
                    if product_id_info:
                        product_id = product_id_info[0]  # Get the id part
                        product = product_source_dict.get(product_id)
                        if product:
                            default_code = product.get('default_code')
                            product_target_id = None
                            if default_code:
                                product_target_id = target_products_by_code_dict.get(default_code)

                            if not product_target_id:
                                missing_products.append(product['name'])

                    receipt_inventory_line_data = {
                        'product_id': int(product_id),
                        'product_uom_qty': line.get('product_uom_qty'),
                        'name': line.get('name'),
                        'quantity': line.get('quantity'),
                        'location_dest_id': int(location_dest_id),
                        'location_id': int(location_id)
                    }
                    receipt_inventory_line_ids.append((0, 0, receipt_inventory_line_data))

                    if missing_products:
                        missing_products_str = ", ".join(missing_products)
                        message = f"Terdapat produk tidak aktif dalam Receipt: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'Receipts', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'Receipts', message, write_date)

                receipt_transfer_data = {
                    # 'name': record.get('name', False) + ' - ' + datetime.now(pytz.timezone('Asia/Jakarta')).strftime("%Y-%m-%d %H:%M:%S"),
                    # 'partner_id': customer_target_id,
                    'scheduled_date': record.get('scheduled_date', False),
                    'date_done': record.get('date_done', False),
                    'vit_trxid': record.get('name', False),
                    'origin': record.get('origin', False),
                    'is_integrated': True,
                    'location_id': int(location_id),
                    'location_dest_id': int(location_dest_id),
                    'picking_type_id': int(picking_type_id),
                    'move_ids_without_package': receipt_inventory_line_ids,
                }

                try:
                    new_receipt_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking', 'create',
                                                                    [receipt_transfer_data])
                    print(f"GRPO baru telah dibuat dengan ID: {new_receipt_id}")

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
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'GRPO', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'GRPO', write_date)
                except Exception as e:
                    message_exception = f"Gagal membuat atau memposting GRPO baru: {e}"
                    self.set_log_ss.create_log_note_failed(record, 'GRPO', message_exception, write_date)
                    self.set_log_mc.create_log_note_failed(record, 'GRPO', message_exception, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(proces_receipts_record_from_mc, record) for record in transaksi_receipt]
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
            
            location_ids = [str(record.get('location_id')[0]) if isinstance(record.get('location_id'), list) else str(record.get('location_id')) for record in transaksi_goods_issue]
            location_dest_id = [str(record.get('location_dest_id')[0]) if isinstance(record.get('location_dest_id'), list) else str(record.get('location_dest_id')) for record in transaksi_goods_issue]
            picking_type_ids = [str(record.get('picking_type_id')[0]) if isinstance(record.get('picking_type_id'), list) else str(record.get('picking_type_id')) for record in transaksi_goods_issue]


            location_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id_mc', 'in', location_ids]]],
                                                                {'fields': ['id', 'id_mc', 'complete_name'] , 'limit': 1})
            location_source_dict = {location['id_mc']: location['id'] for location in location_source}

            location_dest_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'stock.location', 'search_read',
                                                                [[['id_mc', 'in', location_dest_id]]],
                                                                {'fields': ['id', 'id_mc', 'complete_name'] , 'limit': 1})
            location_dest_source_dict = {location_dest['id_mc']: location_dest['id'] for location_dest in location_dest_source}

            picking_type_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking.type', 'search_read',
                                                                    [[['id_mc', 'in', picking_type_ids]]],
                                                                    {'fields': ['id', 'id_mc', 'name'] , 'limit': 1})
            picking_type_source_dict = {type['id_mc']: type['id'] for type in picking_type_source}

            # print(location_source_dict)

            picking_ids = [record['id'] for record in transaksi_goods_issue]

            goods_issue_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
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
            for line in goods_issue_inventory_lines:
                if 'picking_id' in line:
                    picking_id = line['picking_id'][0]
                    if picking_id not in goods_issue_lines_dict:
                        goods_issue_lines_dict[picking_id] = []
                    goods_issue_lines_dict[picking_id].append(line)

            # Pre-fetch product and tax data
            product_ids = [line['product_id'][0] for line in goods_issue_inventory_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'name', 'taxes_id', 'default_code']})
            product_source_dict = {product['id']: product for product in product_source}

            # Pre-fetch products in target by default_code
            default_codes = [product['default_code'] for product in product_source if product.get('default_code')]
            target_products_by_code = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['default_code', 'in', default_codes], ['active', '=', True]]],
                                                                {'fields': ['id', 'default_code']})
            target_products_by_code_dict = {product['default_code']: product['id'] for product in target_products_by_code}

            new_goods_issue_ids = []
            def proces_goods_issue_record_from_mc(record):
                if record['id'] in existing_goods_issue_dict:
                    return
                
                goods_issue_inventory_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'stock.move', 'search_read',
                                                                        [[['picking_id', '=', record['id']]]],
                                                                        {'fields': ['product_id', 'product_uom_qty', 'quantity', 'name']})

                location_id = location_source_dict.get(str(record.get('location_id')[0]) if isinstance(record.get('location_id'), list) else str(record.get('location_id')))
                location_dest_id = location_dest_source_dict.get(str(record.get('location_dest_id')[0]) if isinstance(record.get('location_dest_id'), list) else str(record.get('location_dest_id')))
                picking_type_id = picking_type_source_dict.get(str(record.get('picking_type_id')[0]) if isinstance(record.get('picking_type_id'), list) else str(record.get('picking_type_id')))
                
                if location_id is None or location_dest_id is None or picking_type_id is None:
                    print(f"Data tidak lengkap untuk transaksi dengan ID {record.get('name')}. Tidak membuat dokumen.")
                    return
                
                missing_products = []
                goods_issue_inventory_line_ids = []
                for line in goods_issue_inventory_lines:
                    product_id_info = line.get('product_id')
                    if product_id_info:
                        product_id = product_id_info[0]  # Get the id part
                        product = product_source_dict.get(product_id)
                        if product:
                            default_code = product.get('default_code')
                            product_target_id = None
                            if default_code:
                                product_target_id = target_products_by_code_dict.get(default_code)

                            if not product_target_id:
                                missing_products.append(product['name'])

                    goods_issue_inventory_line_data = {
                        'product_id': product_target_id,
                        'product_uom_qty': line.get('product_uom_qty'),
                        'name': line.get('name'),
                        'quantity': line.get('quantity'),
                        'location_dest_id': int(location_dest_id),
                        'location_id': int(location_id)
                    }
                    goods_issue_inventory_line_ids.append((0, 0, goods_issue_inventory_line_data))

                    if missing_products:
                        missing_products_str = ", ".join(missing_products)
                        message = f"Terdapat produk tidak aktif dalam invoice: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'Goods Issue', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'Goods Issue', message, write_date)
                        return

                goods_issue_transfer_data = {
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
                                                                    [goods_issue_transfer_data])
                    print(f"Goods Issue baru telah dibuat dengan ID: {new_goods_issue_id}")

                    start_time = time.time()
                    self.source_client.call_odoo(
                        'object', 'execute_kw', self.source_client.db,
                        self.source_client.uid, self.source_client.password,
                        'stock.picking', 'write',
                        [[record['id']], {'is_integrated': True}]
                    )
                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Goods Issue', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Goods Issue', write_date)
                except Exception as e:
                    message_exception = f"Gagal membuat atau memposting Goods Issue baru: {e}"
                    self.set_log_ss.create_log_note_failed(record, 'Goods Issue', message_exception, write_date)
                    self.set_log_mc.create_log_note_failed(record, 'Goods Issue', message_exception, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(proces_goods_issue_record_from_mc, record) for record in transaksi_goods_issue]
                concurrent.futures.wait(futures)
        except Exception as e:
            print(f"Gagal membuat atau memposting Goods Issue di Source baru: {e}")

    def update_location_id_mc(self, model_name, fields, description, date_from, date_to):
        # Step 1: Find all POS orders eligible for invoicing.
        stock_location = self.source_client.call_odoo(
            'object', 'execute_kw',
            self.source_client.db, self.source_client.uid, self.source_client.password,
            model_name, 'search_read',
            [[]],
            {'fields': fields}
        )

        if not stock_location:
            print("No location to transfer.")
            return
        
        for rec in stock_location:
            complete_name = rec.get('complete_name')
            id_mc = rec.get('id')

            find_loc_target = self.target_client.call_odoo(
                'object', 'execute_kw',
                self.target_client.db, self.target_client.uid, self.target_client.password,
                model_name, 'search_read',
                [[['complete_name', '=', complete_name]]],
                {'fields': fields}
            )

            for res in find_loc_target:
                self.target_client.call_odoo(
                    'object', 'execute_kw', self.target_client.db,
                    self.target_client.uid, self.target_client.password,
                    model_name, 'write',
                    [[res['id']], {'id_mc': id_mc}]
                )

                print(f"Succes update id_mc in store {res['id']}")
                
    def purchase_order_from_mc(self, model_name, fields, description, date_from, date_to):
        try:
            purchase_order = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                    self.source_client.uid, self.source_client.password,
                                                                    model_name, 'search_read',
                                                                    [[['state', '=', 'purchase'], ['is_integrated', '=', False]]],
                                                                    {'fields': fields})

            if not purchase_order:
                print("Tidak ada transaksi yang ditemukan untuk ditransfer.")
                return
            
            partner_ids = [str(record.get('partner_id')[0]) if isinstance(record.get('partner_id'), list) else str(record.get('partner_id')) for record in purchase_order]
            currency_ids = [str(record.get('currency_id')[0]) if isinstance(record.get('currency_id'), list) else str(record.get('currency_id')) for record in purchase_order]
            picking_type_ids = [str(record.get('picking_type_id')[0]) if isinstance(record.get('picking_type_id'), list) else str(record.get('picking_type_id')) for record in purchase_order]

            partner_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'res.partner', 'search_read',
                                                                [[['id_mc', 'in', partner_ids]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            partner_source_dict = {partner['id_mc']: partner['id'] for partner in partner_source}

            currency_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'res.currency', 'search_read',
                                                                [[['id_mc', 'in', currency_ids]]],
                                                                {'fields': ['id', 'id_mc'] , 'limit': 1})
            currency_source_dict = {currency['id']: currency['id'] for currency in currency_source}

            picking_type_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.picking.type', 'search_read',
                                                                    [[['id_mc', 'in', picking_type_ids]]],
                                                                    {'fields': ['name', 'id_mc', 'default_location_dest_id'] , 'limit': 1})
            picking_type_source_dict = {type['id_mc']: type['id'] for type in picking_type_source} 

            order_ids = [record['id'] for record in purchase_order]

            purchase_order_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                self.source_client.uid, self.source_client.password,
                                                                'purchase.order.line', 'search_read',
                                                                [[['order_id', 'in', order_ids]]],
                                                                {'fields': ['product_id', 'name', 'product_qty', 'qty_received', 'qty_invoiced', 'product_uom', 'price_unit', 'taxes_id']})
            
            existing_purchase_order_dict = {}
            for record in purchase_order:
                existing_pr = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'purchase.order', 'search_read',
                                                            [[['vit_trxid', '=', record.get('name')]]],
                                                            {'fields': ['id'], 'limit': 1})
                if existing_pr:
                    existing_purchase_order_dict[record['id']] = existing_pr[0]['id']

            purchase_order_lines_dict = {}
            for line in purchase_order_lines:
                if 'order_id' in line:
                    order_id = line['order_id'][0]
                    if order_id not in purchase_order_lines_dict:
                        purchase_order_lines_dict[order_id] = []
                    purchase_order_lines_dict[order_id].append(line)

            product_uom_ids = [line['product_uom'][0] for line in purchase_order_lines if line.get('product_uom')]
            product_uom_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        'uom.uom', 'search_read',
                                                        [[['id_mc', 'in', product_uom_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            product_uom_source_dict = {uom['id']: uom['id'] for uom in product_uom_source}

            # Pre-fetch product and tax data
            product_ids = [line['product_id'][0] for line in purchase_order_lines if line.get('product_id')]
            product_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'product.product', 'search_read',
                                                        [[['id', 'in', product_ids]]],
                                                        {'fields': ['id', 'name', 'taxes_id', 'default_code']})
            product_source_dict = {product['id']: product for product in product_source}

            # Pre-fetch products in target by default_code
            default_codes = [product['default_code'] for product in product_source if product.get('default_code')]
            target_products_by_code = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'product.product', 'search_read',
                                                                [[['default_code', 'in', default_codes], ['active', '=', True]]],
                                                                {'fields': ['id', 'default_code']})
            target_products_by_code_dict = {product['default_code']: product['id'] for product in target_products_by_code}
            
            # print(product_template_source_dict)
            tax_ids = [tax_id for product in product_source for tax_id in product.get('taxes_id', [])]
            source_taxes = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        'account.tax', 'search_read',
                                                        [[['id_mc', 'in', tax_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            source_taxes_dict = {tax['id']: tax['id_mc'] for tax in source_taxes}

            def process_purchase_order_record(record):
                if record['id'] in existing_purchase_order_dict:
                    return
                purchase_order_lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                                        self.source_client.uid, self.source_client.password,
                                                                        'purchase.order.line', 'search_read',
                                                                        [[['order_id', '=', record['id']]]],
                                                                        {'fields': ['product_id', 'name', 'product_qty', 'qty_received', 'qty_invoiced', 'product_uom', 'price_unit', 'taxes_id']})
                
                partner_id = partner_source_dict.get(str(record.get('partner_id')[0]) if isinstance(record.get('partner_id'), list) else str(record.get('partner_id')))
                picking_type_id = picking_type_source_dict.get(str(record.get('picking_type_id')[0]) if isinstance(record.get('picking_type_id'), list) else str(record.get('picking_type_id')))
                
                purchase_order_line_ids = []
                missing_products = []
                total_tax = 0  # Initialize total tax

                # Check if all products exist in the target database
                for line in purchase_order_lines:
                    product_id_info = line.get('product_id')
                    if product_id_info:
                        product_id = product_id_info[0]  # Get the id part
                        product = product_source_dict.get(product_id)
                        if product:
                            default_code = product.get('default_code')
                            product_target_id = None
                            if default_code:
                                product_target_id = target_products_by_code_dict.get(default_code)

                            if not product_target_id:
                                missing_products.append(product['name'])  # Append missing product name

                        product_uom = product_uom_source_dict.get(line.get('product_uom')[0] if isinstance(line.get('product_uom'), list) else line.get('product_uom'))
                        tax_ids_mc = [source_taxes_dict.get(tax_id) for tax_id in line.get('taxes_id', []) if tax_id in source_taxes_dict]

                        purchase_order_line_data = {
                            'product_id': product_target_id,
                            'product_qty': line.get('product_qty'),
                            'qty_received': line.get('qty_received'),
                            'qty_invoiced': line.get('qty_invoiced'),
                            # 'product_uom': product_uom,
                            'price_unit': line.get('price_unit'),
                            # 'taxes_id': [(6, 0, [int(tax_id) for tax_id in tax_ids_mc if tax_id is not None])],
                        }
                        purchase_order_line_ids.append((0, 0, purchase_order_line_data))

                    # Check for missing products after processing all lines
                    if missing_products:
                        missing_products_str = ", ".join(missing_products)
                        message = f"Terdapat produk tidak aktif dalam invoice: {missing_products_str}"
                        print(message)
                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_failed(record, 'Purchase Order', message, write_date)
                        self.set_log_ss.create_log_note_failed(record, 'Purchase Order', message, write_date)
                        return

                purchase_order_data = {
                    'partner_id': int(partner_id),
                    'partner_ref': record.get('partner_ref'),
                    'date_approve': record.get('date_approve'),
                    'date_planned': record.get('date_planned'),
                    'picking_type_id': int(picking_type_id),
                    'vit_trxid': record.get('vit_trxid'),
                    'is_integrated': True,
                    'order_line': purchase_order_line_ids
                }

                # print(f"Purchase Order Data: {purchase_order_data}")
                try:
                    start_time = time.time()
                    new_purchase_order_id = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'purchase.order', 'create',
                                                                    [purchase_order_data])

                    print(f"Purchase Order baru telah dibuat dengan ID: {new_purchase_order_id}")

                    self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                self.target_client.uid, self.target_client.password,
                                                'purchase.order', 'button_confirm',
                                                [[new_purchase_order_id]])
                    print(f"Tombol button_confirm telah dijalankan untuk PO ID: {new_purchase_order_id}")

                    self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                self.target_client.uid, self.target_client.password,
                                                'purchase.order', 'action_view_picking',
                                                [[new_purchase_order_id]])
                    print(f"Tombol receive telah dijalankan untuk PO ID: {new_purchase_order_id}")


                    picking_ids = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                            self.target_client.uid, self.target_client.password,
                                            'stock.picking', 'search_read',
                                            [[['purchase_id', '=', [new_purchase_order_id]]]],
                                            {'fields': ['id', 'move_ids_without_package']})
                    
                    purchase_order_data = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        'purchase.order', 'read',
                                                        [[new_purchase_order_id]], {'fields': ['name', 'vit_trxid']})
                    
                    purchase_order_name = purchase_order_data[0]['name']

                    for picking in picking_ids:    
                        self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'stock.picking', 'write',
                                                            [[picking['id']], {'origin': purchase_order_name, 'vit_trxid': record.get('vit_trxid'), 'is_integrated': True}])                    
                        for move_id in picking['move_ids_without_package']:
                            # Baca stock.move untuk mendapatkan quantity
                            move_data = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                    self.target_client.uid, self.target_client.password,
                                                                    'stock.move', 'read',
                                                                    [[move_id]], {'fields': ['product_uom_qty']})

                            if move_data:
                                quantity_done = move_data[0]['product_uom_qty']
                                
                                # Update product_uom_qty dengan quantity_done
                                self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'stock.move', 'write',
                                                            [[move_id], {'quantity': quantity_done, 'origin': purchase_order_name}])
                    
                    self.source_client.call_odoo(
                            'object', 'execute_kw', self.source_client.db,
                            self.source_client.uid, self.source_client.password,
                            'purchase.order', 'write',
                            [[record['id']], {'is_integrated': True}]
                    )
                    
                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Purchase Order', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Purchase Order', write_date)
                except Exception as e:
                    message_exception = f"Terjadi kesalahan saat membuat invoice: {e}"
                    self.set_log_ss.create_log_note_failed(record, 'Purchase Order', message_exception, write_date)
                    self.set_log_mc.create_log_note_failed(record, 'Purchase Order', message_exception, write_date)

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_purchase_order_record, record) for record in purchase_order]
                concurrent.futures.wait(futures)

        except Exception as e:
                print(f"Gagal membuat atau memposting Purchase Order di Source baru: {e}")

    def payment_method_from_mc(self, model_name, fields, description, date_from, date_to):
        try:
            payment_method = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        model_name, 'search_read',
                                                        [[['is_integrated', '=', False]]],
                                                        {'fields': fields})

            if not payment_method:
                print("Tidak ada method yang ditemukan untuk ditransfer")
                return
            
            # print(payment_method)

            # Extract and map journal_ids
            journal_ids = [record.get('journal_id')[0] if isinstance(record.get('journal_id'), list) else record.get('journal_id') for record in payment_method]

            journal_source = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        'account.journal', 'search_read',
                                                        [[['id_mc', 'in', journal_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            journal_source_dict = {journal['id']: journal['id'] for journal in journal_source}

            # print(journal_source_dict)

            # Extract and map config_ids
            config_ids = [config_id for configs in payment_method for config_id in configs.get('config_ids', [])]
            source_config = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        'pos.config', 'search_read',
                                                        [[['id_mc', 'in', config_ids]]],
                                                        {'fields': ['id', 'id_mc']})
            
            source_config_dict = {config['id']: config['id'] for config in source_config}

            # print(source_config_dict)

            existing_payment_method_dict = {}
            for record in payment_method:
                existing_payment = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'pos.payment.method', 'search_read',
                                                                [[['name', '=', record.get('name')]]],
                                                                {'fields': ['id']})
                if existing_payment:
                    existing_payment_method_dict[record['id']] = existing_payment[0]['id']

            def process_payment_method_record_from_mc(record):
                journal_id = journal_source_dict.get(record.get('journal_id')[0] if isinstance(record.get('journal_id'), list) else record.get('journal_id'), False)

                config_ids_mc = [source_config_dict.get(config_id) for config_id in record.get('config_ids', []) 
                                if config_id in source_config_dict]
                config_ids_mc = config_ids_mc if config_ids_mc else []  # Default to empty list if not found

                # No need to check if journal_id or config_ids_mc is None; just leave them empty if they are not found
                if record['id'] in existing_payment_method_dict:
                    # Update id_mc on target_client if payment method exists
                    try:
                        self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                    self.target_client.uid, self.target_client.password,
                                                    'pos.payment.method', 'write',
                                                    [[existing_payment_method_dict[record['id']]],
                                                    {'id_mc': record.get('id'), 'is_updated': True, 'journal_id': int(journal_id), 'config_ids': [(6, 0, config_ids_mc)]}])
                        print(f"id_mc updated for existing Payment Method with ID: {existing_payment_method_dict[record['id']]}")
                    except Exception as e:
                        print(f"Gagal memperbarui id_mc untuk Payment Method yang ada: {e}")
                    return

                payment_method_transfer_data = {
                    'name': record.get('name') if record.get('name') else False,
                    'is_online_payment': record.get('is_online_payment') if record.get('is_online_payment') else False,
                    'split_transactions': record.get('split_transactions') if record.get('split_transactions') else False,
                    'journal_id': int(journal_id),
                    'config_ids': [(6, 0, config_ids_mc)]
                }

                try:
                    new_payment = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                            self.target_client.uid, self.target_client.password,
                                                            'pos.payment.method', 'create',
                                                            [payment_method_transfer_data])
                    print(f"Payment Method baru telah dibuat dengan ID: {new_payment}")

                    start_time = time.time()
                    # self.source_client.call_odoo(
                    #     'object', 'execute_kw', self.source_client.db,
                    #     self.source_client.uid, self.source_client.password,
                    #     'pos.payment.method', 'write',
                    #     [[record['id']], {'is_integrated': True}]
                    # )
                    end_time = time.time()
                    duration = end_time - start_time

                    write_date = self.get_write_date(model_name, record['id'])
                    self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Payment Method', write_date)
                    self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Payment Method', write_date)
                except Exception as e:
                    print(f"Gagal membuat atau memposting Payment Method baru: {e}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_payment_method_record_from_mc, record) for record in payment_method]
                concurrent.futures.wait(futures)
        except Exception as e:
            print(f"Gagal membuat atau memposting Payment Method di Source baru: {e}")

    def pos_config_from_mc(self, model_name, fields, description, date_from, date_to):
        try:
            pos_config = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        model_name, 'search_read',
                                                        [[]],
                                                        {'fields': fields})

            if not pos_config:
                print("Tidak ada Config yang ditemukan untuk ditransfer")
                return

            existing_pos_config_dict = {}
            for record in pos_config:
                existing_pos_config = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                                self.target_client.uid, self.target_client.password,
                                                                'pos.config', 'search_read',
                                                                [[['name', '=', record.get('name')]]],
                                                                {'fields': ['id'], 'limit': 1})
                if existing_pos_config:
                    existing_pos_config_dict[record['id']] = existing_pos_config[0]['id']

            def process_pos_config_record_from_mc(record):
                if record['id'] in existing_pos_config_dict:
                    # Update id_mc on target_client if payment method exists
                    try:
                        start_time = time.time()
                        self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                    self.target_client.uid, self.target_client.password,
                                                    'pos.config', 'write',
                                                    [[existing_pos_config_dict[record['id']]],
                                                    {'id_mc': record.get('id'), 'is_updated': True}])
                        print(f"id_mc updated for existing PoS Config with ID: {existing_pos_config_dict[record['id']]}")
                        end_time = time.time()
                        duration = end_time - start_time

                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Payment Method', write_date)
                        self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Payment Method', write_date)
                    except Exception as e:
                        print(f"Gagal memperbarui id_mc untuk PoS Config yang ada: {e}")
                    return

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                    futures = [executor.submit(process_pos_config_record_from_mc, record) for record in pos_config]
                    concurrent.futures.wait(futures)
        except Exception as e:
            print(f"Gagal membuat atau memposting Payment Method di Source baru: {e}")

    def journal_account_from_mc(self, model_name, fields, description, date_from, date_to):
        try:
            # Retrieve journal accounts from the source
            journal_account = self.source_client.call_odoo(
                'object', 'execute_kw', 
                self.source_client.db,
                self.source_client.uid, 
                self.source_client.password,
                model_name, 'search_read',
                [[]],
                {'fields': fields}
            )

            if not journal_account:
                print("Tidak ada journal yang ditransfer")
                return

            # Prepare a dictionary of existing journals in the target system
            existing_journal_dict = {}
            for record in journal_account:
                existing_journal = self.target_client.call_odoo(
                    'object', 'execute_kw', 
                    self.target_client.db,
                    self.target_client.uid, 
                    self.target_client.password,
                    'account.journal', 'search_read',
                    [[['name', '=', record.get('name')]]],
                    {'fields': ['id'], 'limit': 1}
                )
                if existing_journal:
                    existing_journal_dict[record['id']] = existing_journal[0]['id']

            print(existing_journal_dict)

            # Function to process each journal account
            def process_journal_account(record):
                try:
                    if record['id'] in existing_journal_dict:
                        # Update id_mc for existing journal
                        self.target_client.call_odoo(
                            'object', 'execute_kw', 
                            self.target_client.db,
                            self.target_client.uid, 
                            self.target_client.password,
                            'account.journal', 'write',
                            [[existing_journal_dict[record['id']]], {'id_mc': record.get('id')}]
                        )
                        print(f"id_mc updated for existing Journal with ID: {existing_journal_dict[record['id']]}")
                    else:
                        # Create new journal account
                        journal_account_data = {
                            'name': record.get('name', False),
                            'type': record.get('type', False),
                            'refund_sequence': record.get('refund_sequence', False),
                            'code': record.get('code', False),
                            'account_control_ids': record.get('account_control_ids', False),
                            'invoice_reference_type': record.get('invoice_reference_type', False),
                            'invoice_reference_model': record.get('invoice_reference_model', False),
                        }

                        new_journal_id = self.target_client.call_odoo(
                            'object', 'execute_kw', 
                            self.target_client.db,
                            self.target_client.uid, 
                            self.target_client.password,
                            'account.journal', 'create',
                            [journal_account_data]
                        )
                        print(f"Journal baru telah dibuat dengan ID: {new_journal_id}")

                        # Mark the source journal as integrated
                        start_time = time.time()
                        # self.source_client.call_odoo(
                        #     'object', 'execute_kw', 
                        #     self.source_client.db,
                        #     self.source_client.uid, 
                        #     self.source_client.password,
                        #     'account.journal', 'write',
                        #     [[record['id']], {'is_integrated': True}]
                        # )
                        end_time = time.time()
                        duration = end_time - start_time

                        write_date = self.get_write_date(model_name, record['id'])
                        self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, 'Journal', write_date)
                        self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, 'Journal', write_date)
                except Exception as e:
                    print(f"Gagal memperbarui atau membuat Journal: {e}")

            # Use ThreadPoolExecutor to process records concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(process_journal_account, record) for record in journal_account]
                concurrent.futures.wait(futures)

        except Exception as e:
            print(f"Gagal membuat atau memposting Payment Method di Source baru: {e}")

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
