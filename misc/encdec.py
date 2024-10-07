import os
import base64
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
import argon2
import json
from cryptography.hazmat.primitives.ciphers.aead import AESGCMSIV, ChaCha20Poly1305

# Constants
SALT_SIZE = 16  # Size of the salt in bytes
KEY_SIZE = 32  # AES-256 requires a 32-byte key
ITERATIONS = 100000  # Number of iterations for the key derivation
BLOCK_SIZE = 128  # AES block size is 128 bits (16 bytes)


def _derive_key(password: str, salt: bytes) -> bytes:
    """
    Derive a cryptographic key from the given password and salt using PBKDF2HMAC with SHA-256.
    """
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=ITERATIONS,
        backend=default_backend(),
    )
    return kdf.derive(password.encode())


def enc_AESCBC(password: str, plaintext: str) -> str:
    """
    Encrypts the plaintext using AES-256 and a password. A random salt is used and included in the output.

    :param password: The password to use for key derivation.
    :param plaintext: The data to encrypt.
    :return: The base64-encoded ciphertext, including the salt.
    """
    # Generate a random salt
    salt = os.urandom(SALT_SIZE)

    # Derive the key from the password and salt
    key = _derive_key(password, salt)

    # Initialize cipher (AES-256 in CBC mode with a random IV)
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()

    # Pad the plaintext to be a multiple of the block size
    padder = padding.PKCS7(BLOCK_SIZE).padder()
    padded_data = padder.update(plaintext.encode()) + padder.finalize()

    # Encrypt the padded plaintext
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()

    # Prepend the salt and IV to the ciphertext and base64 encode the result
    encrypted_data = base64.b64encode(salt + iv + ciphertext).decode()
    return encrypted_data


def decrypt(password: str, encrypted: str) -> str:
    """
    Decrypts the ciphertext using AES-256 and the password.

    :param password: The password to use for key derivation.
    :param encrypted_data: The base64-encoded ciphertext, including the salt.
    :return: The decrypted plaintext.
    """
    # Decode the base64-encoded data
    encrypted_data = base64.b64decode(encrypted)

    # Extract the salt (first SALT_SIZE bytes) and IV (next 16 bytes)
    salt = encrypted_data[:SALT_SIZE]
    iv = encrypted_data[SALT_SIZE : SALT_SIZE + 16]
    ciphertext = encrypted_data[SALT_SIZE + 16 :]

    # Derive the key from the password and salt
    key = _derive_key(password, salt)

    # Initialize the cipher for decryption
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()

    # Decrypt the ciphertext
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Unpad the decrypted plaintext
    unpadder = padding.PKCS7(BLOCK_SIZE).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()

    return plaintext.decode()


KEY_LEN_BYTES = 32
SALT_LEN_BYTES = 16
NONCE_LEN_BYTES = 24


def kdf(secret: bytes, salt: bytes):
    return argon2.low_level.hash_secret_raw(
        secret,
        salt,
        time_cost=argon2.DEFAULT_TIME_COST,
        memory_cost=argon2.DEFAULT_MEMORY_COST,
        parallelism=argon2.DEFAULT_PARALLELISM,
        hash_len=KEY_LEN_BYTES,
        type=argon2.Type.ID,
    )


def enc_AESGCMSIV(password: str, content: str, extra: str | None = None) -> str:
    secret = password.encode("utf-8")
    data = content.encode("utf-8")
    extra_data = extra if extra is None else extra.encode("utf-8")
    salt = os.urandom(SALT_LEN_BYTES)
    nonce = os.urandom(NONCE_LEN_BYTES)
    key = kdf(secret, salt)
    cipher = AESGCMSIV(key)
    cipher_data = cipher.encrypt(nonce, data, extra_data)

    def b64e(obj: bytes) -> str:
        return base64.b64encode(obj).decode("utf-8")

    return json.dumps(
        {
            "cipher_text": b64e(cipher_data),
            "salt": b64e(salt),
            "nonce": b64e(nonce),
            "extra": extra,
        }
    )


def dec_AESGCMSIV(password: str, ciphertext: str) -> tuple[str, str]:
    secret = password.encode("utf-8")
    token = json.loads(ciphertext)

    def b64d(obj: str) -> bytes:
        return base64.b64decode(obj.encode("utf-8"))

    data = b64d(token["cipher_text"])
    salt = b64d(token["salt"])
    nonce = b64d(token["nonce"])
    extra = token["extra"]
    extra_data = extra if extra is None else extra.encode("utf-8")

    key = kdf(secret, salt)
    cipher = AESGCMSIV(key)
    return cipher.decrypt(nonce, data, extra_data).decode("utf-8"), extra


def enc_ChaCha20Poly1305(password: str, content: str, extra: str | None = None) -> str:
    secret = password.encode("utf-8")
    data = content.encode("utf-8")
    extra_data = extra if extra is None else extra.encode("utf-8")
    salt = os.urandom(SALT_LEN_BYTES)
    nonce = os.urandom(NONCE_LEN_BYTES)
    key = kdf(secret, salt)
    cipher = ChaCha20Poly1305(key)
    cipher_data = cipher.encrypt(nonce, data, extra_data)

    def b64e(obj: bytes) -> str:
        return base64.b64encode(obj).decode("utf-8")

    return json.dumps(
        {
            "cipher_text": b64e(cipher_data),
            "salt": b64e(salt),
            "nonce": b64e(nonce),
            "extra": extra,
        }
    )


def dec_ChaCha20Poly1305(password: str, ciphertext: str) -> tuple[str, str]:
    secret = password.encode("utf-8")
    token = json.loads(ciphertext)

    def b64d(obj: str) -> bytes:
        return base64.b64decode(obj.encode("utf-8"))

    data = b64d(token["cipher_text"])
    salt = b64d(token["salt"])
    nonce = b64d(token["nonce"])
    extra = token["extra"]
    extra_data = extra if extra is None else extra.encode("utf-8")

    key = kdf(secret, salt)
    cipher = ChaCha20Poly1305(key)
    return cipher.decrypt(nonce, data, extra_data).decode("utf-8"), extra


if __name__ == "__main__":
    import getpass

    enc = enc_ChaCha20Poly1305
    dec = dec_ChaCha20Poly1305
    plaintext = input("message:")
    password = getpass.getpass("password:")
    encrypted = enc(password, plaintext)
    decrypted, extra = dec(password, encrypted)

    print(f"Message: {plaintext}")
    print(f"Password: {password}")
    print(f"Encrypted: {encrypted}")
    print(f"Decrypted: {decrypted}")
