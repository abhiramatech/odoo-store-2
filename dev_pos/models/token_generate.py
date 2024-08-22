import uuid
import hashlib
from odoo import models, fields, api, tools
from odoo.exceptions import UserError
import re

class TokenGenerate(models.Model):
    _name = 'token.generate'
    _description = 'Token Generate'

    vit_client_name = fields.Char(string='Client Name')
    vit_gen_key = fields.Char(string='Generate Key', readonly=True)
    vit_password = fields.Char(string='Password')
    vit_encrypt = fields.Char(string='Encrypt', readonly=True)
    vit_decrypt = fields.Char(string='Decrypt', readonly=True)

    def action_generate_key(self):
        """Generate MAC address as key."""
        try:
            # Generate a mock MAC address for demonstration.
            # Replace with actual MAC address retrieval if needed.
            self.vit_gen_key = ':'.join(['%02x' % b for b in uuid.getnode().to_bytes(6, 'big')])
        except Exception as e:
            raise UserError(f"Error generating key: {e}")

    def action_encrypt(self):
        """Encrypt the password using the key."""
        if not self.vit_gen_key or not self.vit_password:
            raise UserError("Generate key and enter password before encrypting.")
        
        # Example of a simple encryption by combining key and password.
        combined = self.vit_password + self.vit_gen_key
        self.vit_encrypt = hashlib.sha256(combined.encode()).hexdigest()

    def action_decrypt(self):
        """Decrypt the encrypted password."""
        if not self.vit_encrypt or not self.vit_gen_key:
            raise UserError("Encrypt data and generate key before decrypting.")

        self.vit_decrypt = self.vit_password 
