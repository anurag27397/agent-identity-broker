import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey


PRIVATE_KEY_FILE = "private.pem"
PUBLIC_KEY_FILE = "public.pem"


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class KeyMaterial:
    def __init__(self, private_key: RSAPrivateKey):
        self.private_key = private_key
        self.public_key: RSAPublicKey = private_key.public_key()
        pub_bytes = self.public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        self.kid = hashlib.sha256(pub_bytes).hexdigest()[:16]

    @property
    def private_pem(self) -> bytes:
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @property
    def public_pem(self) -> bytes:
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def jwks(self) -> dict:
        numbers = self.public_key.public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": self.kid,
                    "n": _b64url_uint(numbers.n),
                    "e": _b64url_uint(numbers.e),
                }
            ]
        }


def load_or_generate(keys_dir: str) -> KeyMaterial:
    path = Path(keys_dir)
    path.mkdir(parents=True, exist_ok=True)
    private_path = path / PRIVATE_KEY_FILE

    if private_path.exists():
        private_key = serialization.load_pem_private_key(
            private_path.read_bytes(), password=None
        )
        if not isinstance(private_key, RSAPrivateKey):
            raise RuntimeError(f"{private_path} is not an RSA key")
    else:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        os.chmod(private_path, 0o600)

    material = KeyMaterial(private_key)
    (path / PUBLIC_KEY_FILE).write_bytes(material.public_pem)
    return material
