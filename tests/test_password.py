import pytest
from app.services.password_service import (
    validate_password_policy,
    hash_password,
    verify_password,
    PasswordValidationError,
)


def test_reject_password_length_eight_or_less():
    """Password policy rule 1: Must be more than 8 characters."""
    with pytest.raises(PasswordValidationError, match="more than 8 characters"):
        validate_password_policy("Ab1!")  # 4 chars

    with pytest.raises(PasswordValidationError, match="more than 8 characters"):
        validate_password_policy("Passw1@d")  # exactly 8 chars


def test_reject_missing_uppercase():
    """Password policy rule 2: Must contain at least one uppercase letter."""
    with pytest.raises(PasswordValidationError, match="uppercase letter"):
        validate_password_policy("lowercase123!@#")


def test_reject_missing_lowercase():
    """Password policy rule 3: Must contain at least one lowercase letter."""
    with pytest.raises(PasswordValidationError, match="lowercase letter"):
        validate_password_policy("UPPERCASE123!@#")


def test_reject_missing_special_character():
    """Password policy rule 4: Must contain at least one special character."""
    with pytest.raises(PasswordValidationError, match="special character"):
        validate_password_policy("ValidLength123NoSpecial")


def test_accept_valid_passwords():
    """Valid passwords meeting all criteria must pass without exception."""
    valid_passwords = [
        "StrongP@ssw0rd!",
        "Secure#Pass2026",
        "Brightloop$1234",
        "Admin!SuperSecret2026",
    ]
    for pwd in valid_passwords:
        validate_password_policy(pwd)  # Should not raise


def test_argon2id_hashing_and_verification():
    """Verify that Argon2id generates valid hashes and verifies correctly."""
    password = "CorrectHorse$Battery9"
    hashed = hash_password(password)

    # Hash must be distinct from plaintext
    assert hashed != password
    assert hashed.startswith("$argon2id$")

    # Verification must succeed for correct password
    assert verify_password(password, hashed) is True

    # Verification must fail for incorrect password
    assert verify_password("WrongPassword!123", hashed) is False

    # Empty inputs must be rejected safely
    assert verify_password("", hashed) is False
    assert verify_password(password, "") is False

