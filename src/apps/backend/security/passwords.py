"""Password hashing and verification with bcrypt.

Provides a thin wrapper around the ``bcrypt`` library for securely
hashing plaintext passwords and verifying them against stored hashes.
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt with a random salt.

    >>> hashed = hash_password("my-secret")
    >>> hashed.startswith("$2b$")
    True

    Args:
        plain: The plaintext password to hash.

    Returns:
        A bcrypt hash string (UTF-8 encoded).
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    """Check whether a plaintext password matches a bcrypt hash.

    >>> hashed = hash_password("correct-password")
    >>> verify_password("correct-password", hashed)
    True
    >>> verify_password("wrong-password", hashed)
    False

    Args:
        plain:         The plaintext password to check.
        password_hash: The stored bcrypt hash to compare against.

    Returns:
        True if the password matches, False otherwise (including if the
        hash is malformed).
    """
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False
