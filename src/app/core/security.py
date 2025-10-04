import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from app.services.config_manager import SECRET_KEY_FILE

# --- Constants ---
# We will reuse the master key as the secret for signing JWTs.
# This keeps all application secrets tied to one master key.
def get_jwt_secret_key() -> str:
    if not SECRET_KEY_FILE.exists():
        # This case should ideally not happen if ConfigManager has run,
        # but as a fallback, we can't proceed without a key.
        raise RuntimeError("secret.key not found. Cannot configure JWT.")
    return SECRET_KEY_FILE.read_bytes().decode()

SECRET_KEY = get_jwt_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# --- Password Utilities ---

def verify_password(plain_password: str, hashed_password: bytes) -> bool:
    """
    Verifies a plain-text password against a hashed password.

    Args:
        plain_password: The password to check.
        hashed_password: The stored hashed password.

    Returns:
        True if the password is correct, False otherwise.
    """
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password)

def get_password_hash(password: str) -> bytes:
    """
    Hashes a plain-text password.

    Args:
        password: The password to hash.

    Returns:
        The hashed password as bytes.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


# --- JWT Token Utilities ---

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a new JWT access token.

    Args:
        data: The data to encode in the token (e.g., user identifier).
        expires_delta: The optional expiration time for the token.

    Returns:
        The encoded JWT token as a string.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[str]:
    """
    Decodes a JWT access token to get the subject (username).

    Args:
        token: The JWT token to decode.

    Returns:
        The username (subject) if the token is valid, otherwise None.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        return username
    except JWTError:
        return None