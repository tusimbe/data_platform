# src/core/security.py
import base64
import hashlib

from cryptography.fernet import Fernet


def _derive_key(secret: str) -> bytes:
    """从任意长度密钥派生 Fernet 兼容的 32 字节 base64 密钥"""
    key_bytes = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes)


def encrypt_value(plaintext: str, secret_key: str) -> str:
    """加密字符串，返回 base64 编码的密文"""
    f = Fernet(_derive_key(secret_key))
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, secret_key: str) -> str:
    """解密密文，返回原始字符串"""
    f = Fernet(_derive_key(secret_key))
    return f.decrypt(ciphertext.encode()).decode()
