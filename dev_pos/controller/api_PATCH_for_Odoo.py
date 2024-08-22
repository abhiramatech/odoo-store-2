from odoo import http
from odoo.http import request
import json
from .api_utils import check_authorization, paginate_records, serialize_response, serialize_error_response

class MasterCustomerPATCH(http.Controller):
    @http.route(['/api/master_customer/<int:return_id>'], type='json', auth='public', methods=['PATCH'], csrf=False)
    def update_master_customer(self, return_id, **kwargs):
        check_authorization()
        data = request.httprequest.get_json()
        name = data.get('name')
        street = data.get('street')
        email = data.get('email')
        mobile = data.get('mobile')
        website = data.get('website')
        customer_code = data.get('customer_code')
        is_integrated = data.get('is_integrated')
        user_name = data.get('user_name')

        admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
        if not admin_user:
            return {
                'status': "Failed",
                'code': 500,
                'message': "Administrator user not found.",
            }

        master_customer = request.env['res.partner'].sudo().browse(return_id)
        if master_customer.exists():
            master_customer.write({'name': name, 
                                   'street': street,
                                   'email': email, 
                                   'mobile': mobile, 
                                   'website': website,
                                   'customer_code': customer_code,
                                   'is_integrated': is_integrated,
                                   'write_uid': admin_user.id
                                   })
            
            return json.dumps({'code': 200, 'status': 'success', 'message': 'Master Customer updated successfully', 'id': return_id})
        else:
            return json.dumps({'code': 404, 'status': 'error', 'message': 'Master Customer not found', 'id': return_id})
        
class MasterItemPATCH(http.Controller):
    @http.route(['/api/master_item/<int:return_id>'], type='json', auth='public', methods=['PATCH'], csrf=False)
    def update_master_item(self, return_id, **kwargs):
        try:
            # Check authorization
            check_authorization()
            
            # Parse the incoming data
            data = request.httprequest.get_json()
            master_item_id = data.get('id')
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
            pos_categ_id = data.get('pos_categ_id')
            category_name = data.get('category_name')
            available_in_pos = data.get('available_in_pos')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }
            
            # Retrieve the master item from the database
            master_item = request.env['product.template'].sudo().browse(return_id)

            name_categ = request.env['product.category'].sudo().search([('complete_name', '=', category_name)], limit=1)
            if not name_categ:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': f"Failed to create Item. Category not found: {category_name}.",
                }
            
            if master_item:
                # Update the fields with the provided data
                master_item.write({
                    'name': product_name,
                    'default_code': product_code,
                    'list_price': sales_price,
                    # 'standard_price': sales_price,
                    'is_integrated': is_integrated,
                    'detailed_type': product_type,
                    'invoice_policy': invoicing_policy,
                    'list_price': sales_price,
                    'standard_price': cost,
                    'uom_id': uom_id,
                    'uom_po_id': uom_po_id,
                    'categ_id': name_categ.id,
                    'pos_categ_ids': [(6, 0, [pos_categ_id])],
                    'available_in_pos': available_in_pos,
                    'write_uid': admin_user.id
                    # 'active': active
                })
            # Return success response
            return json.dumps({'code': 200, 'status': 'success', 'message': 'Master Item updated successfully', 'id': master_item.id})
        except Exception as e:
            # Handle exceptions and return error response
            return json.dumps({'code': 500, 'status': 'error', 'message': str(e), 'id': return_id})

class MasterPricelistPATCH(http.Controller):
    @http.route(['/api/master_pricelist/<int:return_id>'], type='json', auth='public', methods=['PATCH'], csrf=False)
    def update_master_pricelist(self, return_id, **kwargs):
        try:
            check_authorization()
            data = request.httprequest.get_json()
            name = data.get('name')
            currency_id = data.get('currency_id')
            pricelist_ids = data.get('pricelist_ids')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            master_pricelist = request.env['product.pricelist'].sudo().browse(int(return_id))

            # Update name and currency_id
            master_pricelist.write({
                'name': name,
                'currency_id': currency_id,
                'write_uid': admin_user.id
            })

            # Update pricelist_ids
            for item in pricelist_ids:
                product_code = item['product_code']
                product_id = request.env['product.template'].sudo().search([('default_code', '=', product_code)], limit=1).id

                # Fetch the specific pricelist item to be updated
                pricelist_item = request.env['product.pricelist.item'].sudo().search([('product_tmpl_id', '=', product_id), ('pricelist_id', '=', return_id)])

                # Check if the pricelist item exists before attempting to update
                if pricelist_item.exists():
                    pricelist_item.write({
                        'min_quantity': item['quantity'],
                        'fixed_price': item['price'],
                        'date_start': item['date_start'],
                        'date_end': item['date_end'],
                        'write_uid': request.env.user.id
                    })
                else:
                    # Handle the case where the pricelist item does not exist (optional)
                    return json.dumps({"code": 404, "status": 'failed', "message": f"Pricelist item with product code {product_code} not found", "id": return_id})

            return json.dumps({'code': 200, 'status': 'success', 'message': 'Master Pricelist updated successfully', 'id': return_id})

        except Exception as e:
            return json.dumps({"code": 500, "status": 'failed', "message": str(e), "id": return_id})

class MasterCategoryPATCH(http.Controller):
    @http.route(['/api/item_category/<int:return_id>'], type='json', auth='public', methods=['PATCH'], csrf=False)
    def update_master_category_item(self, return_id, **kwargs):
        try:
            check_authorization()
            data = request.httprequest.get_json()
            
            category_name = data.get('category_name')
            parent_cateogry_id = data.get('parent_cateogry_id')
            costing_method = data.get('costing_method')
            create_date = data.get('create_date')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            master_category = request.env['product.category'].sudo().browse(int(return_id))

            # Update name and currency_id
            master_category.write({
                'name': category_name,
                'parent_id': parent_cateogry_id,
                'property_cost_method': costing_method,
                'create_date': create_date,
                'write_uid': request.env.user.id
            })

            return json.dumps({'code': 200, 'status': 'success', 'message': 'Master Category updated successfully', 'id': return_id})

        except Exception as e:
            return json.dumps({"code": 500, "status": 'failed', "message": str(e), "id": return_id})
        
class MasterPoSCategoryPATCH(http.Controller):
    @http.route(['/api/pos_category/<int:return_id>'], type='json', auth='public', methods=['PATCH'], csrf=False)
    def update_master_pos_category_item(self, return_id, **kwargs):
        try:
            check_authorization()
            data = request.httprequest.get_json()
            
            category_name = data.get('category_name')
            user_name = data.get('user_name')
            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }
            
            master_category = request.env['pos.category'].sudo().browse(int(return_id))

            # Update name and currency_id
            master_category.write({
                'name': category_name,
                'write_uid': admin_user.id
            })

            return json.dumps({'code': 200, 'status': 'success', 'message': 'Master Category updated successfully', 'id': return_id})

        except Exception as e:
            return json.dumps({"code": 500, "status": 'failed', "message": str(e), "id": return_id})

class GoodsIssuePATCH(http.Controller):
    @http.route(['/api/goods_issue/<int:return_id>'], type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_goods_issue_order(self, return_id, **kwargs):
        check_authorization()
        data = json.loads(request.httprequest.data)
        is_integrated = data.get('is_integrated')
        user_name = data.get('user_name')

        admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
        if not admin_user:
            return {
                'status': "Failed",
                'code': 500,
                'message': "Administrator user not found.",
            }

        if is_integrated:
            goods_issue_order = request.env['stock.picking'].sudo().search([('id', '=', return_id), ('picking_type_id.name', '=', 'Goods Issue')], limit=1)
            if goods_issue_order.exists():
                goods_issue_order.write({'is_integrated': is_integrated,
                                        'write_uid': admin_user.id})
                return json.dumps({'code': 200, 'status': 'success', 'message': 'Goods Issue updated successfully', 'id': return_id})
            else:
                return json.dumps({'code': 404, 'status': 'error', 'message': 'Goods Issue not found', 'id': return_id})
        else:
            return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        
class GoodsReceiptPATCH(http.Controller):
    @http.route(['/api/goods_receipt/<int:return_id>'], type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_goods_receipt_order(self, return_id, **kwargs):
        check_authorization()
        data = json.loads(request.httprequest.data)
        is_integrated = data.get('is_integrated')
        user_name = data.get('user_name')

        admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
        if not admin_user:
            return {
                'status': "Failed",
                'code': 500,
                'message': "Administrator user not found.",
            }

        if is_integrated:
            goods_receipt_order = request.env['stock.picking'].sudo().search([('id', '=', return_id), ('picking_type_id.name', '=', 'Goods Receipts')], limit=1)
            if goods_receipt_order.exists():
                goods_receipt_order.write({'is_integrated': is_integrated,
                                        'write_uid': admin_user.id})
                return json.dumps({'code': 200, 'status': 'success', 'message': 'Goods Receipt updated successfully', 'id': return_id})
            else:
                return json.dumps({'code': 404, 'status': 'error', 'message': 'Goods Receipt not found', 'id': return_id})
        else:
            return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        
class GRPOPATCH(http.Controller):
    @http.route(['/api/grpo_transfer/<int:return_id>'], type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_grpo_order(self, return_id, **kwargs):
        check_authorization()
        data = json.loads(request.httprequest.data)
        is_integrated = data.get('is_integrated')
        user_name = data.get('user_name')

        admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
        if not admin_user:
            return {
                'status': "Failed",
                'code': 500,
                'message': "Administrator user not found.",
            }

        if is_integrated:
            grpo_order = request.env['stock.picking'].sudo().search([('id', '=', return_id), ('picking_type_id.name', '=', 'GRPO')], limit=1)
            if grpo_order.exists():
                grpo_order.write({'is_integrated': is_integrated, 'write_uid': admin_user.id})
                return json.dumps({'code': 200, 'status': 'success', 'message': 'GRPO updated successfully', 'id': return_id})
            else:
                return json.dumps({'code': 404, 'status': 'error', 'message': 'GRPO not found', 'id': return_id})
        else:
            return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        
class InternalTransferPATCH(http.Controller):
    @http.route(['/api/internal_transfers/<int:return_id>'], type='json', auth='public', methods=['PATCH'], csrf=False)
    def update_internal_transfer_order(self, return_id, **kwargs):
        try:
            check_authorization()
            data = json.loads(request.httprequest.data)
            is_integrated = data.get('is_integrated')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            if is_integrated:
                internal_trasnfer_order = request.env['stock.picking'].sudo().search([('id', '=', return_id), ('picking_type_id.name', '=', 'Internal Transfers')], limit=1)
                if internal_trasnfer_order.exists():
                    internal_trasnfer_order.write({'is_integrated': is_integrated,
                                                   'write_uid': admin_user.id})
                    return json.dumps({'code': 200, 'status': 'success', 'message': 'Internal Transfer updated successfully', 'id': return_id})
                else:
                    return json.dumps({'code': 404, 'status': 'error', 'message': 'Internal Transfer not found', 'id': return_id})
            else:
                return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        except Exception as e:
            return serialize_error_response(str(e))

class TsOutPATCH(http.Controller):
    @http.route(['/api/transfer_stock_out/<int:return_id>'], type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_transit_out_order(self, return_id, **kwargs):
        try:
            check_authorization()
            data = json.loads(request.httprequest.data)
            is_integrated = data.get('is_integrated')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            if is_integrated:
                transit_out_order = request.env['stock.picking'].sudo().search([('id', '=', return_id), ('picking_type_id.name', '=', 'TS Out')], limit=1)
                if transit_out_order.exists():
                    transit_out_order.write({'is_integrated': is_integrated,
                                            'write_uid': admin_user.id})
                    return json.dumps({'code': 200, 'status': 'success', 'message': 'Transit Out updated successfully', 'id': return_id})
                else:
                    return json.dumps({'code': 404, 'status': 'error', 'message': 'Transit Out not found', 'id': return_id})
            else:
                return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        except Exception as e:
            return serialize_error_response(str(e))
        
class TsInPATCH(http.Controller):
    @http.route(['/api/transfer_stock_in/<int:return_id>'], type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_transit_in_order(self, return_id, **kwargs):
        try:
            check_authorization()
            data = json.loads(request.httprequest.data)
            is_integrated = data.get('is_integrated')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            if is_integrated:
                transit_in_order = request.env['stock.picking'].sudo().search([('id', '=', return_id), ('picking_type_id.name', '=', 'TS In')], limit=1)
                if transit_in_order.exists():
                    transit_in_order.write({'is_integrated': is_integrated,
                                            'write_uid': admin_user.id})
                    return json.dumps({'code': 200, 'status': 'success', 'message': 'Transit In updated successfully', 'id': return_id})
                else:
                    return json.dumps({'code': 404, 'status': 'error', 'message': 'Transit In not found', 'id': return_id})
            else:
                return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        except Exception as e:
            return serialize_error_response(str(e))

class InvoicePATCH(http.Controller):
    @http.route(['/api/invoice_order/<int:return_id>'], type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_invoice_order(self, return_id, **kwargs):
        try:
            check_authorization()
            data = json.loads(request.httprequest.data)
            is_integrated = data.get('is_integrated')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            if is_integrated:
                invoice_order = request.env['account.move'].sudo().search([('id', '=', return_id), ('move_type', '=', 'out_invoice')], limit=1)
                if invoice_order.exists():
                    invoice_order.write({'is_integrated': is_integrated,
                                         'write_uid': admin_user.id})
                    return json.dumps({'code': 200, 'status': 'success', 'message': 'Invoice updated successfully', 'id': return_id})
                else:
                    return json.dumps({'code': 404, 'status': 'error', 'message': 'Invoice not found', 'id': return_id})
            else:
                return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        except Exception as e:
            return serialize_error_response(str(e))
        
class CreditMemoPATCH(http.Controller):
    @http.route(['/api/credit_memo/<int:return_id>'], type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_credit_memo(self, return_id, **kwargs):
        try:
            check_authorization()
            data = json.loads(request.httprequest.data)
            is_integrated = data.get('is_integrated')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            if is_integrated:
                invoice_order = request.env['account.move'].sudo().search([('id', '=', return_id), ('move_type', '=', 'out_refund')], limit=1)
                if invoice_order.exists():
                    invoice_order.write({'is_integrated': is_integrated,
                                         'write_uid': admin_user.id})
                    return json.dumps({'code': 200, 'status': 'success', 'message': 'Credit Memo updated successfully', 'id': return_id})
                else:
                    return json.dumps({'code': 404, 'status': 'error', 'message': 'Credit Memo not found', 'id': return_id})
            else:
                return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        except Exception as e:
            return serialize_error_response(str(e))
        
class PaymentPATCH(http.Controller):
    @http.route(['/api/payment_invoice/<int:return_id>'], type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_payment_invoice(self, return_id, **kwargs):
        try:
            check_authorization()
            data = json.loads(request.httprequest.data)
            is_integrated = data.get('is_integrated')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            if is_integrated:
                payment_invoice= request.env['account.move'].sudo().search([('id', '=', return_id), ('move_type', '=', 'entry')], limit=1)
                if payment_invoice.exists():
                    payment_invoice.write({'is_integrated': is_integrated,
                                           'write_uid': admin_user.id})
                    return json.dumps({'code': 200, 'status': 'success', 'message': 'Payment Invoice updated successfully', 'id': return_id})
                else:
                    return json.dumps({'code': 404, 'status': 'error', 'message': 'Payment Invoice not found', 'id': return_id})
            else:
                return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        except Exception as e:
            return serialize_error_response(str(e))
        
class PaymentCreditMemoPATCH(http.Controller):
    @http.route(['/api/payment_creditmemo/<int:return_id>'], type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_payment_credit_memo(self, return_id, **kwargs):
        try:
            check_authorization()
            data = json.loads(request.httprequest.data)
            is_integrated = data.get('is_integrated')
            user_name = data.get('user_name')
            
            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            if is_integrated:
                payment_creditmemo= request.env['account.move'].sudo().search([('id', '=', return_id), ('move_type', '=', 'entry')], limit=1)
                if payment_creditmemo.exists():
                    payment_creditmemo.write({'is_integrated': is_integrated,
                                              'write_uid': admin_user.id})
                    return json.dumps({'code': 200, 'status': 'success', 'message': 'Payment Credit Memo updated successfully', 'id': return_id})
                else:
                    return json.dumps({'code': 404, 'status': 'error', 'message': 'Payment Credit Memo not found', 'id': return_id})
            else:
                return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        except Exception as e:
            return serialize_error_response(str(e))

class PurchaseOrderPATCH(http.Controller):
    @http.route(['/api/purchase_order/<int:return_id>'], type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_purchase_order(self, return_id, **kwargs):
        try:
            check_authorization()
            data = json.loads(request.httprequest.data)
            is_integrated = data.get('is_integrated')
            user_name = data.get('user_name')

            admin_user = request.env['res.users'].sudo().search([('login', '=', user_name), ('active', '=', True)], limit=1)
            if not admin_user:
                return {
                    'status': "Failed",
                    'code': 500,
                    'message': "Administrator user not found.",
                }

            if is_integrated:
                invoice_order = request.env['purchase.order'].sudo().search([('id', '=', return_id)], limit=1)
                if invoice_order.exists():
                    invoice_order.write({'is_integrated': is_integrated,
                                         'write_uid': admin_user.id})
                    return json.dumps({'code': 200, 'status': 'success', 'message': 'Purchase Order updated successfully', 'id': return_id})
                else:
                    return json.dumps({'code': 404, 'status': 'error', 'message': 'Purchase Order not found', 'id': return_id})
            else:
                return json.dumps({'code': 500, 'status': 'error', 'message': 'Invalid data', 'id': return_id})
        except Exception as e:
            return serialize_error_response(str(e))