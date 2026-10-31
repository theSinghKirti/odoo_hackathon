import re
import string
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Configure Argon2id password hasher
_ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MB
    parallelism=1,
    hash_len=32,
)

# Set of special characters (punctuation and symbols)
SPECIAL_CHARACTERS = set(string.punctuation)


class PasswordValidationError(ValueError):
    """Raised when a password violates the password policy."""
    pass


def validate_password_policy(password: str) -> None:
    """
    Validates a password against the strict system policy:
    1. More than 8 characters in length.
    2. At least one uppercase letter [A-Z].
    3. At least one lowercase letter [a-z].
    4. At least one special character.
    
    Raises PasswordValidationError if any rule fails.
    """
    if not password or len(password) <= 8:
        raise PasswordValidationError("Password must be more than 8 characters in length.")

    if not any(c.isupper() for c in password):
        raise PasswordValidationError("Password must contain at least one uppercase letter.")

    if not any(c.islower() for c in password):
        raise PasswordValidationError("Password must contain at least one lowercase letter.")

    if not any(c in SPECIAL_CHARACTERS for c in password):
        raise PasswordValidationError("Password must contain at least one special character.")


def hash_password(password: str) -> str:
    """
    Hashes a password using Argon2id.
    """
    return _ph.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against an Argon2id hash.
    Safe against timing attacks.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        return _ph.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False

