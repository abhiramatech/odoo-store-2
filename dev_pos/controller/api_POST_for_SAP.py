from odoo import http
from odoo.http import request
import requests
from datetime import datetime
import json
import logging
import base64

_logger = logging.getLogger(__name__)

class POSTMasterItem(http.Controller):
    @http.route('/api/master_item', type='json', auth='public', methods=['POST'], csrf=False)
    def post_master_item(self, **kw):
        try:
            data = request.httprequest.get_json()
            product_name = data.get('product_name')
            product_code = data.get('product_code')
            product_type = data.get('product_type')
            invoicing_policy = data.get('invoice_policy')
            create_date = data.get('create_date')
            sales_price = data.get('sales_price')
            cost = data.get('cost')
            uom_id = data.get('uom_id')
            uom_po_id = data.get('uom_po_id')
            active = data.get('active')
            category_name = data.get('category_name')
            pos_categ_id = data.get('pos_categ_id')
            taxes_id = data.get('taxes_name')
            available_in_pos = data.get('available_in_pos')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            existing_items = request.env['product.template'].sudo().search([('default_code', '=', product_code)], limit=1)
            if existing_items:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Item. Duplicate item code: {product_code}.",
                }
            
            name_categ = request.env['product.category'].sudo().search([('complete_name', '=', category_name)], limit=1)
            if not name_categ:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Item. Category not found: {category_name}.",
                }
            
            tax_name = request.env['account.tax'].sudo().search([('name', '=', taxes_id)], limit=1)
            if not tax_name:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Item. Tax not found: {tax_name}.",
                }

            items = request.env['product.template'].sudo().create({
                'name': product_name,
                'active': active,
                'default_code': product_code,
                'detailed_type': product_type,
                'invoice_policy': invoicing_policy,
                'create_date': create_date,
                'list_price': sales_price,
                'standard_price': cost,
                'uom_id': uom_id,
                'uom_po_id': uom_po_id,
                'pos_categ_ids': [(6, 0, [pos_categ_id])],
                'categ_id': name_categ.id,
                'taxes_id': [(6, 0, [tax_name.id])],
                'available_in_pos': available_in_pos,
                'create_uid': admin_user.id,
            })
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'Item created successfully',
                'id': items.id,
            }
        
        except Exception as e:
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Item. Error: {str(e)}",
            }

class POSTMasterPricelist(http.Controller):
    @http.route('/api/master_pricelist', type='json', auth='public', methods=['POST'], csrf=False)
    def post_pricelist(self, **kw):
        try:
            data = request.httprequest.get_json()
            name = data.get('name')
            currency_id = data.get('currency_id')
            items_lines = data.get('pricelist_ids', [])
            user_name = data.get('user_name')
            items_lines_data = []

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            # Check for duplicate pricelist name
            existing_pricelist = request.env['product.pricelist'].sudo().search([('name', '=', name)], limit=1)
            if existing_pricelist:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Pricelist. Duplicate pricelist: {name}.",
                }
                
            for line in items_lines:
                product_code = line.get('product_code')
                product_uom_qty = line.get('quantity')
                conditions = line.get('conditions')
                compute_price = line.get('compute_price')
                percent_price = line.get('percent_price')
                fixed_price = line.get('fixed_price')
                price = line.get('price')
                date_start = line.get('date_start')
                date_end = line.get('date_end')

                if date_start and date_end:
                    # Convert datetime strings to the correct format
                    date_start = datetime.strptime(date_start.split('.')[0], '%Y-%m-%d %H:%M:%S')
                    date_end = datetime.strptime(date_end.split('.')[0], '%Y-%m-%d %H:%M:%S')

                # Search for the product by default_code
                product = request.env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)

                if product:
                    # Create order line data with the correct format
                    order_line_data = {
                        'product_tmpl_id': product.product_tmpl_id.id,
                        'applied_on': conditions,
                        'compute_price': compute_price,
                        'percent_price': percent_price,
                        'fixed_price': fixed_price,
                        'min_quantity': product_uom_qty,
                        'price': price,
                        'date_start': date_start,
                        'date_end': date_end,
                        'create_uid': admin_user.id,
                    }
                    items_lines_data.append(order_line_data)

            # Create the pricelist with the prepared item lines
            price_list = request.env['product.pricelist'].sudo().create({
                'name': name,
                'currency_id': currency_id,
                'item_ids': [(0, 0, line_data) for line_data in items_lines_data],
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Price List created successfully',
                'id': price_list.id,
            }

        except Exception as e:
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Pricelist. Error: {str(e)}",
            }

class POSTMasterCustomer(http.Controller):
    @http.route('/api/master_customer', type='json', auth='public', methods=['POST'], csrf=False)
    def post_master_customer(self, **kw):
        try:
            data = request.httprequest.get_json()
            name = data.get('name')
            customer_code = data.get('customer_code')
            street = data.get('street')
            phone = data.get('phone')
            email = data.get('email')
            mobile = data.get('mobile')
            website = data.get('website')  
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                } 

            existing_partners = request.env['res.partner'].sudo().search([('customer_code', '=', customer_code)], limit=1)
            if existing_partners:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Customer. Duplicate Customer code: {customer_code}",
                }

            customers = request.env['res.partner'].sudo().create({
                'name': name,
                'customer_code': customer_code,
                'street': street,
                'phone': phone,
                'email': email,
                'mobile': mobile,
                'website': website,
                'create_uid': admin_user.id,
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Customer created successfully',
                'id': customers.id,
            }
        except Exception as e:
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Customer. Error: {str(e)}",
            }
    
class POSTMasterWarehouse(http.Controller):
    @http.route('/api/master_warehouse', type='json', auth='public', methods=['POST'], csrf=False)
    def post_master_warehouse(self, **kw):
        try:
            data = request.httprequest.get_json()
            name = data.get('name')
            location_id = data.get('location_id')
            location_type = data.get('location_type')
            scrap_location = data.get('scrap_location')
            return_location = data.get('return_location')
            replenish_location = data.get('replenish_location')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            locations = request.env['stock.location'].sudo().create({
                'name': name,
                'location_id': location_id,
                'usage': location_type,
                'scrap_location': scrap_location,
                'return_location': return_location,
                'replenish_location': replenish_location,
                'create_uid': admin_user.id,
            })
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'Location created successfully',
                'id': locations.id,
            }
        except Exception as e:
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Warehouse. Error: {str(e)}",
            }
    
class POSTItemCategory(http.Controller):
    @http.route('/api/item_category', type='json', auth='public', methods=['POST'], csrf=False)
    def post_item_group(self, **kw):
        try:
            data = request.httprequest.get_json()
            category_name = data.get('category_name')
            parent_category_id = data.get('parent_category_id')
            costing_method = data.get('costing_method')
            create_data = data.get('create_date')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            existing_category = request.env['product.category'].sudo().search([('name', '=', category_name)], limit=1)
            if existing_category:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Category. Duplicate category code: {category_name}.",
                }

            category = request.env['product.category'].sudo().create({
                'name': category_name,
                'parent_id': parent_category_id,
                'property_cost_method': costing_method,
                'create_date': create_data,
                'created_uid': admin_user.id,
            })
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'Item Category created successfully',
                'id': category.id,
            }
        
        except Exception as e:
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Category. Error: {str(e)}",
            }

class POSTItemPoSCategory(http.Controller):
    @http.route('/api/pos_category', type='json', auth='public', methods=['POST'], csrf=False)
    def post_pos_category(self, **kw):
        try:
            data = request.httprequest.get_json()
            category_name = data.get('category_name')
            create_date = data.get('create_date')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            existing_category = request.env['pos.category'].sudo().search([('name', '=', category_name)], limit=1)
            if existing_category:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create PoS Category. Duplicate category code: {category_name}.",
                }

            category = request.env['pos.category'].sudo().create({
                'name': category_name,
                'create_date': create_date,
                'create_uid': admin_user.id,
            })
            
            return {
                'code': 200,
                'status': 'success',
                'message': 'PoS Category created successfully',
                'id': category.id,
            }
        
        except Exception as e:
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Category. Error: {str(e)}",
            }
        
class POSTGoodsReceipt(http.Controller):
    @http.route('/api/goods_receipt', type='json', auth='public', methods=['POST'], csrf=False)
    def post_goods_receipt(self, **kw):
        try:
            data = request.httprequest.get_json()
            picking_type_name = data.get('picking_type')
            user_name = data.get('user_name')
            location_id = data.get('location_id')
            location_dest_id = data.get('location_dest_id')
            scheduled_date = data.get('scheduled_date')
            date_done = data.get('date_done')
            transaction_id = data.get('transaction_id')
            move_type = data.get('move_type')
            move_lines = data.get('move_lines', [])
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            existing_goods_receipts = request.env['stock.picking'].sudo().search([('vit_trxid', '=', transaction_id), ('picking_type_id.name', '=', 'Goods Receipts')], limit=1)
            if existing_goods_receipts:   
                return {
                    'code': 500,
                    'status': 'failed',
                    'message': 'Goods Receipts already exists',
                    'id': existing_goods_receipts.id,
                }
            picking_type = request.env['stock.picking.type'].sudo().search([('name', '=', picking_type_name)], limit=1)
            if not picking_type:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Goods Receipt. Invalid picking type: {picking_type_name}.",
                }
            
            user_ids = request.env['res.users'].sudo().search([('name', '=', user_name), ('active', '=', True)], limit=1)
            if not user_ids:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Goods Receipts. Invalid user name: {user_name}.",
                }

            goods_receipt = request.env['stock.picking'].sudo().create({
                'picking_type_id': picking_type.id,
                'location_id': location_dest_id,
                'location_dest_id': location_id,
                'move_type': move_type,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'create_uid': admin_user.id,
                'vit_trxid': transaction_id,
            })

            for line in move_lines:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')

                product_id = request.env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    return {
                        'status': "Failed",
                        'code': 500,
                        'message': f"Failed to create Goods Receipt. Invalid product code: {product_code}.",
                    }

                request.env['stock.move'].sudo().create({
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
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Goods Receipt. Error: {str(e)}",
            }

class POSTGoodsIssue(http.Controller):
    @http.route('/api/goods_issue', type='json', auth='public', methods=['POST'], csrf=False)
    def post_goods_issue(self, **kw):
        try:
            data = request.httprequest.get_json()
            picking_type_name = data.get('picking_type')
            user_name = data.get('user_name')
            location_id = data.get('location_id')
            location_dest_id = data.get('location_dest_id')
            scheduled_date = data.get('scheduled_date')
            date_done = data.get('date_done')
            transaction_id = data.get('transaction_id')
            move_type = data.get('move_type')
            move_lines = data.get('move_lines', [])
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            existing_goods_issue = request.env['stock.picking'].sudo().search([('vit_trxid', '=', transaction_id), ('picking_type_id.name', '=', 'Goods Issue')], limit=1)
            if existing_goods_issue:    
                return {
                    'code': 500,
                    'status': 'failed',
                    'message': 'Goods Issue already exists',
                    'id': existing_goods_issue.id,
                }         
            picking_type = request.env['stock.picking.type'].sudo().search([('name', '=', picking_type_name)], limit=1)
            if not picking_type:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Goods Issue. Invalid picking type: {picking_type_name}.",
                }

            user_ids = request.env['res.users'].sudo().search([('name', '=', user_name), ('active', '=', True)], limit=1)
            if not user_ids:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Goods Issue. Invalid user name: {user_name}.",
                }

            goods_issue = request.env['stock.picking'].sudo().create({
                'picking_type_id': picking_type.id,
                'location_id': location_id,
                'location_dest_id': location_dest_id,
                'move_type': move_type,
                'scheduled_date': scheduled_date,
                'date_done': date_done,
                'create_uid': admin_user.id,
                'vit_trxid': transaction_id,
            })

            for line in move_lines:
                product_code = line.get('product_code')
                product_uom_qty = line.get('product_uom_qty')

                product_id = request.env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product_id:
                    return {
                        'status': "Failed",
                        'code': 500,
                        'message': f"Failed to create Goods Issue. Invalid product code: {product_code}.",
                    }

                request.env['stock.move'].sudo().create({
                    'name': product_id.name,
                    'product_id': product_id.id,
                    'product_uom_qty': product_uom_qty,
                    'picking_id': goods_issue.id,
                    'location_id': location_dest_id,
                    'location_dest_id': location_id,
                    'create_uid': user_ids,
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
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Goods Issue. Error: {str(e)}",
            }
        
class POSTPurchaseOrderFromSAP(http.Controller):
    @http.route('/api/login', type='json', auth='none', methods=['POST'], csrf=False)
    def login(self, **kw):
        try:
            data = request.httprequest.get_json()
            login = data.get('login')
            password = data.get('password')
            db = data.get('db')

            # Perform login
            request.session.authenticate(db, login, password)
            return {
                'status': "Success",
                'code': 200,
                'message': "Login successful",
                'session_id': request.session.sid,
            }
        except Exception as e:
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Login failed. Error: {str(e)}",
            }

    @http.route('/api/purchase_order', type='json', auth='user', methods=['POST'], csrf=False)
    def post_purchase_order(self, **kw):
        try:
            data = request.httprequest.get_json()
            customer_code = data.get('customer_code')
            vendor_reference = data.get('vendor_reference')
            currency_id = data.get('currency_id')
            date_order = data.get('date_order')
            transaction_id = data.get('transaction_id')
            expected_arrival = data.get('expected_arrival')
            picking_type_name = data.get('picking_type')
            location_id = data.get('location_id')
            user_name = data.get('user_name')
            order_line = data.get('order_line', [])

            # Retrieve the Administrator user ID
            admin_user = request.env['res.users'].sudo().search([('name', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            # Debugging: Check the type of location_id
            if not isinstance(location_id, int):
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Invalid format for location_id. Expected an integer.",
                }

            # Ensure order_line is a list of dictionaries
            if not isinstance(order_line, list) or not all(isinstance(item, dict) for item in order_line):
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Invalid format for order_line. Expected a list of dictionaries.",
                }

            # Mencari Purchase Order yang ada
            existing_po = request.env['purchase.order'].sudo().search([
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

            # Mencari Partner
            customer_id = request.env['res.partner'].sudo().search([
                ('customer_code', '=', customer_code)
            ], limit=1).id 
            
            picking_types = request.env['stock.picking.type'].sudo().search([
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

                # Search for tax based on name
                tax_name = request.env['account.tax'].sudo().search([('name', '=', taxes_ids)], limit=1)
                if not tax_name:
                    return {
                        'status': "Failed",
                        'code': 500,
                        'message': f"Failed to create PO. Tax not found: {taxes_ids}.",
                    }

                # Ensure taxes_ids is a list of integers (converted from tax_name ID)
                taxes_ids = [tax_name.id]

                product_id = request.env['product.product'].sudo().search([('default_code', '=', product_code)], limit=1)
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
                    'taxes_id': [(6, 0, taxes_ids)],  # Corrected to use tax IDs
                }
                purchase_order_lines.append((0, 0, purchase_order_line))

            # Membuat Purchase Order
            purchase_order = request.env['purchase.order'].sudo().create({
                'partner_id': customer_id,
                'partner_ref': vendor_reference,
                'currency_id': currency_id,
                'date_order': date_order,
                'date_planned': expected_arrival,
                'vit_trxid': transaction_id,
                'picking_type_id': picking_types.id,
                'create_uid': admin_user.id,  # Set to Administrator
                'user_id': admin_user.id,    # Set to Administrator
                'order_line': purchase_order_lines,
            })

            # Mengkonfirmasi Purchase Order
            purchase_order.button_confirm()
            
            # Mengambil Picking yang terkait dengan Purchase Order
            picking_ids = request.env['stock.picking'].sudo().search([
                ('purchase_id', '=', purchase_order.id)
            ])
            
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
            import traceback
            error_message = traceback.format_exc()
            return {
                'status': "Failed",
                'code': 500,
                'message': f"Failed to create Purchase Order. Error: {str(e)}",
                'details': error_message,
            }
