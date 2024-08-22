import json
import random
import urllib.request


class OdooClient:

    # Konstruktor
    def __init__(self, url, db, username, password, server_name):
        self.url = url
        self.db = db
        self.username = username
        self.password = password
        self.uid = self.authenticate()
        self.server_name = server_name

    # Melakukan autentikasi ke instance Odoo dan mendapatkan UID
    def authenticate(self):
        return self.call_odoo('common', 'authenticate', self.db, self.username, self.password, {})

    # Memanggil layanan JSON-RPC Odoo
    def call_odoo(self, service, method, *args):
        payload = {
            'jsonrpc': '2.0',
            'method': 'call',
            'params': {
                'service': service,
                'method': method,
                'args': args,
            },
            'id': random.randint(0, 1000000000),
        }
        headers = {'Content-Type': 'application/json'}
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(self.url, data, headers)
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if result.get('error'):
                raise Exception(result['error'])
            return result['result']
