# api_utils.py
import json
from odoo import http, _
import werkzeug.exceptions

def check_authorization():
    authorization_header = http.request.httprequest.headers.get('Authorization')
    
    # Retrieve the latest `vit_encrypt` value from the `token.generate` model
    token_record = http.request.env['token.generate'].sudo().search([('vit_client_name', 'in', ('Odoo', 'SAP', 'Netsuite'))], limit=1)
    
    if not token_record or authorization_header != token_record.vit_encrypt:
        raise werkzeug.exceptions.Unauthorized(_('Unauthorized'))

def paginate_records(model, domain, pageSize, page):
    pageSize = int(pageSize)
    page = max(1, int(page))
    offset = pageSize * (page - 1)
    total_records = http.request.env[model].sudo().search_count(domain)
    records = http.request.env[model].sudo().search(domain, limit=pageSize, offset=offset)
    return records, total_records

def serialize_response(data, total_records, total_pages):
    response_data = {
        'status': 200,
        'message': 'success',
        'data': data,
        'total_records': total_records,
        'total_pages': total_pages,
    }
    return werkzeug.wrappers.Response(
        status=200,
        content_type='application/json; charset=utf-8',
        response=json.dumps(response_data)
    )

def serialize_error_response(error_description):
    return werkzeug.wrappers.Response(
        status=400,
        content_type='application/json; charset=utf-8',
        response=json.dumps({
            'error': 'Error',
            'error_descrip': error_description,
        })
    )
