from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import os
from django.conf import settings

def generate_aes_key():
    return os.urandom(32)  # 256ビットのAESキーを生成

def encrypt_secret_key(secret_key):
    master_key = settings.SECRET_KEY[:32].encode()  # Djangoの秘密鍵をバイト型で使用
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(master_key), modes.CFB(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted_key = iv + encryptor.update(secret_key) + encryptor.finalize()
    return encrypted_key  # バイナリデータとして返す

def decrypt_secret_key(encrypted_key):
    master_key = settings.SECRET_KEY[:32].encode()  # Djangoの秘密鍵をバイト型で使用
    iv = encrypted_key[:16]
    cipher = Cipher(algorithms.AES(master_key), modes.CFB(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_key = decryptor.update(encrypted_key[16:]) + decryptor.finalize()
    return decrypted_key  # バイナリデータとして返す


def encrypt_user_data(data, secret_key):
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(secret_key), modes.CFB(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted_data = iv + encryptor.update(data.encode()) + encryptor.finalize()
    return encrypted_data  # バイナリデータとして返す

def decrypt_user_data(encrypted_data, secret_key):
    iv = encrypted_data[:16]
    cipher = Cipher(algorithms.AES(secret_key), modes.CFB(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted_data = decryptor.update(encrypted_data[16:]) + decryptor.finalize()
    return decrypted_data.decode()  # 復号化して文字列として返す
