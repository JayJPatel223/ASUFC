"""Single designated staff account; passwords never stored in plaintext."""
import hashlib
import secrets

def hash_password(password):
    salt=secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=2**14,r=8,p=1,dklen=32)
    return salt+":"+digest.hex()

def verify_password(password,stored):
    salt,digest=stored.split(":")
    actual=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=2**14,r=8,p=1,dklen=32)
    return secrets.compare_digest(actual.hex(),digest)

def validate_password(password):
    if not 16<=len(password)<=1024 or password.isspace() or password=="replace-with-random-password":
        raise ValueError("Use a unique password of at least 16 characters")
