import os

from cryptography.fernet import Fernet, InvalidToken


class SecretCipher:
    """Application-level authenticated encryption for operational credentials."""

    environment_variable = "PPA_SECRET_ENCRYPTION_KEY"

    @classmethod
    def _fernet(cls):
        key = os.getenv(cls.environment_variable)
        if not key:
            raise ValueError("Secret encryption key is not configured.")
        try:
            return Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as error:
            raise ValueError("Secret encryption key is invalid.") from error

    @classmethod
    def encrypt(cls, plaintext):
        if plaintext is None:
            return False
        return cls._fernet().encrypt(str(plaintext).encode("utf-8")).decode("ascii")

    @classmethod
    def decrypt(cls, ciphertext):
        if not ciphertext:
            return False
        try:
            return cls._fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeDecodeError) as error:
            raise ValueError("Stored mailbox credential cannot be decrypted.") from error
