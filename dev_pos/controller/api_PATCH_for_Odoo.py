from odoo import http
from odoo.http import request
import json
from odoo.exceptions import AccessError
from .api_utils import check_authorization, paginate_records, serialize_response, serialize_error_response
import logging
_logger = logging.getLogger(__name__)

class MasterCustomerPATCH(http.Controller):
    @http.route(['/api/master_customer/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_customer(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            # Parse the incoming data
            data = request.get_json_data()
            name = data.get('name')
            street = data.get('street')
            email = data.get('email')
            mobile = data.get('mobile')
            website = data.get('website')
            customer_code = data.get('customer_code')
            is_integrated = data.get('is_integrated')

            # Find and update the customer
            master_customer = env['res.partner'].sudo().browse(return_id)
            if not master_customer.exists():
                return {
                    'code': 404, 
                    'status': 'error', 
                    'message': 'Master Customer not found', 
                    'id': return_id
                }

            update_data = {
                'name': name,
                'street': street,
                'email': email,
                'mobile': mobile,
                'website': website,
                'customer_code': customer_code,
                'is_integrated': is_integrated,
                'write_uid': uid
            }

            master_customer.write(update_data)

            return {
                'code': 200, 
                'status': 'success', 
                'message': 'Master Customer updated successfully', 
                'id': return_id
            }

        except AccessError as ae:
            _logger.error(f"Access Error: {str(ae)}")
            return {
                'code': 403,
                'status': 'error',
                'message': f"Access Denied: {str(ae)}",
                'id': return_id
            }
        except Exception as e:
            _logger.error(f"Error updating master customer: {str(e)}")
            return {
                'code': 500, 
                'status': 'error', 
                'message': str(e), 
                'id': return_id
            }
        
class MasterItemPATCH(http.Controller):
    @http.route(['/api/master_item/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_item(self, return_id, **kwargs):
        try:
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            # Parse the incoming data
            data = request.get_json_data()
            product_name = data.get('product_name')
            product_code = data.get('product_code')
            sales_price = data.get('sales_price')
            is_integrated = data.get('is_integrated')
            product_type = data.get('product_type')
            invoicing_policy = data.get('invoice_policy')
            cost = data.get('cost')
            active = data.get('active')
            uom_id = data.get('uom_id')
            uom_po_id = data.get('uom_po_id')
            pos_categ_ids = data.get('pos_categ_ids', [])
            category_name = data.get('category_name')
            taxes_names = data.get('taxes_names', [])
            available_in_pos = data.get('available_in_pos')
            
            # Retrieve the master item from the database
            master_item = env['product.template'].sudo().search([('id', '=', int(return_id))], limit=1)
            if not master_item:
                return {
                    'status': "Failed",
                    'code': 404,
                    'message': f"Master Item with ID {return_id} not found.",
                }

            name_categ = env['product.category'].sudo().search([('complete_name', '=', category_name)], limit=1)
            if not name_categ:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to update Item. Category not found: {category_name}.",
                }
            
            # Find all taxes based on the provided names
            tax_command = []
            for tax_name in data.get('taxes_names', []):
                tax = env['account.tax'].sudo().search([('name', '=', tax_name)], limit=1)
                if tax:
                    tax_command.append((4, tax.id))
                else:
                    return {'status': "Failed", 'code': 400, 'message': f"Tax with name '{tax_name}' not found."}

            # Prepare the update data
            update_data = {
                'name': product_name,
                'default_code': product_code,
                'list_price': sales_price,
                'is_integrated': is_integrated,
                'detailed_type': product_type,
                'invoice_policy': invoicing_policy,
                'standard_price': cost,
                'uom_id': uom_id,
                'uom_po_id': uom_po_id,
                'categ_id': name_categ.id,
                'pos_categ_ids': [(6, 0, pos_categ_ids)],
                'taxes_id': tax_command,
                'available_in_pos': available_in_pos,
                'write_uid': uid,
            }

            # Only update 'active' if it's provided in the data
            if active is not None:
                update_data['active'] = active

            # Update the master item
            master_item.sudo().write(update_data)

            # Return success response
            return {
                'code': 200, 
                'status': 'success', 
                'message': 'Master Item updated successfully', 
                'id': master_item.id
            }

        except AccessError as ae:
            _logger.error(f"Access Error: {str(ae)}")
            return {
                'code': 403,
                'status': 'error',
                'message': f"Access Denied: {str(ae)}",
                'id': return_id
            }
        except Exception as e:
            _logger.error(f"Error updating master item: {str(e)}")
            return {
                'code': 500, 
                'status': 'error', 
                'message': str(e), 
                'id': return_id
            }

class MasterPricelistPATCH(http.Controller):
    @http.route(['/api/master_pricelist/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_pricelist(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            name = data.get('name')
            currency_id = data.get('currency_id')
            pricelist_ids = data.get('pricelist_ids')

            master_pricelist = env['product.pricelist'].sudo().browse(int(return_id))
            if not master_pricelist.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Master Pricelist not found',
                    'id': return_id
                }

            # Update name and currency_id
            master_pricelist.write({
                'name': name,
                'currency_id': currency_id,
                'write_uid': uid
            })

            # Update pricelist_ids
            for item in pricelist_ids:
                product_code = item['product_code']
                product = env['product.template'].sudo().search([('default_code', '=', product_code)], limit=1)
                if not product:
                    return {
                        'code': 404,
                        'status': 'error',
                        'message': f"Product with code {product_code} not found",
                        'id': return_id
                    }

                pricelist_item = env['product.pricelist.item'].sudo().search([
                    ('product_tmpl_id', '=', product.id),
                    ('pricelist_id', '=', return_id)
                ], limit=1)

                item_data = {
                    'min_quantity': item['quantity'],
                    'fixed_price': item['price'],
                    'date_start': item['date_start'],
                    'date_end': item['date_end'],
                    'write_uid': uid
                }

                if pricelist_item:
                    pricelist_item.write(item_data)
                else:
                    item_data.update({
                        'pricelist_id': return_id,
                        'product_tmpl_id': product.id,
                    })
                    env['product.pricelist.item'].sudo().create(item_data)

            return {
                'code': 200,
                'status': 'success',
                'message': 'Master Pricelist updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating master pricelist: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }

class MasterCategoryPATCH(http.Controller):
    @http.route(['/api/item_category/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_category_item(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            
            category_name = data.get('category_name')
            parent_category_id = data.get('parent_category_id')
            costing_method = data.get('costing_method')
            create_date = data.get('create_date')

            master_category = env['product.category'].sudo().browse(int(return_id))
            if not master_category.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Master Category not found',
                    'id': return_id
                }

            # Update category
            master_category.write({
                'name': category_name,
                'parent_id': parent_category_id,
                'property_cost_method': costing_method,
                'create_date': create_date,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Master Category updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating master category: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }
        
class MasterPoSCategoryPATCH(http.Controller):
    @http.route(['/api/pos_category/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_master_pos_category_item(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            
            category_name = data.get('category_name')
            
            master_category = env['pos.category'].sudo().browse(int(return_id))
            if not master_category.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'POS Category not found',
                    'id': return_id
                }

            # Update name
            master_category.write({
                'name': category_name,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'POS Category updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating POS category: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }

class GoodsIssuePATCH(http.Controller):
    @http.route(['/api/goods_issue/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_goods_issue_order(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            goods_issue_order = env['stock.picking'].sudo().search([
                ('id', '=', return_id),
                ('picking_type_id.name', '=', 'Goods Issue')
            ], limit=1)

            if not goods_issue_order.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Goods Issue not found',
                    'id': return_id
                }

            goods_issue_order.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Goods Issue updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating Goods Issue: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }
        
class GoodsReceiptPATCH(http.Controller):
    @http.route(['/api/goods_receipt/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_goods_receipt_order(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            goods_receipt_order = env['stock.picking'].sudo().search([
                ('id', '=', return_id),
                ('picking_type_id.name', '=', 'Goods Receipts')
            ], limit=1)

            if not goods_receipt_order.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Goods Receipt not found',
                    'id': return_id
                }

            goods_receipt_order.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Goods Receipt updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating Goods Receipt: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }

class GRPOPATCH(http.Controller):
    @http.route(['/api/grpo_transfer/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_grpo_order(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            grpo_order = env['stock.picking'].sudo().search([
                ('id', '=', return_id),
                ('picking_type_id.name', '=', 'GRPO')
            ], limit=1)

            if not grpo_order.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'GRPO not found',
                    'id': return_id
                }

            grpo_order.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'GRPO updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating GRPO: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }
        
class InternalTransferPATCH(http.Controller):
    @http.route(['/api/internal_transfers/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_internal_transfer_order(self, return_id, **kwargs):
        return self._update_stock_picking(return_id, 'Internal Transfers', 'Internal Transfer')

class TsOutPATCH(http.Controller):
    @http.route(['/api/transfer_stock_out/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_transit_out_order(self, return_id, **kwargs):
        return self._update_stock_picking(return_id, 'TS Out', 'Transit Out')

class TsInPATCH(http.Controller):
    @http.route(['/api/transfer_stock_in/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_transit_in_order(self, return_id, **kwargs):
        return self._update_stock_picking(return_id, 'TS In', 'Transit In')

    @staticmethod
    def _update_stock_picking(return_id, picking_type_name, operation_name):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': f'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            stock_picking = env['stock.picking'].sudo().search([
                ('id', '=', return_id),
                ('picking_type_id.name', '=', picking_type_name)
            ], limit=1)

            if not stock_picking.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': f'{operation_name} not found',
                    'id': return_id
                }

            stock_picking.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': f'{operation_name} updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating {operation_name}: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }

class AccountMovePATCH(http.Controller):
    @http.route(['/api/invoice_order/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_invoice_order(self, return_id, **kwargs):
        return self._update_account_move(return_id, 'out_invoice', 'Invoice')

    @http.route(['/api/credit_memo/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_credit_memo(self, return_id, **kwargs):
        return self._update_account_move(return_id, 'out_refund', 'Credit Memo')

    @staticmethod
    def _update_account_move(return_id, move_type, operation_name):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': f'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            account_move = env['account.move'].sudo().search([
                ('id', '=', return_id),
                ('move_type', '=', move_type)
            ], limit=1)

            if not account_move.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': f'{operation_name} not found',
                    'id': return_id
                }

            account_move.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': f'{operation_name} updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating {operation_name}: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }
        
class PaymentPATCH(http.Controller):
    @http.route(['/api/payment_invoice/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_payment_invoice(self, return_id, **kwargs):
        return self._update_payment(return_id, 'Payment Invoice')

    @http.route(['/api/payment_creditmemo/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_payment_credit_memo(self, return_id, **kwargs):
        return self._update_payment(return_id, 'Payment Credit Memo')

    @staticmethod
    def _update_payment(return_id, operation_name):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': f'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            payment = env['account.move'].sudo().search([
                ('id', '=', return_id),
                ('move_type', '=', 'entry')
            ], limit=1)

            if not payment.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': f'{operation_name} not found',
                    'id': return_id
                }

            payment.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': f'{operation_name} updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating {operation_name}: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }

class PurchaseOrderPATCH(http.Controller):
    @http.route(['/api/purchase_order/<int:return_id>'], type='json', auth='none', methods=['PATCH'], csrf=False)
    def update_purchase_order(self, return_id, **kwargs):
        try:
            # Get configuration
            config = request.env['setting.config'].sudo().search([('vit_config_server', '=', 'mc')], limit=1)
            if not config:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Configuration not found.",
                }
            
            username = config.vit_config_username
            password = config.vit_config_password_api

            # Manual authentication
            uid = request.session.authenticate(request.session.db, username, password)
            if not uid:
                return {
                    'status': "Failed",
                    'code': 401,
                    'message': "Authentication failed.",
                }

            # Use superuser environment
            env = request.env(user=request.env.ref('base.user_admin').id)

            data = request.get_json_data()
            is_integrated = data.get('is_integrated')

            if not isinstance(is_integrated, bool):
                return {
                    'code': 400,
                    'status': 'error',
                    'message': 'Invalid data: is_integrated must be a boolean',
                    'id': return_id
                }

            purchase_order = env['purchase.order'].sudo().search([('id', '=', return_id)], limit=1)

            if not purchase_order.exists():
                return {
                    'code': 404,
                    'status': 'error',
                    'message': 'Purchase Order not found',
                    'id': return_id
                }

            purchase_order.write({
                'is_integrated': is_integrated,
                'write_uid': uid
            })

            return {
                'code': 200,
                'status': 'success',
                'message': 'Purchase Order updated successfully',
                'id': return_id
            }

        except Exception as e:
            _logger.error(f"Error updating Purchase Order: {str(e)}")
            return {
                'code': 500,
                'status': 'error',
                'message': str(e),
                'id': return_id
            }