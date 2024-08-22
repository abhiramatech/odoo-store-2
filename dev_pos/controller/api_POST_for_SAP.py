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
            
            data = data = request.get_json_data()
            name = data.get('name')

            if env['product.pricelist'].sudo().search([('name', '=', name)], limit=1):
                return {'status': "Failed", 'code': 400, 'message': f"Duplicate pricelist: {name}."}
                
            items_lines_data = []
            for line in data.get('pricelist_ids', []):
                product = env['product.product'].sudo().search([('default_code', '=', line.get('product_code'))], limit=1)
                if not product:
                    return {'status': "Failed", 'code': 400, 'message': f"Product with code {line.get('product_code')} not found."}

                date_start = line.get('date_start')
                date_end = line.get('date_end')
                if date_start and date_end:
                    date_start = datetime.strptime(date_start.split('.')[0], '%Y-%m-%d %H:%M:%S')
                    date_end = datetime.strptime(date_end.split('.')[0], '%Y-%m-%d %H:%M:%S')

                items_lines_data.append({
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'applied_on': line.get('conditions'),
                    'compute_price': line.get('compute_price'),
                    'percent_price': line.get('percent_price'),
                    'fixed_price': line.get('fixed_price'),
                    'min_quantity': line.get('quantity'),
                    'price': line.get('price'),
                    'date_start': date_start,
                    'date_end': date_end,
                })

            pricelist_data = {
                'name': name,
                'currency_id': data.get('currency_id'),
                'create_uid': uid,
                'item_ids': [(0, 0, line_data) for line_data in items_lines_data],
            }

            pricelist = env['product.pricelist'].sudo().create(pricelist_data)

            return {
                'code': 200,
                'status': 'success',
                'message': 'Price List created successfully',
                'id': pricelist.id,
            }

        except Exception as e:
            _logger.error(f"Failed to create Pricelist: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Pricelist: {str(e)}"}

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
            
            data = data = request.get_json_data()
            picking_type_name = data.get('picking_type')
            location_id = data.get('location_id')
            location_dest_id = data.get('location_dest_id')
            scheduled_date = data.get('scheduled_date')
            date_done = data.get('date_done')
            transaction_id = data.get('transaction_id')
            move_type = data.get('move_type')
            move_lines = data.get('move_lines', [])

            existing_goods_receipts = env['stock.picking'].sudo().search([('vit_trxid', '=', transaction_id), ('picking_type_id.name', '=', 'Goods Receipts')], limit=1)
            if existing_goods_receipts:   
                return {
                    'code': 400,
                    'status': 'failed',
                    'message': 'Goods Receipts already exists',
                    'id': existing_goods_receipts.id,
                }

            picking_type = env['stock.picking.type'].sudo().search([('name', '=', picking_type_name)], limit=1)
            if not picking_type:
                return {'status': "Failed", 'code': 400, 'message': f"Invalid picking type: {picking_type_name}."}

            goods_receipt = env['stock.picking'].sudo().create({
                'picking_type_id': picking_type.id,
                'location_id': location_dest_id,
                'location_dest_id': location_id,
                'move_type': move_type,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'vit_trxid': transaction_id,
                'create_uid': uid
            })

            for line in move_lines:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')

                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    return {'status': "Failed", 'code': 400, 'message': f"Invalid product code: {product_code}."}

                env['stock.move'].sudo().create({
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_uom_qty': product_uom_qty,
                    'picking_id': goods_receipt.id,
                    'location_id': location_id,
                    'location_dest_id': location_dest_id,
                })
            
            goods_receipt.button_validate()

            return {
                'code': 200,
                'status': 'success',
                'message': 'Goods Receipt created successfully',
                'id': goods_receipt.id,
                'doc_num': goods_receipt.name
            }

        except Exception as e:
            _logger.error(f"Failed to create Goods Receipt: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Goods Receipt: {str(e)}"}

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
            
            data = data = request.get_json_data()
            picking_type_name = data.get('picking_type')
            location_id = data.get('location_id')
            location_dest_id = data.get('location_dest_id')
            scheduled_date = data.get('scheduled_date')
            date_done = data.get('date_done')
            transaction_id = data.get('transaction_id')
            move_type = data.get('move_type')
            move_lines = data.get('move_lines', [])

            existing_goods_issue = env['stock.picking'].sudo().search([('vit_trxid', '=', transaction_id), ('picking_type_id.name', '=', 'Goods Issue')], limit=1)
            if existing_goods_issue:    
                return {
                    'code': 400,
                    'status': 'failed',
                    'message': 'Goods Issue already exists',
                    'id': existing_goods_issue.id,
                }         

            picking_type = env['stock.picking.type'].sudo().search([('name', '=', picking_type_name)], limit=1)
            if not picking_type:
                return {'status': "Failed", 'code': 400, 'message': f"Invalid picking type: {picking_type_name}."}

            goods_issue = env['stock.picking'].sudo().create({
                'picking_type_id': picking_type.id,
                'location_id': location_id,
                'location_dest_id': location_dest_id,
                'move_type': move_type,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'vit_trxid': transaction_id,
                'create_uid': uid
            })

            for line in move_lines:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')

                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    return {'status': "Failed", 'code': 400, 'message': f"Invalid product code: {product_code}."}

                env['stock.move'].sudo().create({
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_uom_qty': product_uom_qty,
                    'picking_id': goods_issue.id,
                    'location_id': location_dest_id,
                    'location_dest_id': location_id,
                })
            
            goods_issue.button_validate()

            return {
                'code': 200,
                'status': 'success',
                'message': 'Goods Issue created successfully',
                'id': goods_issue.id,
                'doc_num': goods_issue.name
            }
            
        except Exception as e:
            _logger.error(f"Failed to create Goods Issue: {str(e)}")
            return {'status': "Failed", 'code': 500, 'message': f"Failed to create Goods Issue: {str(e)}"}
        
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
            
            data = data = request.get_json_data()
            customer_code = data.get('customer_code')
            vendor_reference = data.get('vendor_reference')
            currency_id = data.get('currency_id')
            date_order = data.get('date_order')
            transaction_id = data.get('transaction_id')
            expected_arrival = data.get('expected_arrival')
            picking_type_name = data.get('picking_type')
            location_id = data.get('location_id')
            order_line = data.get('order_line', [])

            existing_po = env['purchase.order'].sudo().search([
                ('vit_trxid', '=', transaction_id), 
                ('picking_type_id.name', '=', picking_type_name)
            ], limit=1)
            
            if existing_po:
                return {
                    'code': 500,
                    'status': 'failed',
                    'message': 'Purchase Order already exists',
                    'id': existing_po.id,
                }

            customer_id = env['res.partner'].sudo().search([('customer_code', '=', customer_code)], limit=1).id 
            
            picking_types = env['stock.picking.type'].sudo().search([
                ('name', '=', picking_type_name), ('default_location_dest_id', '=', location_id)
            ], limit=1)

            if not picking_types:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Picking type with name '{picking_type_name}' and location_id '{location_id}' not found.",
                }

            purchase_order_lines = []
            for line in order_line:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')
                price_unit = line.get('price_unit')
                taxes_ids = line.get('taxes_ids')

                tax_name = env['account.tax'].sudo().search([('name', '=', taxes_ids)], limit=1)
                if not tax_name:
                    return {
                        'status': "Failed",
                        'code': 500,
                        'message': f"Failed to create PO. Tax not found: {taxes_ids}.",
                    }

                taxes_ids = [tax_name.id]

                product_id = env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    return {
                        'status': "Failed",
                        'code': 500,
                        'message': f"Product with code '{product_code}' not found.",
                    }

                purchase_order_line = {
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_qty': product_uom_qty,
                    'price_unit': price_unit,
                    'taxes_id': [(6, 0, taxes_ids)],
                }
                purchase_order_lines.append((0, 0, purchase_order_line))

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

            purchase_order.button_confirm()
            
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
