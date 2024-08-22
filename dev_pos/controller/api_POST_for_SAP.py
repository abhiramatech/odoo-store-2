from odoo import http
from odoo.http import request
import requests
from datetime import datetime
import json
import logging
import base64

_logger = logging.getLogger(__name__)

class POSTMasterItem(http.Controller):
    @http.route('/api/master_item', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_item(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = data = request.get_json_data()
            product_code = data.get('product_code')

            if env['product.template'].sudo().search([('default_code', '=', product_code)], limit=1):
                return {'status': "Failed", 'code': 400, 'message': f"Duplicate item code: {product_code}."}
            
            category = env['product.category'].sudo().search([('complete_name', '=', data.get('category_name'))], limit=1)
            if not category:
                return {'status': "Failed", 'code': 400, 'message': f"Category not found: {data.get('category_name')}."}
            
            pos_categ_command = []
            for categ_id in data.get('pos_categ_ids', []):
                if env['pos.category'].sudo().search([('id', '=', categ_id)], limit=1):
                    pos_categ_command.append((4, categ_id))
                else:
                    return {'status': "Failed", 'code': 400, 'message': f"POS category with ID {categ_id} not found."}

            tax_command = []
            for tax_name in data.get('taxes_names', []):
                tax = env['account.tax'].sudo().search([('name', '=', tax_name)], limit=1)
                if tax:
                    tax_command.append((4, tax.id))
                else:
                    return {'status': "Failed", 'code': 400, 'message': f"Tax with name '{tax_name}' not found."}

            item_data = {
                'name': data.get('product_name'),
                'active': data.get('active'),
                'default_code': product_code,
                'detailed_type': data.get('product_type'),
                'invoice_policy': data.get('invoice_policy'),
                'create_date': data.get('create_date'),
                'list_price': data.get('sales_price'),
                'standard_price': data.get('cost'),
                'uom_id': data.get('uom_id'),
                'uom_po_id': data.get('uom_po_id'),
                'pos_categ_ids': pos_categ_command,
                'categ_id': category.id,
                'taxes_id': tax_command,
                'available_in_pos': data.get('available_in_pos'),
                'create_uid': uid
            }

            item = env['product.template'].sudo().create(item_data)
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'Item created successfully',
                'id': item.id,
            }
        
        except Exception as e:
            _logger.error(f"Failed to create Item: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Item: {str(e)}"}

class POSTMasterPricelist(http.Controller):
    @http.route('/api/master_pricelist', type='json', auth='none', methods=['POST'], csrf=False)
    def post_pricelist(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = request.get_json_data()
            
            # Validate required fields
            required_fields = ['name', 'currency_id', 'pricelist_ids']
            missing_fields = [field for field in required_fields if not data.get(field)]
            if missing_fields:
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Missing required fields: {', '.join(missing_fields)}"
                }

            name = data.get('name')
            currency_id = data.get('currency_id')

            # Validate currency
            currency = env['res.currency'].sudo().browse(currency_id)
            if not currency.exists():
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Currency with ID {currency_id} not found."
                }

            # Check for duplicate pricelist
            existing_pricelist = env['product.pricelist'].sudo().search([('name', '=', name)], limit=1)
            if existing_pricelist:
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Pricelist with name '{name}' already exists.",
                    'id': existing_pricelist.id
                }

            # Validate all products first
            missing_products = []
            invalid_dates = []
            items_lines_data = []

            for line in data.get('pricelist_ids', []):
                product_code = line.get('product_code')
                if not product_code:
                    return {
                        'status': "Failed", 
                        'code': 400, 
                        'message': "Product code is required for all pricelist items."
                    }

                product = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product:
                    missing_products.append(product_code)
                    continue

                # Validate and parse dates
                date_start = line.get('date_start')
                date_end = line.get('date_end')
                
                try:
                    if date_start:
                        date_start = datetime.strptime(date_start.split('.')[0], '%Y-%m-%d %H:%M:%S')
                    if date_end:
                        date_end = datetime.strptime(date_end.split('.')[0], '%Y-%m-%d %H:%M:%S')
                        
                    if date_start and date_end and date_start > date_end:
                        invalid_dates.append(product_code)
                        continue
                except ValueError as e:
                    return {
                        'status': "Failed", 
                        'code': 400, 
                        'message': f"Invalid date format for product {product_code}: {str(e)}"
                    }

                # Validate pricing fields
                compute_price = line.get('compute_price')
                if compute_price == 'percentage' and not line.get('percent_price'):
                    return {
                        'status': "Failed", 
                        'code': 400, 
                        'message': f"Percent price is required for percentage computation for product {product_code}"
                    }
                elif compute_price == 'fixed' and not line.get('fixed_price'):
                    return {
                        'status': "Failed", 
                        'code': 400, 
                        'message': f"Fixed price is required for fixed computation for product {product_code}"
                    }

                items_lines_data.append({
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'applied_on': line.get('conditions'),
                    'compute_price': compute_price,
                    'percent_price': line.get('percent_price'),
                    'fixed_price': line.get('fixed_price'),
                    'min_quantity': line.get('quantity', 1),
                    'price': line.get('price'),
                    'date_start': date_start,
                    'date_end': date_end,
                })

            if missing_products:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Products with codes {', '.join(missing_products)} not found. Pricelist creation cancelled."
                }

            if invalid_dates:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Invalid date range for products: {', '.join(invalid_dates)}"
                }

            try:
                # Create pricelist
                pricelist_data = {
                    'name': name,
                    'currency_id': currency_id,
                    'create_uid': uid,
                    'item_ids': [(0, 0, line_data) for line_data in items_lines_data],
                }

                pricelist = env['product.pricelist'].sudo().create(pricelist_data)

            except Exception as create_error:
                _logger.error(f"Failed to create pricelist: {str(create_error)}", exc_info=True)
                return {
                    'status': "Failed", 
                    'code': 500, 
                    'message': f"Failed to create pricelist: {str(create_error)}"
                }

            return {
                'code': 200,
                'status': 'success',
                'message': 'Price List created successfully',
                'id': pricelist.id,
                'name': pricelist.name
            }

        except Exception as e:
            _logger.error(f"Failed to create Pricelist: {str(e)}", exc_info=True)
            return {
                'status': "Failed", 
                'code': 500, 
                'message': f"Failed to create Pricelist: {str(e)}"
            }

class POSTMasterCustomer(http.Controller):
    @http.route('/api/master_customer', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_customer(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = data = request.get_json_data()
            customer_code = data.get('customer_code')

            if env['res.partner'].sudo().search([('customer_code', '=', customer_code)], limit=1):
                return {'status': "Failed", 'code': 400, 'message': f"Duplicate Customer code: {customer_code}"}

            customer_data = {
                'name': data.get('name'),
                'customer_code': customer_code,
                'street': data.get('street'),
                'phone': data.get('phone'),
                'email': data.get('email'),
                'mobile': data.get('mobile'),
                'website': data.get('website'),
                'create_uid': uid
            }

            customer = env['res.partner'].sudo().create(customer_data)

            return {
                'code': 200,
                'status': 'success',
                'message': 'Customer created successfully',
                'id': customer.id,
            }
        except Exception as e:
            _logger.error(f"Failed to create Customer: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Customer: {str(e)}"}
    
class POSTMasterWarehouse(http.Controller):
    @http.route('/api/master_warehouse', type='json', auth='none', methods=['POST'], csrf=False)
    def post_master_warehouse(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = data = request.get_json_data()
            code = data.get('code')

            if env['stock.warehouse'].sudo().search([('code', '=', code)], limit=1):
                return {'status': "Failed", 'code': 400, 'message': f"Duplicate Warehouse code: {code}"}

            warehouse_data = {
                'name': data.get('name'),
                'code': code,
                'create_uid': uid
            }

            warehouse = env['stock.warehouse'].sudo().create(warehouse_data)
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'Warehouse created successfully',
                'id': warehouse.id,
            }
        except Exception as e:
            _logger.error(f"Failed to create Warehouse: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Warehouse: {str(e)}"}
    
class POSTItemCategory(http.Controller):
    @http.route('/api/item_category', type='json', auth='none', methods=['POST'], csrf=False)
    def post_item_group(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = data = request.get_json_data()
            category_name = data.get('category_name')

            if env['product.category'].sudo().search([('name', '=', category_name)], limit=1):
                return {'status': "Failed", 'code': 400, 'message': f"Duplicate category name: {category_name}."}

            category_data = {
                'name': category_name,
                'parent_id': data.get('parent_category_id'),
                'property_cost_method': data.get('costing_method'),
                'create_date': data.get('create_date'),
                'create_uid': uid
            }

            category = env['product.category'].sudo().create(category_data)
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'Item Category created successfully',
                'id': category.id,
            }
        
        except Exception as e:
            _logger.error(f"Failed to create Category: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Category: {str(e)}"}

class POSTItemPoSCategory(http.Controller):
    @http.route('/api/pos_category', type='json', auth='none', methods=['POST'], csrf=False)
    def post_pos_category(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = data = request.get_json_data()
            category_name = data.get('category_name')

            if env['pos.category'].sudo().search([('name', '=', category_name)], limit=1):
                return {'status': "Failed", 'code': 400, 'message': f"Duplicate PoS category name: {category_name}."}

            category_data = {
                'name': category_name,
                'create_date': data.get('create_date'),
                'create_uid': uid
            }

            category = env['pos.category'].sudo().create(category_data)
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'PoS Category created successfully',
                'id': category.id,
            }
        
        except Exception as e:
            _logger.error(f"Failed to create PoS Category: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create PoS Category: {str(e)}"}
        
class POSTGoodsReceipt(http.Controller):
    @http.route('/api/goods_receipt', type='json', auth='none', methods=['POST'], csrf=False)
    def post_goods_receipt(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = request.get_json_data()
            picking_type_name = data.get('picking_type')
            location_id = data.get('location_id')
            location_dest_id = data.get('location_dest_id')
            scheduled_date = data.get('scheduled_date')
            date_done = data.get('date_done')
            transaction_id = data.get('transaction_id')
            move_type = data.get('move_type')
            move_lines = data.get('move_lines', [])

            # Validate if Goods Receipt already exists
            existing_goods_receipts = env['stock.picking'].sudo().search([
                ('vit_trxid', '=', transaction_id), 
                ('picking_type_id.name', '=', 'Goods Receipts')
            ], limit=1)
            
            if existing_goods_receipts:   
                return {
                    'code': 400,
                    'status': 'failed',
                    'message': 'Goods Receipt already exists',
                    'id': existing_goods_receipts.id,
                    'doc_num': existing_goods_receipts.name
                }

            # Validate picking type
            picking_type = env['stock.picking.type'].sudo().search([('name', '=', picking_type_name)], limit=1)
            if not picking_type:
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Picking type '{picking_type_name}' not found."
                }

            # Validate locations
            source_location = env['stock.location'].sudo().browse(location_id)
            dest_location = env['stock.location'].sudo().browse(location_dest_id)
            
            if not source_location.exists():
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Source location with ID {location_id} not found."
                }
            
            if not dest_location.exists():
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Destination location with ID {location_dest_id} not found."
                }

            # Validate all products first before creating Goods Receipt
            missing_products = []
            for line in move_lines:
                product_code = line.get('product_code')
                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    missing_products.append(product_code)

            if missing_products:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Products with codes {', '.join(missing_products)} not found. Goods Receipt creation cancelled."
                }

            # Create Goods Receipt
            goods_receipt = env['stock.picking'].sudo().create({
                'picking_type_id': picking_type.id,
                'location_id': location_dest_id,
                'location_dest_id': location_id,
                'move_type': move_type,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'vit_trxid': transaction_id,
                'create_uid': uid,
                # 'immediate_transfer': True  # Added to ensure immediate transfer
            })

            # Create move lines
            move_line_vals = []
            for line in move_lines:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')
                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)

                move_vals = {
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_uom': product_id.uom_id.id,  # Added product UOM
                    'product_uom_qty': product_uom_qty,
                    'quantity': product_uom_qty,  # Added to ensure validation
                    'picking_id': goods_receipt.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'state': 'draft',
                }
                move_line_vals.append((0, 0, move_vals))

            # Update goods receipt with move lines
            goods_receipt.write({
                'move_ids_without_package': move_line_vals
            })

            try:
                # Validate the goods receipt
                goods_receipt.button_validate()
            except Exception as validate_error:
                # If validation fails, delete the goods receipt and return error
                goods_receipt.sudo().unlink()
                raise Exception(f"Failed to validate Goods Receipt: {str(validate_error)}")

            return {
                'code': 200,
                'status': 'success',
                'message': 'Goods Receipt created and validated successfully',
                'id': goods_receipt.id,
                'doc_num': goods_receipt.name
            }

        except Exception as e:
            _logger.error(f"Failed to create Goods Receipt: {str(e)}", exc_info=True)
            return {
                'status': "Failed", 
                'code': 500, 
                'message': f"Failed to create Goods Receipt: {str(e)}"
            }

class POSTGoodsIssue(http.Controller):
    @http.route('/api/goods_issue', type='json', auth='none', methods=['POST'], csrf=False)
    def post_goods_issue(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = request.get_json_data()
            picking_type_name = data.get('picking_type')
            location_id = data.get('location_id')
            location_dest_id = data.get('location_dest_id')
            scheduled_date = data.get('scheduled_date')
            date_done = data.get('date_done')
            transaction_id = data.get('transaction_id')
            move_type = data.get('move_type')
            move_lines = data.get('move_lines', [])

            # Validate if Goods Issue already exists
            existing_goods_issue = env['stock.picking'].sudo().search([
                ('vit_trxid', '=', transaction_id), 
                ('picking_type_id.name', '=', 'Goods Issue')
            ], limit=1)
            
            if existing_goods_issue:    
                return {
                    'code': 400,
                    'status': 'failed',
                    'message': 'Goods Issue already exists',
                    'id': existing_goods_issue.id,
                    'doc_num': existing_goods_issue.name
                }         

            # Validate picking type
            picking_type = env['stock.picking.type'].sudo().search([('name', '=', picking_type_name)], limit=1)
            if not picking_type:
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Picking type '{picking_type_name}' not found."
                }

            # Validate locations
            source_location = env['stock.location'].sudo().browse(location_id)
            dest_location = env['stock.location'].sudo().browse(location_dest_id)
            
            if not source_location.exists():
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Source location with ID {location_id} not found."
                }
            
            if not dest_location.exists():
                return {
                    'status': "Failed", 
                    'code': 400, 
                    'message': f"Destination location with ID {location_dest_id} not found."
                }

            # Validate all products first before creating Goods Issue
            missing_products = []
            for line in move_lines:
                product_code = line.get('product_code')
                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    missing_products.append(product_code)

            if missing_products:
                return {
                    'status': "Failed",
                    'code': 400,
                    'message': f"Products with codes {', '.join(missing_products)} not found. Goods Issue creation cancelled."
                }

            # Create Goods Issue
            goods_issue = env['stock.picking'].sudo().create({
                'picking_type_id': picking_type.id,
                'location_id': location_id,
                'location_dest_id': location_dest_id,
                'move_type': move_type,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'vit_trxid': transaction_id,
                'create_uid': uid,
                # 'immediate_transfer': True  # Added to ensure immediate transfer
            })

            # Create move lines
            move_line_vals = []
            for line in move_lines:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')
                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)

                move_vals = {
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_uom': product_id.uom_id.id,  # Added product UOM
                    'product_uom_qty': product_uom_qty,
                    'quantity': product_uom_qty,  # Added to ensure validation
                    'picking_id': goods_issue.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                    'state': 'draft',
                }
                move_line_vals.append((0, 0, move_vals))

            # Update goods issue with move lines
            goods_issue.write({
                'move_ids_without_package': move_line_vals
            })

            try:
                # Validate the goods issue
                goods_issue.button_validate()
            except Exception as validate_error:
                # If validation fails, delete the goods issue and return error
                goods_issue.sudo().unlink()
                raise Exception(f"Failed to validate Goods Issue: {str(validate_error)}")

            return {
                'code': 200,
                'status': 'success',
                'message': 'Goods Issue created and validated successfully',
                'id': goods_issue.id,
                'doc_num': goods_issue.name
            }
            
        except Exception as e:
            _logger.error(f"Failed to create Goods Issue: {str(e)}", exc_info=True)
            return {
                'status': "Failed", 
                'code': 500, 
                'message': f"Failed to create Goods Issue: {str(e)}"
            }
        
class POSTPurchaseOrderFromSAP(http.Controller):
    @http.route('/api/purchase_order', type='json', auth='none', methods=['POST'], csrf=False)
    def post_purchase_order(self, **kw):
        try:
            # Authentication
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {'status': "Failed", 'code': 500, 'message': "Configuration not found."}
            
            uid = request.session.authenticate(request.session.db, config.vit_config_username, config.vit_config_password_api)
            if not uid:
                return {'status': "Failed", 'code': 401, 'message': "Authentication failed."}

            env = request.env(user=request.env.ref('base.user_admin').id)
            
            data = request.get_json_data()
            customer_code = data.get('customer_code')
            vendor_reference = data.get('vendor_reference')
            currency_id = data.get('currency_id')
            date_order = data.get('date_order')
            transaction_id = data.get('transaction_id')
            expected_arrival = data.get('expected_arrival')
            picking_type_name = data.get('picking_type')
            location_id = data.get('location_id')
            order_line = data.get('order_line', [])

            # Check if PO already exists
            existing_po = env['purchase.order'].sudo().search([
                ('vit_trxid', '=', transaction_id), 
                ('picking_type_id.name', '=', picking_type_name),
                ('picking_type_id.default_location_dest_id', '=', location_id)
            ], limit=1)
            
            if existing_po:
                return {
                    'code': 500,
                    'status': 'failed',
                    'message': 'Purchase Order already exists',
                    'id': existing_po.id,
                }

            # Validate customer
            customer_id = env['res.partner'].sudo().search([('customer_code', '=', customer_code)], limit=1).id 
            if not customer_id:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Customer with code '{customer_code}' not found.",
                }

            # Validate picking type
            picking_types = env['stock.picking.type'].sudo().search([
                ('name', '=', picking_type_name), 
                ('default_location_dest_id', '=', location_id)
            ], limit=1)

            if not picking_types:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Picking type with name '{picking_type_name}' and location_id '{location_id}' not found.",
                }

            # Validate all products first before creating PO
            missing_products = []
            for line in order_line:
                product_code = line.get('product_code')
                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    missing_products.append(product_code)

            if missing_products:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Products with codes {', '.join(missing_products)} not found. Purchase Order creation cancelled.",
                }

            # Create purchase order lines
            purchase_order_lines = []
            for line in order_line:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')
                price_unit = line.get('price_unit')
                taxes_ids = line.get('taxes_ids')

                # Validate tax
                tax_name = env['account.tax'].sudo().search([('name', '=', taxes_ids)], limit=1)
                if not tax_name:
                    return {
                        'status': "Failed",
                        'code': 500,
                        'message': f"Failed to create PO. Tax not found: {taxes_ids}.",
                    }

                taxes_ids = [tax_name.id]

                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                purchase_order_line = {
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_qty': product_uom_qty,
                    'price_unit': price_unit,
                    'taxes_id': [(6, 0, taxes_ids)],
                    'product_uom': product_id.uom_id.id,  # Added product UOM
                }
                purchase_order_lines.append((0, 0, purchase_order_line))

            # Create purchase order
            purchase_order = env['purchase.order'].sudo().create({
                'partner_id': customer_id,
                'partner_ref': vendor_reference,
                'currency_id': currency_id,
                'date_order': date_order,
                'date_planned': expected_arrival,
                'vit_trxid': transaction_id,
                'picking_type_id': picking_types.id,
                'create_uid': uid,
                'user_id': uid,
                'order_line': purchase_order_lines,
            })

            # Confirm purchase order
            purchase_order.button_confirm()
            
            # Update related pickings
            picking_ids = env['stock.picking'].sudo().search([('purchase_id', '=', purchase_order.id)])
            
            if picking_ids:
                for picking in picking_ids:
                    for move in picking.move_ids_without_package:
                        move.product_uom_qty = move.quantity
                    picking.write({
                        'origin': purchase_order.name,
                        'vit_trxid': transaction_id
                    })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Purchase created and validated successfully',
                'id': purchase_order.id,
                'doc_num': purchase_order.name
            }

        except Exception as e:
            _logger.error(f"Failed to create Purchase Order: {str(e)}", exc_info=True)
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Purchase Order: {str(e)}",
            }