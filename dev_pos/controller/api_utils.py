# api_utils.py
import json
from odoo import http, _
import werkzeug.exceptions

def check_authorization():
    request_auth_header = http.request.httprequest.headers.get('Authorization')
    if not request_auth_header:
        raise werkzeug.exceptions.Unauthorized(_('Authorization header not found.'))
    
    # Retrieve all tokens for Odoo, SAP, and Netsuite
    token_records = http.request.env['token.generate'].sudo().search([
        ('vit_client_name', 'in', ['Odoo', 'SAP', 'Netsuite'])
    ])
    
    # Check if the request header matches any of the stored tokens
    valid_token = False
    for token in token_records:
        if token.vit_encrypt == request_auth_header:
            valid_token = True
            break
    
    if not valid_token:
        raise werkzeug.exceptions.Unauthorized(_('Invalid authorization header.'))

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
