import time
from datetime import datetime, timedelta
import re
import xmlrpc.client
import json
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, as_completed

class DataIntegrator:
    def __init__(self, source_client, target_client):
        self.source_client = source_client
        self.target_client = target_client
        self.set_log_mc = SetLogMC(self.source_client)
        self.set_log_ss = SetLogSS(self.target_client)

    def get_field_uniq_from_model(self, model):
        try:
            field_uniq_mapping = {
                'res.partner': 'customer_code',
                'product.template': 'default_code',
                'product.category': 'complete_name',
                'res.users': 'login',
                'stock.location': 'complete_name',
                'account.account': 'code',
                'loyalty.card': 'code'
            }
            return field_uniq_mapping.get(model, 'name')
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"Error occurred when getting param existing data: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"Error occurred when getting param existing data: {e}", None)

    # Master Console --> Store Server
    def get_existing_data(self, model, field_uniq, fields):
        try:
            fields_target = fields.copy() # kalau tidak pakai copy makan value fields akan berubah juga sama seperti fields_target
            fields_target.extend(['id_mc'])

            existing_data = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password, model,
                                                        'search_read', [[[field_uniq, '!=', False]]], {'fields': fields_target}) # , {'fields': [field_uniq]}
            return existing_data
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    def get_index_store_data(self, model, id, len_master_store):
        try:
            index_store_data = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password, model,
                                                        'search_read', [[['id', '=', id]]], {'fields': ['index_store']})
            filtered_index_store_data = [data['id'] for data in index_store_data if len(data.get('index_store', [])) == len_master_store]
            return filtered_index_store_data
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    def get_company_id(self, field_uniq):
        try:
            company_name_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                                        self.source_client.password, 'res.company', 'search_read', [[[field_uniq, '!=', False]]],
                                                        {'fields': ['name']})
            company_name_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                                self.target_client.password, 'res.company', 'search_read', [[[field_uniq, '!=', False]]],
                                                {'fields': ['name']})
             
            existing_company = {data['name'] for data in company_name_target}
            if not existing_company:
                self.set_log_mc.create_log_note_failed("Company does not exist", "Master Tax", "No companies found in the target database.", None)
                self.set_log_ss.create_log_note_failed("Company does not exist", "Master Tax", "No companies found in the target database.", None)
                return None
            existing_company_str_one = next(iter(existing_company))

            company_id_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                                self.source_client.password, 'res.company', 'search_read', [[['name', '=', existing_company_str_one]]],
                                                {'fields': ['id']})
            if company_id_source:
                company_id_source_dict = next(iter(company_id_source))
                company_id_source_str_one = company_id_source_dict['id']
                return company_id_source_str_one
            else:
                self.set_log_mc.create_log_note_failed("Company does not exist", "Master Tax", "Company name in the source database does not exist.", None)
                self.set_log_ss.create_log_note_failed("Company does not exist", "Master Tax", "Company name in the source database does not exist.", None)
                return None
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - account.tax", f"Master Tax from {self.source_client.server_name} to {self.target_client.server_name}", f"Error occurred when get company id: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - account.tax", "Master Tax", f"Error occurred when get company id: {e}", None)

    def get_data_list(self, model, fields, field_uniq, date_from, date_to):
        try:
            if model == 'account.tax':
                company_id = self.get_company_id(field_uniq)
                data_list = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                                    self.source_client.password, model, 'search_read', [[[field_uniq, '!=', False], ['is_integrated', '=', False], ['company_id', '=', company_id], ['write_date', '>=', date_from], ['write_date', '<=', date_to]]],
                                                    {'fields': fields})
            elif model == 'ir.sequence':
                data_list = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                                    self.source_client.password, model, 'search_read', [[[field_uniq, '!=', False], ['is_integrated', '=', False], ['is_from_operation_types', '=', True], ['write_date', '>=', date_from], ['write_date', '<=', date_to]]],
                                                    {'fields': fields})
            else:
                data_list = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                                    self.source_client.password, model, 'search_read', [[[field_uniq, '!=', False], ['is_integrated', '=', False], ['write_date', '>=', date_from], ['write_date', '<=', date_to]]],
                                                    {'fields': fields})  # , 'limit': 1 , 'limit': 100 debug False
            return data_list
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"Error occurred when get data list: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"Error occurred when get data list: {e}", None)

    def get_master_conf(self):
        try:
            data_master_conf = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                                        self.source_client.password, 'setting.config', 'search_read', [[]]) # ['vit_config_server', '!=', 'mc'], ['vit_linked_server', '=', 'True']
            
            if data_master_conf:
                ss_data = [item for item in data_master_conf if item['vit_config_server'] != 'mc' and item['vit_linked_server']]
                len_master_conf = len(ss_data)
                last_index = len_master_conf - 1
                vit_config_last_store = ss_data[last_index].get('vit_config_server_name')

                # Ambil id berdasarkan 'vit_config_server_name'
                index_field_store = next((item['id'] for item in ss_data if item['vit_config_server_name'] == self.target_client.server_name), None)
            # self.set_log_mc.create_log_note_failed(f"Exception - search setting.config", f"Check debug from {self.source_client.server_name} to {self.target_client.server_name}", f"{data_master_conf}, {ss_data}, {len_master_conf}, {last_index} {vit_config_last_store}, {index_field_store} {self.target_client.server_name}", None)
            return len_master_conf, vit_config_last_store, index_field_store
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - search setting.config", f"search setting.config from {self.source_client.server_name} to {self.target_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - search setting.config", f"search setting.config", e, None)
    
    
    def get_type_data_source(self, model, fields):
        try:
            type_info = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                     self.source_client.uid, self.source_client.password,
                                                     model, 'fields_get', [], {'attributes': ['type', 'relation']})
            relations_only = {key: value['relation'] for key, value in type_info.items() if key in fields and 'relation' in value}
            # relations_only = {key: value['relation'] for key, value in type_info.items() if key in fields and 'relation' in value and key != 'item_ids'}
            # types_only = {key: value['type'] for key, value in type_info.items() if key in relations_only}
            types_only = {key: value['type'] for key, value in type_info.items() if key in relations_only and value['type'] != 'one2many'}
            return types_only, relations_only
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)
    
    def get_relation_source_all(self, model):
        try:
            if model == 'product.pricelist.item':
                filter = ['|', ['is_integrated', '=', False], ['is_updated', '=', True]]
                fields = ['product_tmpl_id', 'min_quantity', 'fixed_price', 'date_start', 'date_end', 'compute_price', 'percent_price', 'base', 'price_discount', 'price_surcharge', 'price_round', 'price_min_margin', 'price_max_margin', 'applied_on', 'categ_id', 'product_id'] # , 'is_integrated', 'is_updated'
            elif model == 'account.tax.repartition.line':
                filter = []
                fields = ['tax_id','factor_percent','repartition_type', 'account_id','tag_ids', 'document_type', 'use_in_tax_closing']
            elif model == 'res.partner':
                filter = []
                fields = ['customer_code', 'name']
            else:
                filter = []
                field_uniq_relation_source_all = self.get_field_uniq_from_model(model)
                fields = [field_uniq_relation_source_all]

            relation_data_source = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                     self.source_client.uid, self.source_client.password,
                                                     model, 'search_read', [filter], {'fields': fields})
            return relation_data_source
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)
    
    def get_relation_target_all(self, model):
        try:
            if model == 'product.pricelist.item':
                fields = ['product_tmpl_id', 'min_quantity', 'fixed_price', 'date_start', 'date_end', 'compute_price', 'percent_price', 'base', 'price_discount', 'price_surcharge', 'price_round', 'price_min_margin', 'price_max_margin', 'applied_on', 'categ_id', 'product_id', 'id_mc']
            elif model == 'account.tax.repartition.line':
                fields = ['tax_id','factor_percent','repartition_type', 'account_id','tag_ids', 'document_type', 'use_in_tax_closing']
            else:
                field_uniq_relation_source_all = self.get_field_uniq_from_model(model)
                fields = [field_uniq_relation_source_all]

            relation_data_target = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                     self.target_client.uid, self.target_client.password,
                                                     model, 'search_read', [[]], {'fields': fields})
            return relation_data_target
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)
    
    def transfer_data(self, model, fields, modul, date_from, date_to):
        try:  
            field_uniq = self.get_field_uniq_from_model(model)
            data_list = self.get_data_list(model, fields, field_uniq, date_from, date_to)
            # buat update dadakan di mc
            # ids = [item['id'] for item in data_list]
            # ids = [2972]
            # self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
            #                                     self.source_client.password, 'product.pricelist.item', 'write', [ids, {'is_integrated': True, 'is_updated': False}]) # ,  'mobile': '+62', 'website': 'wwww.test_cust.co.id', 'title': 3
            # for id in ids:
            #     self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
            #                                     self.source_client.password, model, 'write', [id, {'customer_code': f"Cust_test{id}"}]) # {'is_integrated': False }, 'categ_id' : 7, 'available_in_pos' : False

            if data_list:
                len_master, last_master_url, index_store_field = self.get_master_conf()
                existing_data_target = self.get_existing_data(model, field_uniq, fields) # 1 calling odoo
                existing_data = {data[field_uniq] for data in existing_data_target}
                type_fields, relation_fields = self.get_type_data_source(model, fields) # 2 calling odoo

                dict_relation_source = {}
                dict_relation_target = {}
                dict_relation_source_line = {}
                dict_relation_target_line = {}
                type_fields_line = None
                relation_fields_line = None

                for relation in relation_fields:
                    relation_model = relation_fields[relation]
                    many_source = self.get_relation_source_all(relation_model) # 4 1 x relation_fields calling odoo # pilih mau field apa aja?
                    dict_relation_source[relation_model] = many_source
                    many_target = self.get_relation_target_all(relation_model) # 5 1 x relation_fields calling odoo # pilih mau field apa aja?
                    dict_relation_target[relation_model] = many_target

                if model == 'account.tax' or model == 'product.pricelist':
                    if model == 'product.pricelist':
                        model_line = 'product.pricelist.item'
                        fields_line = ['product_tmpl_id', 'min_quantity', 'fixed_price', 'date_start', 'date_end', 'compute_price', 'percent_price', 'base', 'price_discount', 'price_surcharge', 'price_round', 'price_min_margin', 'applied_on', 'categ_id', 'product_id']
                        type_fields_line, relation_fields_line = self.get_type_data_source(model_line, fields_line) # 2 calling odoo
                    elif model == 'account.tax':
                        model_line = 'account.tax.repartition.line'
                        fields_line = ['tax_id','factor_percent','repartition_type', 'account_id','tag_ids', 'document_type', 'use_in_tax_closing']
                        type_fields_line, relation_fields_line = self.get_type_data_source(model_line, fields_line)
                        
                    for relation_line in relation_fields_line:
                        relation_model_line = relation_fields_line[relation_line]
                        many_source_line = self.get_relation_source_all(relation_model_line) # 4 1 x relation_fields calling odoo # pilih mau field apa aja?
                        dict_relation_source_line[relation_model_line] = many_source_line
                        many_target_line = self.get_relation_target_all(relation_model_line) # 5 1 x relation_fields calling odoo # pilih mau field apa aja?
                        dict_relation_target_line[relation_model_line] = many_target_line

                filtered_data_for_create = [item for item in data_list if item[field_uniq] not in existing_data]
                filtered_data_for_update = [item for item in data_list if item[field_uniq] in existing_data]
                self.process_data_async_create(model, fields, field_uniq, filtered_data_for_create, modul, existing_data, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target, last_master_url, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line, len_master, index_store_field)    
                self.process_data_async_update(model, fields, field_uniq, filtered_data_for_update, modul, existing_data, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target, last_master_url, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line, len_master, index_store_field)

        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"Error occurred when transfer data: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"Error occurred when transfer data: {e}", None)

    def process_data_async_create(self, model, fields, field_uniq, partial_data, modul, existing_data, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target, last_master_url, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line, len_master, index_store_field):
        try:
            data_for_create = []
            log_data_created = []
            id_mc_for_update_isintegrated = []
            id_line_for_update_isintegrated = []
            # Dapatkan data yang sudah ada di target
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = []
                # Kirim setiap record dalam partial_data untuk diproses secara asinkron
                for record in partial_data:
                    future = executor.submit(self.transfer_record_data_create, model, fields, field_uniq, record, existing_data, modul, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target, last_master_url, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line)
                    futures.append(future)
                # Tunggu semua proses selesai
                for future in concurrent.futures.as_completed(futures):
                    try:
                        valid_record = future.result()
                        if valid_record:
                            data_for_create.append(valid_record)
                    except Exception as e:
                        self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"Error occurred while processing record data: {e}", None)
                        self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"Error occurred while processing record data: {e}", None)

            if data_for_create:
                start_time = time.time()
                create = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                self.target_client.password, model, 'create', [data_for_create])
                end_time = time.time()
                duration = end_time - start_time

                print(create)

                if create:
                    for index, data_create in enumerate(data_for_create):
                        if model == 'product.pricelist':
                            item_line = data_for_create[index]['item_ids']
                            id_line = [item[2]['id'] for item in item_line]
                            id_line_for_update_isintegrated.extend(id_line)  
                        id_mc = data_create['id']
                        write_date = data_create['write_date']
                        log_record = self.set_log_mc.log_record_success(data_create, start_time, end_time, duration, modul, write_date, self.source_client.server_name, self.target_client.server_name)
                        log_data_created.append(log_record)
                        id_mc_for_update_isintegrated.append(id_mc)
                
                    self.update_indexstore_source(model, id_mc_for_update_isintegrated, index_store_field)
                    if model == 'product.pricelist':
                        self.update_indexstore_source('product.pricelist.item', id_line_for_update_isintegrated, index_store_field)
                    
                    if self.target_client.server_name == last_master_url:
                        index_store_data = self.get_index_store_data(model, id_mc_for_update_isintegrated, len_master)
                        self.update_isintegrated_source(model, index_store_data)
                        if model == 'product.pricelist':
                            index_store_data = self.get_index_store_data('product.pricelist.item', id_line_for_update_isintegrated, len_master)
                            self.update_isintegrated_source('product.pricelist.item', index_store_data)
                        
                    self.set_log_mc.create_log_note_success(log_data_created)
                    self.set_log_ss.create_log_note_success(log_data_created)
            # #     # self.set_log_mc.delete_data_log_failed(record['name'])
            # #     # self.set_log_ss.delete_data_log_failed(record['name'])
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    def process_data_async_update(self, model, fields, field_uniq, partial_data, modul, existing_data, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target, last_master_url, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line, len_master, index_store_field):
        try:
            data_for_update = []
            log_data_updated = []
            id_mc_for_update_isintegrated = []
            ids_for_update_index_store = []
            # Dapatkan data yang sudah ada di target
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = []
                # Kirim setiap record dalam partial_data untuk diproses secara asinkron
                for record in partial_data:
                    future = executor.submit(self.transfer_record_data_update, model, fields, field_uniq, record, existing_data, modul, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target, last_master_url, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line)
                    futures.append(future)
                # Tunggu semua proses selesai
                for future in concurrent.futures.as_completed(futures):
                    try:
                        valid_record, id_for_update_index_store = future.result()
                        if valid_record:
                            data_for_update.append(valid_record)
                        if id_for_update_index_store:
                            ids_for_update_index_store.append(id_for_update_index_store)

                    except Exception as e:
                        self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"Error occurred while processing record data: {e}", None)
                        self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"Error occurred while processing record data: {e}", None)

            if ids_for_update_index_store:
                self.update_indexstore_source(model, ids_for_update_index_store, index_store_field)

                if self.target_client.server_name == last_master_url:
                    index_store_data = self.get_index_store_data(model, ids_for_update_index_store, len_master)
                    self.update_isintegrated_source(model, index_store_data)

            if data_for_update:
                for data_update in data_for_update:
                    id_mc = data_update[0]['id']
                    write_date = data_update[0]['write_date']
                    log_record = self.set_log_mc.log_update_record_success(data_update[0], data_update[1], data_update[2], data_update[3], data_update[4], data_update[5], modul, write_date, self.target_client.server_name, self.source_client.server_name)
                    log_data_updated .append(log_record)
                    id_mc_for_update_isintegrated.append(id_mc)
            
                print(log_data_updated)

                self.update_indexstore_source(model, id_mc_for_update_isintegrated, index_store_field)
                
                if self.target_client.server_name == last_master_url:
                    index_store_data = self.get_index_store_data(model, id_mc_for_update_isintegrated, len_master)
                    self.update_isintegrated_source(model, index_store_data)

            # if self.target_client.url == last_master_url + "jsonrpc":
                # self.update_isintegrated_source(model, id_mc_for_update_isintegrated)

                self.set_log_mc.create_log_note_update_success(log_data_updated)
                self.set_log_ss.create_log_note_update_success(log_data_updated)

        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)


    def transfer_record_data_create(self, model, fields, field_uniq, record, existing_data, modul, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target, last_master_url, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
        try:
            id_mc = record['id']
            if model == 'product.pricelist':
                filtered_pricelist = [item for item in dict_relation_source.get('product.pricelist.item', []) if item['id'] in record.get('item_ids', [])]
                record['item_ids'] = self.transfer_pricelist_lines(filtered_pricelist, 'product.pricelist.item', [record], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line)
            elif model == 'account.tax':
                filtered_taxes_invoice = [item for item in dict_relation_source.get('account.tax.repartition.line', []) if item['id'] in record.get('invoice_repartition_line_ids', [])]
                record['invoice_repartition_line_ids'] = self.transfer_tax_lines_invoice(filtered_taxes_invoice, 'account.tax.repartition.line', record, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line)
                filtered_taxes_refund = [item for item in dict_relation_source.get('account.tax.repartition.line', []) if item['id'] in record.get('refund_repartition_line_ids', [])]
                record['refund_repartition_line_ids'] = self.transfer_tax_lines_refund(filtered_taxes_refund, 'account.tax.repartition.line', record, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line)    
            valid_record = self.validate_record_data(record, model, [record], type_fields, relation_fields, dict_relation_source, dict_relation_target)
            if valid_record:
                record['id_mc'] = id_mc
                return record
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"Error occurred while processing record: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"Error occurred while processing record: {e}", None)
    
    def transfer_record_data_update(self, model, fields, field_uniq, record, existing_data, modul, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target, last_master_url, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
        try:
            data_for_update = None
            id_for_update_index_store = None
            code = record.get(field_uniq)
            target_record = next((item for item in existing_data_target if item[field_uniq] == code), None)
            # record = self.validate_record_data_update_before(record, model, [record], type_fields, relation_fields, dict_relation_source, dict_relation_target)
            # target_record = self.validate_record_data_update_before(target_record, model, [target_record], type_fields, relation_fields, dict_relation_source, dict_relation_target)

            if model == 'product.pricelist':
                filtered_pricelist = [item_line for item_line in dict_relation_source.get('product.pricelist.item', []) if item_line['id'] in record.get('item_ids', [])]
                filtered_pricelist_target = [item_line_target for item_line_target in dict_relation_target.get('product.pricelist.item', []) 
                             if any(int(item_line_target.get('id_mc', 0)) == item_line.get('id') for item_line in filtered_pricelist)]

                record['item_ids'] = self.transfer_pricelist_lines_update(filtered_pricelist, 'product.pricelist.item', [record], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line)
                target_record['item_ids'] = self.transfer_pricelist_lines_update_target(filtered_pricelist_target, 'product.pricelist.item', [target_record], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line)

                def update_pricelist_item(target_client, id_line_target, updated_filtered_pricelist):
                    start_time = time.time()
                    update_line = target_client.call_odoo('object', 'execute_kw', target_client.db, target_client.uid,
                                                        target_client.password, 'product.pricelist.item', 'write', [id_line_target, updated_filtered_pricelist])
                    end_time = time.time()
                    duration = end_time - start_time
                    print(f"Updated pricelist item {id_line_target} in {duration:.2f} seconds.")
                    return update_line
                
                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = []
                    data_for_line_update = []
                    for id in target_record['item_ids']:
                        id_line_target = id['id']
                        id_line_mc = id['id_mc']
                        updated_filtered_pricelist = [item_line for item_line in dict_relation_source.get('product.pricelist.item', []) if item_line['id'] == int(id_line_mc)]
                        updated_filtered_pricelist = updated_filtered_pricelist[0] if updated_filtered_pricelist else {}
                        
                        # Submit each update task to the executor
                        futures.append(executor.submit(update_pricelist_item, self.target_client, id_line_target, updated_filtered_pricelist))

                    # Wait for all threads to finish
                    for future in futures:
                        valid_record_line = future.result()
                        if valid_record_line:
                            data_for_line_update.append(valid_record_line)
                            
                    for data_update in data_for_line_update:
                        if isinstance(data_update, dict) and 'id' in data_update:
                            id_mc = data_for_line_update[0]['id']
                for id in record['item_ids']:
                    id_line_mc = [id['id']]
                    filtered_pricelist_target = [item_line_target for item_line_target in dict_relation_target.get('product.pricelist.item', []) if int(item_line_target.get('id_mc', 0)) in id_line_mc]
                
                # for id in target_record['item_ids']:
                #     id_line_target = id['id']
                #     id_line_mc = id['id_mc']
                #     if id_line_mc:
                #         updated_filtered_pricelist = [item_line for item_line in dict_relation_source.get('product.pricelist.item', []) if item_line['id'] == int(id_line_mc)]
                #         updated_filtered_pricelist = updated_filtered_pricelist[0] if updated_filtered_pricelist else {}
                #         start_time = time.time()
                #         # update product.pricelist
                #         update_line = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                #                                     self.target_client.password, 'product.pricelist.item', 'write', [id_line_target, updated_filtered_pricelist])
                #         end_time = time.time()
                #         duration = end_time - start_time
                #     # elif not id_line_mc:
                #     #     update_line_mc = {}

                #     #     update_line = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                #     #                                 self.target_client.password, 'product.pricelist.item', 'write', [id_line_target, updated_filtered_pricelist])
                #     # else:
                #     #     lines_update = record['item_ids']
                #     #     lines_target = target_record['item_ids']
                #     #     filtered_lines = [item for item in lines_update if item['id'] not in lines_target]
                        
                #     #     if filtered_lines:
                #     #         for line in filtered_lines:
                #     #             line['pricelist_id'] = record_id
                            
                #     #         start_time = time.time()
                #     #         create = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                #     #                         self.target_client.password, 'product.pricelist.item', 'create', [filtered_lines])
                #     #         end_time = time.time()
                #     #         duration = end_time - start_time

                #     #         if create:
                #     #             write_date = record['write_date']
                #     #             self.set_log_mc.create_log_note_update_success(record, record_id, filtered_lines, start_time, end_time, duration, modul, write_date, self.source_client.server_name, self.target_client.server_name)
                #     #             self.set_log_ss.create_log_note_update_success(record, record_id, filtered_lines, start_time, end_time, duration, modul, write_date)

            updated_fields = {field: record[field] for field in record if record.get(field) != target_record.get(field) and field not in ('id', 'create_date', 'write_date')}

            if 'id_mc' in target_record and target_record['id_mc'] == False:
                updated_fields['id_mc'] = record['id']

            if not updated_fields:
                id_for_update_index_store = record.get('id')

            if updated_fields and model != 'stock.picking.type': 
                keys_to_remove = []
                field_data_source = []
                field_data_target = []

                fields_many2one_to_check = [
                    'title', 'categ_id', 'category_id',  'uom_id', 'uom_po_id', 'parent_id', 'location_id', 'partner_id', 'sequence_id', 'warehouse_id',
                    'default_location_src_id', 'return_picking_type_id', 'default_location_dest_id']
                for field in updated_fields:
                    if field in fields_many2one_to_check:
                        if record[field][1] == target_record[field][1]:
                            keys_to_remove.append(field) 

                fields_many2many_to_check = ['taxes_id', 'pos_categ_ids']
                for field in updated_fields:
                    if field in fields_many2many_to_check:
                        relation_model = relation_fields[field]
                        
                        field_value_source = record.get(field)
                        for data_source in field_value_source:
                            name_source = dict_relation_source[relation_model]
                            value_source = next((item['name'] for item in name_source if item['id'] == data_source), None)
                            field_data_source.append(value_source)
                        
                        field_value_target = target_record.get(field)
                        for data_target in field_value_target:
                            name_target = dict_relation_target[relation_model]
                            value_target = next((item['name'] for item in name_target if item['id'] == data_target), None)
                            field_data_target.append(value_target)
                        
                        if field_data_source == field_data_target:
                            keys_to_remove.append(field)

                fields_one2many_to_remove = ['invoice_repartition_line_ids', 'refund_repartition_line_ids', 'item_ids']
                for field in updated_fields:
                    if field in fields_one2many_to_remove:
                        keys_to_remove.append(field)

                # Remove the fields after iteration
                for key in keys_to_remove:
                    del updated_fields[key]

                if updated_fields: 
                    valid_record = self.validate_record_data_update(updated_fields, model, [record], type_fields, relation_fields, dict_relation_source, dict_relation_target)
                    if valid_record:
                        record_id = target_record.get('id')
                        data_for_update = self.update_data(model, record_id, valid_record, modul, record, last_master_url, target_record)
                else:
                    id_for_update_index_store = record.get('id')
                    
            return data_for_update, id_for_update_index_store
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"Error occurred while processing record: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"Error occurred while processing record: {e}", None)
        
     
    # to get string value for many2one, many2many data type
    def validate_record_data(self, record, model, data_list, type_fields, relation_fields, dict_relation_source, dict_relation_target):
        try:
            multiple_wh_operation_types = False

            if model == 'stock.picking.type': # tolong check ini lagi
                if record['name'] in ('Goods Receipts', 'TS In'):
                    record['code'] = 'incoming'
                elif record['name'] in ('Goods Issue', 'TS Out'):
                    record['code'] = 'outgoing'

            for field_name in relation_fields and type_fields:
                field_value = record[field_name]
                
                if not field_value:
                    continue

                field_metadata = type_fields[field_name]
                relation_model = relation_fields[field_name]

                if field_metadata == 'many2one' and isinstance(field_value, list):
                    field_data = field_value[1] if field_value else False
                elif field_metadata == 'many2many' and isinstance(field_value, list):
                    name_datas_source = dict_relation_source.get(relation_model, [])
                    field_data = [
                        next((item['name'] for item in name_datas_source if item['id'] == data), None)
                        for data in field_value
                    ]
                elif field_metadata == 'one2many':
                    continue
                    
                if isinstance(relation_model, str):
                    field_uniq = self.get_field_uniq_from_model(relation_model)

                    if model == 'product.pricelist.item' and record['applied_on'] == '1_product':
                        pattern = r'\[(.*?)\]'
                        if pattern:
                            match = re.search(pattern, field_data)
                            field_data = match.group(1)
                    if relation_model == 'account.account':
                        parts = field_data.split() # Menggunakan split untuk memisahkan string
                        field_data = parts[0] # Mengambil bagian pertama yang merupakan angka
                    
                    
                    if model == 'stock.picking.type' and field_name in ('default_location_src_id', 'default_location_dest_id'):
                        datas = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                            self.target_client.uid, self.target_client.password,
                                            relation_model, 'search_read',
                                            [[['usage', '=', 'internal']]], {'fields': ['id']})
                        if len(datas) > 1:
                            multiple_wh_operation_types = True
                    else:
                        datas_target = dict_relation_target[relation_model]
                        if isinstance(field_data, str):
                            datas_target_result = next((item['id'] for item in datas_target if item[field_uniq] == field_data), None)
                        elif isinstance(field_data, list):
                            datas_target_result = []
                            for value in field_data:
                                datas_target_notyet_result = next((item['id'] for item in datas_target if item[field_uniq] == value), None)
                                if datas_target_notyet_result is not None:
                                    datas_target_result.append(datas_target_notyet_result)
                                else:
                                    self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                                    self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                        
                        # datas = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                        #                     self.target_client.uid, self.target_client.password,
                        #                     relation_model, 'search_read',
                        #                     [[[field_uniq, '=', field_data]]], {'fields': ['id']})
                        
                        
                    if datas_target_result:
                        if field_name == 'default_location_src_id' and record['code'] == 'outgoing':
                            record[field_name] = datas[0]['id'] if datas[0] else False
                        elif field_name == 'default_location_src_id' and record['code'] == 'incoming':
                            record[field_name] = False
                        elif field_name == 'default_location_dest_id' and record['code'] == 'outgoing':
                            record[field_name] = False
                        elif field_name == 'default_location_dest_id' and record['code'] == 'incoming':
                            record[field_name] = datas[0]['id'] if datas[0] else False
                        else:
                            record[field_name] = datas_target_result if datas_target_result else False # datas[0]['id'] if datas[0] else False
                        
                    else:
                        if model == 'account.tax.repartition.line':
                            record[field_name] = field_value[0] if field_value else False
                        else:
                            self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                            self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                            return None  # Mengembalikan None jika kondisi else terpenuhi
            
            if multiple_wh_operation_types and model == 'stock.picking.type':
            # Tambahkan elemen baru ke dalam data_list
                for data in datas:
                    # Buat salinan dari record
                    new_record = record.copy()
                    if record['code'] == 'outgoing':
                        new_record['default_location_src_id'] = data['id'] if datas else False
                        new_record['default_location_dest_id'] = False
                    elif record['code'] == 'incoming':
                        new_record['default_location_src_id'] = False
                        new_record['default_location_dest_id'] = data['id'] if datas else False
                    
                    if data['id'] != record['default_location_src_id'] and data['id'] != record['default_location_dest_id']:
                        data_list.append(new_record)
            
            return record
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while validating record data: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while validating record data: {e}", None)

    def validate_record_data_update_before(self, record, model, data_list, type_fields, relation_fields, dict_relation_source, dict_relation_target):
        try:
            for field_name in relation_fields and type_fields:
                if field_name in record:
                    field_value = record[field_name]
                    
                    if not field_value :
                        if model == 'product.template'and (relation_fields[field_name] == 'account.tax' or relation_fields[field_name] == 'pos.category'):
                            record[field_name] = [(5, 0, 0)] # untuk delete
                        continue

                    field_metadata = type_fields[field_name]
                    relation_model = relation_fields[field_name]
                    
                    if field_metadata == 'many2one' and isinstance(field_value, list):
                        field_data = field_value[1] if field_value else False
                        record[field_name] = field_data
                    elif field_metadata == 'many2many' and isinstance(field_value, list):
                        name_datas_source = dict_relation_source.get(relation_model, [])
                        field_data = [
                            next((item['name'] for item in name_datas_source if item['id'] == data), None)
                            for data in field_value
                        ]
                        record[field_name] = field_data
                    elif field_metadata == 'one2many':
                        continue
                        
            #         if isinstance(relation_model, str):
            #             field_uniq = self.get_field_uniq_from_model(relation_model)

            #             if model == 'product.pricelist.item' and record['applied_on'] == '1_product':
            #                 pattern = r'\[(.*?)\]'
            #                 if pattern:
            #                     match = re.search(pattern, field_data)
            #                     field_data = match.group(1)
            #             if relation_model == 'account.account':
            #                 parts = field_data.split() # Menggunakan split untuk memisahkan string
            #                 field_data = parts[0] # Mengambil bagian pertama yang merupakan angka
                        
                        
            #             if model == 'stock.picking.type' and field_name in ('default_location_src_id', 'default_location_dest_id'):
            #                 datas = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
            #                                     self.target_client.uid, self.target_client.password,
            #                                     relation_model, 'search_read',
            #                                     [[['usage', '=', 'internal']]], {'fields': ['id']})
            #                 if len(datas) > 1:
            #                     multiple_wh_operation_types = True
            #             else:
            #                 datas_target = dict_relation_target[relation_model]
            #                 if isinstance(field_data, str):
            #                     datas_target_result = next((item['id'] for item in datas_target if item[field_uniq] == field_data), None)
            #                 elif isinstance(field_data, list):
            #                     datas_target_result = []
            #                     for value in field_data:
            #                         datas_target_notyet_result = next((item['id'] for item in datas_target if item[field_uniq] == value), None)
            #                         if datas_target_notyet_result is not None:
            #                             datas_target_result.append(datas_target_notyet_result)
            #                         else:
            #                             write_date = record['write_date']
            #                             self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", write_date)
            #                             self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", write_date)
                            
            #                 # datas = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
            #                 #                     self.target_client.uid, self.target_client.password,
            #                 #                     relation_model, 'search_read',
            #                 #                     [[[field_uniq, '=', field_data]]], {'fields': ['id']})
                            
                            
            #             if datas_target_result:
            #                 # if field_name == 'tag_ids' or field_name == 'taxes_id' or field_name == 'pos_categ_ids':
            #                     # value = [data['id'] for data in datas_target_result] if datas_target_result else False
            #                     # Jika value ada dan bukan list, bungkus dalam list
            #                     # record[field_name] = [datas_target_result] if datas_target_result and not isinstance(datas_target_result, list) else datas_target_result
            #                 if field_name == 'default_location_src_id' and record['code'] == 'outgoing':
            #                     record[field_name] = datas[0]['id'] if datas[0] else False
            #                 elif field_name == 'default_location_src_id' and record['code'] == 'incoming':
            #                     record[field_name] = False
            #                 elif field_name == 'default_location_dest_id' and record['code'] == 'outgoing':
            #                     record[field_name] = False
            #                 elif field_name == 'default_location_dest_id' and record['code'] == 'incoming':
            #                     record[field_name] = datas[0]['id'] if datas[0] else False
            #                 else:
            #                     record[field_name] = datas_target_result if datas_target_result else False # datas[0]['id'] if datas[0] else False
                            
            #             else:
            #                 if model == 'account.tax.repartition.line':
            #                     record[field_name] = field_value[0] if field_value else False
            #                 else:
            #                     self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
            #                     self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
            #                     return None  # Mengembalikan None jika kondisi else terpenuhi
            
            # if multiple_wh_operation_types and model == 'stock.picking.type':
            # # Tambahkan elemen baru ke dalam data_list
            #     for data in datas:
            #         # Buat salinan dari record
            #         new_record = record.copy()
            #         if record['code'] == 'outgoing':
            #             new_record['default_location_src_id'] = data['id'] if datas else False
            #             new_record['default_location_dest_id'] = False
            #         elif record['code'] == 'incoming':
            #             new_record['default_location_src_id'] = False
            #             new_record['default_location_dest_id'] = data['id'] if datas else False
                    
            #         if data['id'] != record['default_location_src_id'] and data['id'] != record['default_location_dest_id']:
            #             data_list.append(new_record)
            
            return record
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while validating record data: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while validating record data: {e}", None)

    # to get string value for many2one, many2many data type
    def validate_record_data_update(self, record, model, data_list, type_fields, relation_fields, dict_relation_source, dict_relation_target):
        try:
            multiple_wh_operation_types = False

            for field_name in relation_fields and type_fields:
                if field_name in record:
                    field_value = record[field_name]
                    
                    if not field_value :
                        if model == 'product.template'and (relation_fields[field_name] == 'account.tax' or relation_fields[field_name] == 'pos.category'):
                            record[field_name] = [(5, 0, 0)] # untuk delete
                        continue

                    field_metadata = type_fields[field_name]
                    relation_model = relation_fields[field_name]
                    
                    if field_metadata == 'many2one' and isinstance(field_value, list):
                        field_data = field_value[1] if field_value else False
                    elif field_metadata == 'many2many' and isinstance(field_value, list):
                        name_datas_source = dict_relation_source.get(relation_model, [])
                        field_data = [
                            next((item['name'] for item in name_datas_source if item['id'] == data), None)
                            for data in field_value
                        ]
                    elif field_metadata == 'one2many':
                        continue
                        
                    if isinstance(relation_model, str):
                        field_uniq = self.get_field_uniq_from_model(relation_model)

                        if model == 'product.pricelist.item' and record['applied_on'] == '1_product':
                            pattern = r'\[(.*?)\]'
                            if pattern:
                                match = re.search(pattern, field_data)
                                field_data = match.group(1)
                        if relation_model == 'account.account':
                            parts = field_data.split() # Menggunakan split untuk memisahkan string
                            field_data = parts[0] # Mengambil bagian pertama yang merupakan angka
                        
                        
                        if model == 'stock.picking.type' and field_name in ('default_location_src_id', 'default_location_dest_id'):
                            datas = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                self.target_client.uid, self.target_client.password,
                                                relation_model, 'search_read',
                                                [[['usage', '=', 'internal']]], {'fields': ['id']})
                            if len(datas) > 1:
                                multiple_wh_operation_types = True
                        else:
                            datas_target = dict_relation_target[relation_model]
                            if isinstance(field_data, str):
                                datas_target_result = next((item['id'] for item in datas_target if item[field_uniq] == field_data), None)
                            elif isinstance(field_data, list):
                                datas_target_result = []
                                for value in field_data:
                                    datas_target_notyet_result = next((item['id'] for item in datas_target if item[field_uniq] == value), None)
                                    if datas_target_notyet_result is not None:
                                        datas_target_result.append(datas_target_notyet_result)
                                    else:
                                        write_date = record['write_date']
                                        self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", write_date)
                                        self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", write_date)
                            
                            # datas = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                            #                     self.target_client.uid, self.target_client.password,
                            #                     relation_model, 'search_read',
                            #                     [[[field_uniq, '=', field_data]]], {'fields': ['id']})
                            
                            
                        if datas_target_result:
                            # if field_name == 'tag_ids' or field_name == 'taxes_id' or field_name == 'pos_categ_ids':
                                # value = [data['id'] for data in datas_target_result] if datas_target_result else False
                                # Jika value ada dan bukan list, bungkus dalam list
                                # record[field_name] = [datas_target_result] if datas_target_result and not isinstance(datas_target_result, list) else datas_target_result
                            if field_name == 'default_location_src_id' and record['code'] == 'outgoing':
                                record[field_name] = datas[0]['id'] if datas[0] else False
                            elif field_name == 'default_location_src_id' and record['code'] == 'incoming':
                                record[field_name] = False
                            elif field_name == 'default_location_dest_id' and record['code'] == 'outgoing':
                                record[field_name] = False
                            elif field_name == 'default_location_dest_id' and record['code'] == 'incoming':
                                record[field_name] = datas[0]['id'] if datas[0] else False
                            else:
                                record[field_name] = datas_target_result if datas_target_result else False # datas[0]['id'] if datas[0] else False
                            
                        else:
                            if model == 'account.tax.repartition.line':
                                record[field_name] = field_value[0] if field_value else False
                            else:
                                self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                                self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                                return None  # Mengembalikan None jika kondisi else terpenuhi
            
            if multiple_wh_operation_types and model == 'stock.picking.type':
            # Tambahkan elemen baru ke dalam data_list
                for data in datas:
                    # Buat salinan dari record
                    new_record = record.copy()
                    if record['code'] == 'outgoing':
                        new_record['default_location_src_id'] = data['id'] if datas else False
                        new_record['default_location_dest_id'] = False
                    elif record['code'] == 'incoming':
                        new_record['default_location_src_id'] = False
                        new_record['default_location_dest_id'] = data['id'] if datas else False
                    
                    if data['id'] != record['default_location_src_id'] and data['id'] != record['default_location_dest_id']:
                        data_list.append(new_record)
            
            return record
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while validating record data: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while validating record data: {e}", None)

    def validate_record_data_line_update(self, record, model, data_list, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
        try:
            for field_name in relation_fields_line:
                if field_name in record:
                    field_value = record[field_name]
                    
                    if not field_value :
                        if model == 'product.template'and (relation_fields_line[field_name] == 'account.tax' or relation_fields_line[field_name] == 'pos.category'):
                            record[field_name] = [(5, 0, 0)] # untuk delete
                        continue

                    field_metadata = type_fields_line[field_name]
                    relation_model = relation_fields_line[field_name]
                    
                    if (field_metadata == 'many2one') and isinstance(field_value, list):
                        field_data = field_value[1] if field_value else False
                        # if model == 'product.pricelist.item' and record['applied_on'] == '1_product':
                        #     pattern = r'\[(.*?)\]'
                        #     if pattern:
                        #         match = re.search(pattern, field_data)
                        #         field_data = match.group(1)
                        # record[field_name] = field_data
                    elif (field_metadata == 'many2many') and isinstance(field_value, list):
                        field_data_list = []
                        for field_data in field_value:
                            name_datas_source = dict_relation_source_line[relation_model]
                            name_datas_source_result = next((item['name'] for item in name_datas_source if item['id'] == field_data), None)
                            field_data_list.append(name_datas_source_result)
                        field_data = field_data_list
                        # record[field_name] = field_data
                    elif (field_metadata == 'one2many') and isinstance(field_value, list):
                        continue
                        
                    if isinstance(relation_model, str):
                        field_uniq = self.get_field_uniq_from_model(relation_model)

                        if model == 'product.pricelist.item' and record['applied_on'] == '1_product':
                            pattern = r'\[(.*?)\]'
                            if pattern:
                                match = re.search(pattern, field_data)
                                field_data = match.group(1)
                        if relation_model == 'account.account':
                            parts = field_data.split() # Menggunakan split untuk memisahkan string
                            field_data = parts[0] # Mengambil bagian pertama yang merupakan angka
                        
                        
                        if model == 'stock.picking.type' and field_name in ('default_location_src_id', 'default_location_dest_id'):
                            datas = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                self.target_client.uid, self.target_client.password,
                                                relation_model, 'search_read',
                                                [[['usage', '=', 'internal']]], {'fields': ['id']})
                        else:
                            datas_target = dict_relation_target_line[relation_model]
                            if isinstance(field_data, str):
                                datas_target_result = next((item['id'] for item in datas_target if item[field_uniq] == field_data), None)
                            elif isinstance(field_data, list):
                                datas_target_result = []
                                for value in field_data:
                                    datas_target_notyet_result = next((item['id'] for item in datas_target if item[field_uniq] == value), None)
                                    if datas_target_notyet_result is not None:
                                        datas_target_result.append(datas_target_notyet_result)
                                    else:
                                        write_date = record['write_date']
                                        self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", write_date)
                                        self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", write_date)
                            
                            # datas = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                            #                     self.target_client.uid, self.target_client.password,
                            #                     relation_model, 'search_read',
                            #                     [[[field_uniq, '=', field_data]]], {'fields': ['id']})
                            
                            
                        if datas_target_result:
                            record[field_name] = datas_target_result if datas_target_result else False # datas[0]['id'] if datas[0] else False
                            
                        else:
                            if model == 'account.tax.repartition.line':
                                record[field_name] = field_value[0] if field_value else False
                            else:
                                self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                                self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                                return None  # Mengembalikan None jika kondisi else terpenuhi
            return record
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while validating record data: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while validating record data: {e}", None)

    # to get string value for many2one, many2many data type
    def validate_record_data_line(self, record, model, data_list, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
        try:
            if model == 'product.pricelist.item':
                record['id_mc'] = record['id']
            for field_name in relation_fields_line:
                if field_name in record:
                    field_value = record[field_name]
                    
                    if not field_value :
                        if model == 'product.template'and (relation_fields_line[field_name] == 'account.tax' or relation_fields_line[field_name] == 'pos.category'):
                            record[field_name] = [(5, 0, 0)] # untuk delete
                        continue

                    field_metadata = type_fields_line[field_name]
                    relation_model = relation_fields_line[field_name]
                    
                    if (field_metadata == 'many2one') and isinstance(field_value, list):
                        field_data = field_value[1] if field_value else False
                    elif (field_metadata == 'many2many') and isinstance(field_value, list):
                        field_data_list = []
                        for field_data in field_value:
                            name_datas_source = dict_relation_source_line[relation_model]
                            name_datas_source_result = next((item['name'] for item in name_datas_source if item['id'] == field_data), None)
                            field_data_list.append(name_datas_source_result)
                        field_data = field_data_list
                    elif (field_metadata == 'one2many') and isinstance(field_value, list):
                        continue
                        
                    if isinstance(relation_model, str):
                        field_uniq = self.get_field_uniq_from_model(relation_model)

                        if model == 'product.pricelist.item' and record['applied_on'] == '1_product':
                            pattern = r'\[(.*?)\]'
                            if pattern:
                                match = re.search(pattern, field_data)
                                field_data = match.group(1)
                        if relation_model == 'account.account':
                            parts = field_data.split() # Menggunakan split untuk memisahkan string
                            field_data = parts[0] # Mengambil bagian pertama yang merupakan angka
                        
                        
                        if model == 'stock.picking.type' and field_name in ('default_location_src_id', 'default_location_dest_id'):
                            datas = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                self.target_client.uid, self.target_client.password,
                                                relation_model, 'search_read',
                                                [[['usage', '=', 'internal']]], {'fields': ['id']})
                        else:
                            datas_target = dict_relation_target_line[relation_model]
                            if isinstance(field_data, str):
                                datas_target_result = next((item['id'] for item in datas_target if item[field_uniq] == field_data), None)
                            elif isinstance(field_data, list):
                                datas_target_result = []
                                for value in field_data:
                                    datas_target_notyet_result = next((item['id'] for item in datas_target if item[field_uniq] == value), None)
                                    if datas_target_notyet_result is not None:
                                        datas_target_result.append(datas_target_notyet_result)
                                    else:
                                        write_date = record['write_date']
                                        self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", write_date)
                                        self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", write_date)
                            
                            # datas = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                            #                     self.target_client.uid, self.target_client.password,
                            #                     relation_model, 'search_read',
                            #                     [[[field_uniq, '=', field_data]]], {'fields': ['id']})
                            
                            
                        if datas_target_result:
                            record[field_name] = datas_target_result if datas_target_result else False # datas[0]['id'] if datas[0] else False
                            
                        else:
                            if model == 'account.tax.repartition.line':
                                record[field_name] = field_value[0] if field_value else False
                            else:
                                self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                                self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                                return None  # Mengembalikan None jika kondisi else terpenuhi
            return record
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while validating record data: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while validating record data: {e}", None)
    
    # def create_data(self, model, record, modul, id_mc, last_master_url, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
    #     try:
    #         # if model == 'product.pricelist':
    #         #     record['item_ids'] = self.transfer_pricelist_lines(record['id'], 'product.pricelist.item', [record], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line)
    #         if model == 'account.tax':
    #             record['invoice_repartition_line_ids'] = self.transfer_tax_lines_invoice(record['id'], 'account.tax.repartition.line', record)
    #             record['refund_repartition_line_ids'] = self.transfer_tax_lines_refund(record['id'], 'account.tax.repartition.line', record)    

    #         # menambahkan id mc
    #         record['id_mc'] = id_mc
            
    #         return record

    #         # start_time = time.time()
    #         # create = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
    #         #                              self.target_client.password, model, 'create', [record])
    #         # end_time = time.time()
    #         # duration = end_time - start_time

    #         # id = record.get('id')
    #         # if create:
    #         #     if self.target_client.url == last_master_url + "jsonrpc":
    #         #         self.update_isintegrated_source(model, id)

    #         #     write_date = record['write_date']
    #         #     self.set_log_mc.create_log_note_success(record, start_time, end_time, duration, modul, write_date, self.source_client.server_name, self.target_client.server_name)
    #         #     self.set_log_ss.create_log_note_success(record, start_time, end_time, duration, modul, write_date)

    #         #     # self.set_log_mc.delete_data_log_failed(record['name'])
    #         #     # self.set_log_ss.delete_data_log_failed(record['name'])

    #     except Exception as e:
    #         id = record.get('id')
    #         write_date = record['write_date']
    #         self.set_log_mc.create_log_note_failed(record, modul, e, write_date)
    #         self.set_log_ss.create_log_note_failed(record, modul, e, write_date)

    def transfer_pricelist_lines_update(self, pricelist_lines, model, record, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
        try:
            formatted_pricelist_lines = []
            # Function to process each line
            def process_line(line): # 0, 0, 
                return (self.validate_record_data_line_update(line, model, [pricelist_lines], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line))
        
            # Use ThreadPoolExecutor to parallelize the processing of lines
            with ThreadPoolExecutor(max_workers=10) as executor:  # max_workers menentukan berapa thread yang digunakan
                future_to_line = {executor.submit(process_line, line): line for line in pricelist_lines}

                for future in as_completed(future_to_line):
                    try:
                        result = future.result()
                        formatted_pricelist_lines.append(result)
                    except Exception as e:
                        # Log error jika ada masalah di thread tertentu
                        line = future_to_line[future]
                        self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while processing pricelist line: {e}", None)
                        self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while processing pricelist line: {e}", None)

            formatted_pricelist_lines = sorted(formatted_pricelist_lines, key=lambda x: x.get('id', 0))
            return formatted_pricelist_lines
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while transfer pricelist lines: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while transfer pricelist lines: {e}", None)
    
    def transfer_pricelist_lines_update_target(self, pricelist_lines, model, record, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
        try:
            formatted_pricelist_lines = []
            # Function to process each line
            def process_line(line): # 0, 0, 
                return (self.validate_record_data_line_update(line, model, [record], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line))
        
            # Use ThreadPoolExecutor to parallelize the processing of lines
            with ThreadPoolExecutor(max_workers=10) as executor:  # max_workers menentukan berapa thread yang digunakan
                future_to_line = {executor.submit(process_line, line): line for line in pricelist_lines}

                for future in as_completed(future_to_line):
                    try:
                        result = future.result()
                        formatted_pricelist_lines.append(result)
                    except Exception as e:
                        # Log error jika ada masalah di thread tertentu
                        line = future_to_line[future]
                        self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while processing pricelist line: {e}", None)
                        self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while processing pricelist line: {e}", None)

            formatted_pricelist_lines = sorted(formatted_pricelist_lines, key=lambda x: x.get('id', 0))
            return formatted_pricelist_lines
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while transfer pricelist lines: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while transfer pricelist lines: {e}", None)
    
    def transfer_pricelist_lines(self, pricelist_lines, model, record, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
        try:
            formatted_pricelist_lines = []

            # for line in pricelist_lines:
            #     valid_lines = self.validate_record_data_line(line, model, [record], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line)                
            #     formatted_pricelist_lines.append((0, 0, valid_lines))

            # Function to process each line
            def process_line(line):
                return (0, 0, self.validate_record_data_line(line, model, [record], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line))
        
            # Use ThreadPoolExecutor to parallelize the processing of lines
            with ThreadPoolExecutor(max_workers=10) as executor:  # max_workers menentukan berapa thread yang digunakan
                future_to_line = {executor.submit(process_line, line): line for line in pricelist_lines}

                for future in as_completed(future_to_line):
                    try:
                        result = future.result()
                        formatted_pricelist_lines.append(result)
                    except Exception as e:
                        # Log error jika ada masalah di thread tertentu
                        line = future_to_line[future]
                        self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while processing pricelist line: {e}", None)
                        self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while processing pricelist line: {e}", None)

            formatted_pricelist_lines = sorted(formatted_pricelist_lines, key=lambda x: x[2].get('id', 0))
            return formatted_pricelist_lines
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while transfer pricelist lines: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while transfer pricelist lines: {e}", None)

    def transfer_pricelist_lines_target(self, pricelist_lines, model, record, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
        try:
            # fields = ['product_tmpl_id', 'min_quantity', 'fixed_price', 'date_start', 'date_end', 'compute_price', 'percent_price', 'base', 'price_discount', 'price_surcharge', 'price_round', 'price_min_margin', 'applied_on', 'categ_id', 'product_id', 'id_mc']
            # lines = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
            #                                     self.target_client.uid, self.target_client.password,
            #                                     model, 'search_read',
            #                                     [[['pricelist_id', '=', pricelist_id]]],
            #                                     {'fields': fields})

            formatted_invoice_lines = []
            for line in pricelist_lines:
                valid_lines = self.validate_record_data_line(line, model, [record], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line)
                formatted_invoice_lines.append((0, 0, valid_lines))

            formatted_invoice_lines = sorted(formatted_invoice_lines, key=lambda x: x[2].get('id', 0))
            return formatted_invoice_lines
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while transfer pricelist lines: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while transfer pricelist lines: {e}", None)

    def transfer_tax_lines_invoice(self, taxes_line, model, record, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
        try:
            # fields = ['tax_id','factor_percent','repartition_type', 'account_id','tag_ids', 'document_type', 'use_in_tax_closing']
            # lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
            #                                     self.source_client.uid, self.source_client.password,
            #                                     model, 'search_read',
            #                                     [[['tax_id', '=', tax_id], ['document_type', '=', 'invoice']]],
            #                                     {'fields': fields})

            formatted_invoice_lines = []
            # for line in taxes_line:
            #     valid_lines = self.validate_record_data_line(line, model, [record])
            #     formatted_invoice_lines.append((0, 0, valid_lines))

            # Function to process each line
            def process_line(line):
                return (0, 0, self.validate_record_data_line(line, model, [record], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line))
        
            # Use ThreadPoolExecutor to parallelize the processing of lines
            with ThreadPoolExecutor(max_workers=10) as executor:  # max_workers menentukan berapa thread yang digunakan
                future_to_line = {executor.submit(process_line, line): line for line in taxes_line}

                for future in as_completed(future_to_line):
                    try:
                        result = future.result()
                        formatted_invoice_lines.append(result)
                    except Exception as e:
                        # Log error jika ada masalah di thread tertentu
                        line = future_to_line[future]
                        self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while processing pricelist line: {e}", None)
                        self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while processing pricelist line: {e}", None)

            formatted_invoice_lines = sorted(formatted_invoice_lines, key=lambda x: x[2].get('id', 0))
            return formatted_invoice_lines
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while transfer tax lines invoice: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while transfer tax lines invoice: {e}", None)

    def transfer_tax_lines_refund(self, taxes_line, model, record, dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line):
        try:
            # fields = ['tax_id','factor_percent','repartition_type', 'account_id','tag_ids', 'document_type', 'use_in_tax_closing']
            # lines = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
            #                                     self.source_client.uid, self.source_client.password,
            #                                     model, 'search_read',
            #                                     [[['tax_id', '=', tax_id], ['document_type', '=', 'refund']]],
            #                                     {'fields': fields})

            formatted_refund_lines = []
            # for line in taxes_line:
            #     valid_lines = self.validate_record_data_line(line, model, [record])
            #     formatted_refund_lines.append((0, 0, valid_lines))

            # Function to process each line
            def process_line(line):
                return (0, 0, self.validate_record_data_line(line, model, [record], dict_relation_source_line, dict_relation_target_line, type_fields_line, relation_fields_line))
        
            # Use ThreadPoolExecutor to parallelize the processing of lines
            with ThreadPoolExecutor(max_workers=10) as executor:  # max_workers menentukan berapa thread yang digunakan
                future_to_line = {executor.submit(process_line, line): line for line in taxes_line}

                for future in as_completed(future_to_line):
                    try:
                        result = future.result()
                        formatted_refund_lines.append(result)
                    except Exception as e:
                        # Log error jika ada masalah di thread tertentu
                        line = future_to_line[future]
                        self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while processing pricelist line: {e}", None)
                        self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while processing pricelist line: {e}", None)

            formatted_refund_lines = sorted(formatted_refund_lines, key=lambda x: x[2].get('id', 0))
            return formatted_refund_lines
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"An error occurred while transfer tax lines refund: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"An error occurred while transfer tax lines refund: {e}", None)
    
    
    def update_data(self, model, record_id, updated_fields, modul, record, last_master_url, target_record):
        try:
            if model == 'product.pricelist':
                # record['item_ids'] = self.transfer_pricelist_lines(record['id'], 'product.pricelist.item', record)
                # target_record['item_ids'] = self.transfer_pricelist_lines_target(target_record['id'], 'product.pricelist.item', target_record)
                length_of_item_ids = len(record['item_ids'])
                length_of_item_ids_target_record = len(target_record['item_ids'])

                if length_of_item_ids > length_of_item_ids_target_record:
                    lines_update = record['item_ids']
                    lines_target = target_record['item_ids']
                    filtered_lines = [item[2] for item in lines_update if item[2]['id'] not in lines_target]
                    
                    if filtered_lines:
                        for line in filtered_lines:
                            line['pricelist_id'] = record_id
                        
                        start_time = time.time()
                        create = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                         self.target_client.password, 'product.pricelist.item', 'create', [filtered_lines])
                        end_time = time.time()
                        duration = end_time - start_time

                        if create:
                            write_date = record['write_date']
                            self.set_log_mc.create_log_note_update_success(record, record_id, filtered_lines, start_time, end_time, duration, modul, write_date, self.source_client.server_name, self.target_client.server_name)
                            self.set_log_ss.create_log_note_update_success(record, record_id, filtered_lines, start_time, end_time, duration, modul, write_date)

                    updated_fields['item_ids'] = target_record['item_ids']

                # elif length_of_item_ids <= length_of_item_ids_target_record:
                #     lines_update = record['item_ids']
                #     lines_target = target_record['item_ids']
                #     # filtered_lines = [item[2] for item in lines_target if item[2]['id'] not in lines_target]
                    
                #     # if filtered_lines:
                #     #     for line in filtered_lines:
                #     #         line['pricelist_id'] = record_id
                #     delete = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                #                          self.target_client.password, 'product.pricelist.item', 'unlink', [target_record['item_ids']])
                    
                #     updated_fields['item_ids'] = target_record['item_ids']
                    
            # elif model == 'account.tax':
            #     record['invoice_repartition_line_ids'] = self.transfer_tax_lines_invoice(record['id'], 'account.tax.repartition.line', record)
            #     record['refund_repartition_line_ids'] = self.transfer_tax_lines_refund(record['id'], 'account.tax.repartition.line', record)    
            
            start_time = time.time()
            update = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                        self.target_client.password, model, 'write', [record_id, updated_fields])
            end_time = time.time()
            duration = end_time - start_time

            if update:
                return record, [record_id], updated_fields, start_time, end_time, duration
            
        except Exception as e:
            write_date = record['write_date']
            self.set_log_mc.create_log_note_failed(record, modul, e, write_date)
            self.set_log_ss.create_log_note_failed(record, modul, e, write_date)

    
    def update_indexstore_source(self, model, id, index_store_field):
        try:
            # if model == 'res.partner' or model == 'product.template':
            self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                            self.source_client.password, model, 'write', [id, {'index_store': [(4, index_store_field)]}]) # index_store_field
            # if model == 'product.pricelist':
            #     self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
            #                                 self.source_client.password, 'product.pricelist.item', 'write', [id, {'is_integrated': True}])
            # elif model == 'account.tax':
            #     self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
            #                                 self.source_client.password, 'account.tax.repartition.line', 'write', [id, {'is_integrated': True}])
  
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    
    def update_isintegrated_source(self, model, id):
        try:
            # if model == 'res.partner' or model == 'product.template':
            self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                            self.source_client.password, model, 'write', [id, {'is_integrated': True, 'index_store': [(5, 0, 0)]}])
  
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.source_client.server_name} to {self.target_client.server_name}", f"Error occurred when update is_integrated target: {e}", None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, f"Error occurred when update is_integrated target: {e}", None)
    
    def create_staging(self, model, record):
        try:
            url = "http://192.168.1.104:8069"
            db = "MasterConsole"
            username = "admin"
            password = "68057350f2cd9827a46537ffc87a2e29aef92ecc"
            
            # Autentikasi ke Odoo
            common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
            uid = common.authenticate(db, username, password, {})
            
            # Mengonversi record ke string
            record_string = json.dumps(record)
            
            # Memanggil model 'log_code_runtime' untuk membuat record
            models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
            models.execute_kw(db, uid, password, 'log.code.runtime', 'create', [{'vit_code_type': record_string, 'vit_duration': model}])

        except Exception as e:
            print(f"An error occurred while creating data staging test: {e}")
        



    # Store Server --> Master Console
    def get_existing_data_mc(self, model, field_uniq, fields):
        try:
            existing_data = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password, model,
                                                        'search_read', [[[field_uniq, '!=', False]]], {'fields': fields}) # , {'fields': [field_uniq]}
            return existing_data
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    def get_data_list_ss(self, model, fields, field_uniq, date_from, date_to):
        try:
            # hanya model res.partner.title, res.partner, hr.employee
            if model == 'res.partner':
                data_list = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                                    self.target_client.password, model, 'search_read', [[[field_uniq, '!=', False], ['employee_ids', '=', []], ['is_integrated', '=', True], ['write_date', '>=', date_from], ['write_date', '<=', date_to]]],
                                                    {'fields': fields}) # , 'limit': 1  
            elif model == 'hr.employee':
                data_list = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                                    self.target_client.password, model, 'search_read', [[[field_uniq, '!=', False], ['is_integrated', '=', True], ['write_date', '>=', date_from], ['write_date', '<=', date_to]]],
                                                    {'fields': fields}) # , 'limit': 1 
            elif model == 'loyalty.card':
                currency = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                                    self.target_client.password, 'loyalty.program', 'search_read', [[]], {'fields': ['currency_id'], 'limit': 1})
                currency_id = currency[0]['currency_id'][0]
                data_list = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                                    self.target_client.password, model, 'search_read', [[['code','=', '044d-ab69-4a4a'], ['currency_id','=', currency_id], ['is_integrated', '=', True], [field_uniq, '!=', False], ['write_date', '>=', date_from], ['write_date', '<=', date_to]]],
                                                    {'fields': fields, 'limit': 1}) # ['code','=', '044d-ab69-4a4a']
            elif model == 'res.partner.title':
                data_list = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                                    self.target_client.password, model, 'search_read', [[[field_uniq, '!=', False], ['write_date', '>=', date_from], ['write_date', '<=', date_to]]],
                                                    {'fields': fields})

            return data_list
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    def transfer_data_mc(self, model, fields, modul, date_from, date_to):
        try:
            field_uniq = self.get_field_uniq_from_model(model)
            data_list = self.get_data_list_ss(model, fields, field_uniq, date_from, date_to) # 1 calling odoo
            
            # id_create = 6
            # id_ss = [6]
            # self.update_idmc_source_ss(model, id_create, id_ss)
             # buat update dadakan di mc
            # ids = [item['id'] for item in data_list]
            # self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
            #                                    self.target_client.password, model, 'write', [ids, {'is_integrated': False}]) # ,  'mobile': '+62', 'website': 'wwww.test_cust.co.id', 'title': 3
            # for id in ids:
            #     self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
            #                                     self.source_client.password, model, 'write', [id, {'customer_code': f"Cust_test{id}"}]) # {'is_integrated': False }, 'categ_id' : 7, 'available_in_pos' : False

            if data_list:
                existing_data_target_mc = self.get_existing_data_mc(model, field_uniq, fields)  # 2 calling odoo
                existing_data_mc = {data[field_uniq] for data in existing_data_target_mc}
                type_fields, relation_fields = self.get_type_data_source(model, fields) # 3 calling odoo

                dict_relation_source = {}
                dict_relation_target = {}
                for relation in relation_fields:
                    relation_model = relation_fields[relation]
                    many_source = self.get_relation_source_all(relation_model) # 4 (1 x relation_fields) calling odoo # pilih mau field apa aja?
                    dict_relation_source[relation_model] = many_source
                    # many_target = self.get_relation_target_all(relation_model) # 5 (1 x relation_fields) calling odoo # pilih mau field apa aja?
                    # dict_relation_target[relation_model] = many_target
                
                filtered_data_for_create = [item for item in data_list if item[field_uniq] not in existing_data_mc]
                filtered_data_for_update = [item for item in data_list if item[field_uniq] in existing_data_mc]
                
                self.process_data_async_create_mc(model, filtered_data_for_create, modul, type_fields, relation_fields, dict_relation_source, dict_relation_target)    
                self.process_data_async_update_mc(model, field_uniq, filtered_data_for_update, modul, type_fields, relation_fields, existing_data_target_mc, dict_relation_source, dict_relation_target)
            
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    def process_data_async_create_mc(self, model, partial_data, modul, type_fields, relation_fields, dict_relation_source, dict_relation_target):
        try:
            data_for_create = []
            log_data_created = []
            id_ss_for_update_isintegrated = []
            # Dapatkan data yang sudah ada di target
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = []
                # Kirim setiap record dalam partial_data untuk diproses secara asinkron
                for record in partial_data:
                    future = executor.submit(self.transfer_record_data_create_mc, model, record, type_fields, relation_fields, dict_relation_source, dict_relation_target)
                    futures.append(future)
                # Tunggu semua proses selesai
                for future in concurrent.futures.as_completed(futures):
                    try:
                        valid_record = future.result()
                        if valid_record:
                            data_for_create.append(valid_record)
                    except Exception as e:
                        self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
                        self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

            if data_for_create:
                start_time = time.time()
                create = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                            self.source_client.password, model, 'create', [data_for_create])
                end_time = time.time()
                duration = end_time - start_time
                print(create)

                if create:
                    for index, data_create in enumerate(data_for_create):
                        id_ss = data_create['id']
                        id_create = create[index]
                        self.update_idmc_source_ss(model, id_create, id_ss)
                        write_date = data_create['write_date']
                        log_record = self.set_log_mc.log_record_success(data_create, start_time, end_time, duration, modul, write_date, self.target_client.server_name, self.source_client.server_name)
                        log_data_created.append(log_record)
                        id_ss_for_update_isintegrated.append(id_ss)

                    if model == 'loyalty.card':
                        self.update_isintegrated_source_ss(model, id_ss_for_update_isintegrated)

                    self.set_log_mc.create_log_note_success(log_data_created)
                    self.set_log_ss.create_log_note_success(log_data_created)

            # #     # self.set_log_mc.delete_data_log_failed(record['name'])
            # #     # self.set_log_ss.delete_data_log_failed(record['name'])
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    def process_data_async_update_mc(self, model, field_uniq, partial_data, modul, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target):
        try:
            data_for_update = []
            log_data_updated = []
            id_ss_for_update_isintegrated = []
            # Dapatkan data yang sudah ada di target
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = []
                # Kirim setiap record dalam partial_data untuk diproses secara asinkron
                for record in partial_data:
                    future = executor.submit(self.transfer_record_data_update_mc, model, field_uniq, record, modul, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target)
                    futures.append(future)
                # Tunggu semua proses selesai
                for future in concurrent.futures.as_completed(futures):
                    try:
                        valid_record = future.result()
                        if valid_record:
                            data_for_update.append(valid_record)

                    except Exception as e:
                        self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
                        self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

            if data_for_update:
                for data_update in data_for_update:
                    id_mc = data_update[0]['id']
                    write_date = data_update[0]['write_date']
                    log_record = self.set_log_mc.log_update_record_success(data_update[0], data_update[1], data_update[2], data_update[3], data_update[4], data_update[5], modul, write_date, self.target_client.server_name, self.source_client.server_name)
                    log_data_updated .append(log_record)
                    id_ss_for_update_isintegrated.append(id_mc)
            
                print(log_data_updated)
                self.update_isintegrated_source_ss(model, id_ss_for_update_isintegrated)

                self.set_log_mc.create_log_note_update_success(log_data_updated)
                self.set_log_ss.create_log_note_update_success(log_data_updated)

        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    def transfer_record_data_create_mc(self, model, record, type_fields, relation_fields, dict_relation_source, dict_relation_target):
        try:
            id_mc = record['id']
            valid_record = self.validate_record_data_mc(record, model, type_fields, relation_fields, dict_relation_source, dict_relation_target)
            if valid_record:
                return record
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)
    
    def transfer_record_data_update_mc(self, model, field_uniq, record, modul, type_fields, relation_fields, existing_data_target, dict_relation_source, dict_relation_target):
        try:
            code = record.get(field_uniq)
            target_record = next((item for item in existing_data_target if item[field_uniq] == code), None)
            updated_fields = {field: record[field] for field in record if record.get(field) != target_record.get(field) and field not in ('id', 'create_date', 'write_date')}

            if updated_fields: 
                keys_to_remove = []
                fields_many2one_to_check = ['title', 'program_id', 'partner_id']
                for field in updated_fields:
                    if field in fields_many2one_to_check:
                        if record[field][1] == target_record[field][1]:
                            keys_to_remove.append(field) 
                # Remove the fields after iteration
                for key in keys_to_remove:
                    del updated_fields[key]

                if updated_fields: 
                    valid_record = self.validate_record_data_update_mc(updated_fields, model, type_fields, relation_fields, dict_relation_source, dict_relation_target)
                    if valid_record:
                        record_id = target_record.get('id')
                        data_for_update = self.update_data_mc(model, record_id, valid_record, modul, record)
        
                        return data_for_update
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)
    
    # to get string value for many2one data type
    def validate_record_data_mc(self, record, model, type_fields, relation_fields, dict_relation_source, dict_relation_target):
        try:
            for field_name in relation_fields and type_fields:
                field_value = record[field_name]
                
                if field_value:
                    field_metadata = type_fields[field_name]
                    relation_model = relation_fields[field_name]

                    if field_metadata == 'many2one' and isinstance(field_value, list):
                        field_data = field_value[1] if field_value else False
                        
                    if isinstance(relation_model, str):
                        field_uniq = self.get_field_uniq_from_model(relation_model)
                        if model == 'loyalty.card' and relation_model == 'res.partner':
                            field_uniq = 'name'
                        
                        datas_target = dict_relation_source[relation_model]
                        if isinstance(field_data, str):
                            datas_target_result = next((item['id'] for item in datas_target if item[field_uniq] == field_data), None)
                        
                        if datas_target_result:
                            record[field_name] = datas_target_result if datas_target_result else False # datas[0]['id'] if datas[0] else False
                        else:
                            self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                            self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                            return None  # Mengembalikan None jika kondisi else terpenuhi
            return record
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    # to get string value for many2one data type
    def validate_record_data_update_mc(self, record, model, type_fields, relation_fields, dict_relation_source, dict_relation_target):
        try:
            for field_name in relation_fields and type_fields:
                if field_name in record:
                    field_value = record[field_name]
                    
                    if field_value :
                        field_metadata = type_fields[field_name]
                        relation_model = relation_fields[field_name]
                        
                        if field_metadata == 'many2one' and isinstance(field_value, list):
                            field_data = field_value[1] if field_value else False
                        
                        if isinstance(relation_model, str):
                            field_uniq = self.get_field_uniq_from_model(relation_model)
                            if model == 'loyalty.card' and relation_model == 'res.partner':
                                field_uniq = 'name'
                            
                            datas_target = dict_relation_source[relation_model]
                            if isinstance(field_data, str):
                                datas_target_result = next((item['id'] for item in datas_target if item[field_uniq] == field_data), None)
                            
                            if datas_target_result:
                                record[field_name] = datas_target_result if datas_target_result else False # datas[0]['id'] if datas[0] else False 
                            else:
                                self.set_log_mc.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                                self.set_log_ss.create_log_note_failed(record, model, f"{field_uniq} {field_data} in {relation_model} not exist", None)
                                return None  # Mengembalikan None jika kondisi else terpenuhi
            return record
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)
    
    def update_data_mc(self, model, record_id, updated_fields, modul, record):
        try:
            start_time = time.time()
            update = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                        self.source_client.password, model, 'write', [record_id, updated_fields])
            end_time = time.time()
            duration = end_time - start_time

            if update:
                return record, [record_id], updated_fields, start_time, end_time, duration
            
        except Exception as e:
            write_date = record['write_date']
            self.set_log_mc.create_log_note_failed(record, modul, e, write_date)
            self.set_log_ss.create_log_note_failed(record, modul, e, write_date)

    def update_isintegrated_source_ss(self, model, id):
        try:
            if model == 'res.partner' or model == 'hr.employee' or model == 'loyalty.card':
                self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                            self.target_client.password, model, 'write', [id, {'is_integrated': False}])
            
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)

    def update_idmc_source_ss(self, model, id_mc, id):
        try:
            if model == 'res.partner' or model == 'hr.employee':
                self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                            self.target_client.password, model, 'write', [id, {'id_mc': id_mc, 'is_integrated': False}])
            
        except Exception as e:
            self.set_log_mc.create_log_note_failed(f"Exception - {model}", f"{model} from {self.target_client.server_name} to {self.source_client.server_name}", e, None)
            self.set_log_ss.create_log_note_failed(f"Exception - {model}", model, e, None)


class SetLogMC:
    def __init__(self, source_client):
        self.source_client = source_client

    def log_record_success(self, record, start_time, end_time, duration, modul, write_date, source, target):
        gmt_7_now = datetime.now() #- timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        gmt_7_start_time = datetime.fromtimestamp(start_time) #- timedelta(hours=7)
        gmt_7_end_time = datetime.fromtimestamp(end_time) #- timedelta(hours=7)

        if record.get('code'):
            key = record.get('code')
        elif record.get('complete_name'):
            key = record.get('complete_name')
        else:
            key = record.get('name')

        record_log_success = {
            'vit_doc_type': f"{modul} from {source} to {target}",
            'vit_trx_key': key,
            'vit_trx_date': write_date,
            'vit_sync_date': gmt_7_now.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_sync_status': 'Success',
            'vit_sync_desc': f"Data yang masuk: {record}",
            'vit_start_sync': gmt_7_start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_end_sync': gmt_7_end_time.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_duration' : f"{duration:.2f} second"
        }
        return record_log_success
    
    def log_update_record_success(self, record, record_id, updated_fields, start_time, end_time, duration, modul, write_date, source, target):
        gmt_7_now = datetime.now() #- timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        gmt_7_start_time = datetime.fromtimestamp(start_time) #- timedelta(hours=7)
        gmt_7_end_time = datetime.fromtimestamp(end_time) #- timedelta(hours=7)

        if record.get('code'):
            key = record.get('code')
        elif record.get('complete_name'):
            key = record.get('complete_name')
        else:
            key = record.get('name')

        record_log_success = {
            'vit_doc_type': f"Update: {modul} from {source} to {target}",
            'vit_trx_key': key,
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
        gmt_7_now = datetime.now() #- timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        
        if isinstance(sync_status, str) is False:
            sync_status = sync_status.args[0]
            if isinstance(sync_status, str) is False:
                sync_status = sync_status['data']['message']

        if isinstance(record, str):
            key = record  # Jika record adalah string, gunakan langsung sebagai key
        else:
            # Jika record adalah dictionary atau object, ambil key dari 'code' atau 'name'
            if record.get('code'):
                key = record.get('code')
            elif record.get('complete_name'):
                key = record.get('complete_name')
            else:
                key = record.get('name')

        record_log_failed = {
            'vit_doc_type': modul,
            'vit_trx_key': key,
            'vit_trx_date': write_date,
            'vit_sync_date': gmt_7_now.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_sync_status': 'Failed',
            'vit_sync_desc': sync_status
        }
        return record_log_failed 

    def delete_data_log_failed(self, key_success):
        try:
            list_log_failed = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'log.note', 'search_read', [[['vit_sync_status', '=', 'Failed'], ['vit_trx_key', '=', key_success]]])
            for record in list_log_failed:
                self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                            self.source_client.password, 'log.note', 'unlink', [[record['id']]])
        except Exception as e:
            print(f"An error occurred while deleting data: {e}")
    
    def delete_data_log_expired(self):
        try:
            expired_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            list_log_expired = self.source_client.call_odoo('object', 'execute_kw', self.source_client.db,
                                                        self.source_client.uid, self.source_client.password,
                                                        'log.note', 'search_read', [[['vit_sync_date', '<=', expired_date]]])

            for record in list_log_expired:
                self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                            self.source_client.password, 'log.note', 'unlink', [[record['id']]])
        except Exception as e:
            print(f"An error occurred while deleting data: {e}")

    def create_log_note_success(self, log_record):
        try:
            self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                         self.source_client.password, 'log.note', 'create', [log_record])
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def create_log_note_update_success(self, log_record):
        try:
            # log_record = self.log_update_record_success(record, record_id, updated_fields, start_time, end_time, duration, modul, write_date, source, target)
            self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                         self.source_client.password, 'log.note', 'create', [log_record])
            # print(f"Data log note yang masuk: {log_record}")
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def create_log_note_failed(self, record, modul, sync_status, write_date):
        try:
            log_record = self.log_record_failed(record, modul, sync_status, write_date)
            log_record_existing = self.get_log_note_failed(log_record['vit_trx_key'], log_record['vit_sync_desc'])
            if not log_record_existing:
                self.source_client.call_odoo('object', 'execute_kw', self.source_client.db, self.source_client.uid,
                                            self.source_client.password, 'log.note', 'create', [log_record])
                # print(f"Data log note yang masuk: {log_record}")
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
        gmt_7_now = datetime.now() #- timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        gmt_7_start_time = datetime.fromtimestamp(start_time) #- timedelta(hours=7)
        gmt_7_end_time = datetime.fromtimestamp(end_time) #- timedelta(hours=7)
        
        if record.get('code'):
            key = record.get('code')
        elif record.get('complete_name'):
            key = record.get('complete_name')
        else:
            key = record.get('name')

        record_log_success = {
            'vit_doc_type': modul,
            'vit_trx_key': key,
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
        gmt_7_now = datetime.now() #- timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        gmt_7_start_time = datetime.fromtimestamp(start_time) #- timedelta(hours=7)
        gmt_7_end_time = datetime.fromtimestamp(end_time) #- timedelta(hours=7)
        
        if record.get('code'):
            key = record.get('code')
        elif record.get('complete_name'):
            key = record.get('complete_name')
        else:
            key = record.get('name')

        record_log_success = {
            'vit_doc_type': f"Update: {modul}",
            'vit_trx_key': key,
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
        gmt_7_now = datetime.now() #- timedelta(hours=7)  # Odoo menggunakan UTC, belum diatur zona waktunya
        
        if isinstance(sync_status, str) is False:
            sync_status = sync_status.args[0]
            if isinstance(sync_status, str) is False:
                sync_status = sync_status['data']['message']

        if isinstance(record, str):
            key = record  # Jika record adalah string, gunakan langsung sebagai key
        else:
            # Jika record adalah dictionary atau object, ambil key dari 'code' atau 'name'
            if record.get('code'):
                key = record.get('code')
            elif record.get('complete_name'):
                key = record.get('complete_name')
            else:
                key = record.get('name')

        record_log_failed = {
            'vit_doc_type': modul,
            'vit_trx_key': key,
            'vit_trx_date': write_date,
            'vit_sync_date': gmt_7_now.strftime('%Y-%m-%d %H:%M:%S'),
            'vit_sync_status': 'Failed',
            'vit_sync_desc': sync_status
        }
        return record_log_failed

    def delete_data_log_failed(self, key_success):
        try:
            list_log_failed = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        'log.note', 'search_read', [[['vit_sync_status', '=', 'Failed'], ['vit_trx_key', '=', key_success]]])
            for record in list_log_failed:
                self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                            self.target_client.password, 'log.note', 'unlink', [[record['id']]])
        except Exception as e:
            print(f"An error occurred while deleting data: {e}")

    def delete_data_log_expired(self):
        try:
            expired_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            list_log_expired = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password,
                                                        'log.note', 'search_read', [[['vit_sync_date', '<=', expired_date]]])

            for record in list_log_expired:
                self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                            self.target_client.password, 'log.note', 'unlink', [[record['id']]])
        except Exception as e:
            print(f"An error occurred while deleting data: {e}")

    def create_log_note_success(self, log_record):
        try:
            self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                         self.target_client.password, 'log.note', 'create', [log_record])
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def create_log_note_update_success(self, log_record):
        try:
            # log_record = self.log_update_record_success(record, record_id, updated_fields, start_time, end_time, duration, modul, write_date)
            self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                         self.target_client.password, 'log.note', 'create', [log_record])
            # print(f"Data log note yang masuk: {log_record}")
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def create_log_note_failed(self, record, modul, sync_status, write_date):
        try:
            log_record = self.log_record_failed(record, modul, sync_status, write_date)
            log_record_existing = self.get_log_note_failed(log_record['vit_trx_key'], log_record['vit_sync_desc'])
            if not log_record_existing:
                self.target_client.call_odoo('object', 'execute_kw', self.target_client.db, self.target_client.uid,
                                            self.target_client.password, 'log.note', 'create', [log_record])
                # print(f"Data log note yang masuk: {log_record}")
        except Exception as e:
            print(f"An error occurred while creating log note: {e}")

    def get_log_note_failed(self, key, desc):
        log_note_failed = self.target_client.call_odoo('object', 'execute_kw', self.target_client.db,
                                                        self.target_client.uid, self.target_client.password, 'log.note',
                                                        'search_read', [[['vit_trx_key', '=', key], ['vit_sync_desc', '=', desc] , ['vit_sync_status', '=', 'Failed']]])
        return log_note_failed
