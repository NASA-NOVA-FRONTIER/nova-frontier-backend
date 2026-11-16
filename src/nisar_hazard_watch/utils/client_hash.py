import hashlib

from nisar_hazard_watch.constants.limits import CLIENT_KEY_LENGTH


def hash_client_key(client: str) -> str:
    """What is stored about a client: a digest of its address, never the address itself."""
    return hashlib.sha256(client.encode()).hexdigest()[:CLIENT_KEY_LENGTH]
