from datetime import timedelta

import pytest

from appbase import security

SECRET = "super-secret-key-of-sufficient-length!!"


def test_verify_password_roundtrip_and_mismatch():
    h = security.hash_password("correct horse")
    assert security.verify_password("correct horse", h) is True
    # A wrong password must return False, not raise VerifyMismatchError.
    assert security.verify_password("wrong", h) is False


def test_verify_token_valid():
    token = security.create_token({"sub": "alice"}, timedelta(hours=1), SECRET)
    assert security.verify_token(token, SECRET) == {"sub": "alice"}


def test_verify_token_expired_raises_valueerror():
    token = security.create_token({"sub": "alice"}, timedelta(seconds=-1), SECRET)
    # Expiry must surface as ValueError, not a leaked jwt.ExpiredSignatureError.
    with pytest.raises(ValueError):
        security.verify_token(token, SECRET)


def test_verify_token_bad_signature_raises_valueerror():
    token = security.create_token({"sub": "alice"}, timedelta(hours=1), SECRET)
    with pytest.raises(ValueError):
        security.verify_token(token, "the-wrong-secret-of-sufficient-length!!")
