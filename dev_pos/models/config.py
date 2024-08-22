import json
from cryptography.fernet import Fernet


class Config:

    # __init__ method: Konstruktor kelas yang dipanggil saat membuat instance dari kelas
    def __init__(self, file_path, encryption_key):
        self.config = self._read_config(file_path)
        self.cipher_suite = Fernet(encryption_key)

    # Membaca file JSON dan mengembalikan isinya dalam bentuk dictionary
    def _read_config(self, file_path):
        with open(file_path, 'r') as file:
            return json.load(file)

    # Mengambil konfigurasi untuk instance tertentu berdasarkan nama instance
    def get_instance(self, instance_name):
        return self.config.get(instance_name)

    # Mendekripsi password yang terenkripsi
    def decrypt_password(self, encrypted_password):
        return self.cipher_suite.decrypt(encrypted_password.encode()).decode()
