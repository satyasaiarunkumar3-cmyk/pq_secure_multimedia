import os, hashlib

def kyber_keygen():
    private_key = os.urandom(32)
    public_key = hashlib.sha256(private_key).digest()
    return public_key, private_key
