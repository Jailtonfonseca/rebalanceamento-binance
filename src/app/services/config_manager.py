"""Manages application configuration, including sensitive data encryption.

This module provides a robust configuration management system using Pydantic
for validation and Fernet for encryption. It handles loading settings from a
JSON file, encrypting and decrypting API keys, managing a master encryption key,
and providing a singleton instance of the configuration for the application.
"""
import os
import json
from pathlib import Path
from typing import Dict, Literal, Optional

import logging
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, Field, ValidationError, field_validator
import bcrypt

logger = logging.getLogger(__name__)

# --- Constants ---
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
CONFIG_FILE = DATA_DIR / "config.json"
SECRET_KEY_FILE = DATA_DIR / "secret.key"

# --- Pydantic Models for Configuration ---


class BinanceSettings(BaseModel):
    """Pydantic model for Binance API settings.

    Attributes:
        api_key: The plaintext Binance API key (used for input, not saved).
        secret_key: The plaintext Binance secret key (used for input, not saved).
        api_key_encrypted: The encrypted Binance API key.
        secret_key_encrypted: The encrypted Binance secret key.
    """
    api_key: str = ""
    secret_key: str = ""
    # These will hold the encrypted values
    api_key_encrypted: Optional[bytes] = None
    secret_key_encrypted: Optional[bytes] = None


class CMCSettings(BaseModel):
    """Pydantic model for CoinMarketCap API settings.

    Attributes:
        api_key: The plaintext CMC API key (used for input, not saved).
        api_key_encrypted: The encrypted CMC API key.
    """
    api_key: str = ""
    api_key_encrypted: Optional[bytes] = None


class AppSettings(BaseModel):
    """The main Pydantic model for all application settings.

    This model aggregates all other settings models and defines the structure
    of the main `config.json` file. It includes validation rules.
    """
    admin_user: str = Field("admin", description="Username for the web UI.")
    password_hash: Optional[bytes] = Field(
        None, description="Hashed password for the admin user."
    )

    binance: BinanceSettings = Field(default_factory=BinanceSettings)
    cmc: CMCSettings = Field(default_factory=CMCSettings)

    max_cmc_rank: int = Field(
        100, gt=0, le=5000, description="Fetch top N assets from CoinMarketCap."
    )
    strategy: Literal["periodic", "threshold"] = Field(
        "periodic", description="Rebalancing strategy."
    )
    periodic_hours: int = Field(
        24, gt=0, description="Interval in hours for periodic rebalancing."
    )
    threshold_pct: float = Field(
        5.0, gt=0, lt=100, description="Threshold percentage to trigger rebalancing."
    )

    allocations: Dict[str, float] = Field(
        default_factory=lambda: {"BTC": 50.0, "ETH": 50.0},
        description="Target allocations for assets.",
    )
    base_pair: str = Field(
        "USDT", description="The stablecoin to use for trading (e.g., USDT, BUSD)."
    )
    dry_run: bool = Field(
        True, description="If true, simulates trades without executing them."
    )

    min_trade_value_usd: float = Field(
        10.0, ge=10.0, description="Minimum value in USD for a trade to be executed."
    )
    trade_fee_pct: float = Field(
        0.1, ge=0, le=5, description="The trading fee percentage."
    )

    @field_validator("allocations")
    @classmethod
    def allocations_must_sum_to_100(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Validates that the allocation percentages sum to 100."""
        if round(sum(v.values())) != 100:
            raise ValueError("Allocation percentages must sum to 100.")
        return v


# --- Configuration Manager ---


class ConfigManager:
    """Handles loading, saving, and encrypting application settings.

    This class is responsible for all interactions with the configuration file
    and the master encryption key. It uses Fernet for symmetric encryption of
    sensitive data like API keys. It is designed to be used as a singleton.

    Attributes:
        config_path: The path to the JSON configuration file.
        secret_key_path: The path to the file storing the Fernet key.
        fernet: The Fernet instance used for encryption/decryption.
        settings: The Pydantic model instance holding the current settings.
    """
    def __init__(
        self, config_path: Path = CONFIG_FILE, secret_key_path: Path = SECRET_KEY_FILE
    ):
        """Initializes the ConfigManager.

        Args:
            config_path: The path to the configuration file.
            secret_key_path: The path to the secret key file.
        """
        self.config_path = config_path
        self.secret_key_path = secret_key_path
        self.fernet = self._get_fernet()
        self.settings = self._load_settings()

    def _get_fernet(self) -> Fernet:
        """Initializes Fernet using the master key.

        The key is sourced from the MASTER_KEY environment variable first.
        If not found, it tries to read from the secret key file. If that file
        doesn't exist, a new key is generated and saved.

        Returns:
            An initialized Fernet instance.
        """
        master_key = os.getenv("MASTER_KEY")
        if master_key:
            key = master_key.encode()
        elif self.secret_key_path.exists():
            key = self.secret_key_path.read_bytes()
        else:
            DATA_DIR.mkdir(exist_ok=True)
            key = Fernet.generate_key()
            self.secret_key_path.write_bytes(key)
            logger.warning("=" * 80)
            logger.warning("!!! NEW MASTER KEY GENERATED !!!")
            logger.warning(f"A new master key has been generated and saved to: {self.secret_key_path}")
            logger.warning("You MUST back up this key and set it as the MASTER_KEY environment variable.")
            logger.warning("If you lose this key, you will lose access to your encrypted API keys.")
            logger.warning(f"MASTER_KEY: {key.decode()}")
            logger.warning("=" * 80)

        return Fernet(key)

    def _load_settings(self) -> AppSettings:
        """Loads settings from the JSON file.

        If the file doesn't exist, it creates a default configuration with a
        default 'admin' user and password. It also handles potential errors
        during file parsing and validation, falling back to default settings.

        Returns:
            An instance of AppSettings with the loaded configuration.
        """
        if not self.config_path.exists():
            logger.info(
                f"Config file not found at {self.config_path}. Creating a default one."
            )
            DATA_DIR.mkdir(exist_ok=True)
            # Set a default password for the first run
            default_password = "admin"
            hashed_password = bcrypt.hashpw(
                default_password.encode("utf-8"), bcrypt.gensalt()
            )
            default_settings = AppSettings(password_hash=hashed_password)
            self.save_settings(default_settings)
            logger.info("Default username 'admin' with password 'admin' has been set.")
            return default_settings

        try:
            with open(self.config_path, "r") as f:
                data = json.load(f)
                # Pydantic doesn't handle bytes from JSON, so we need to decode them if they exist
                if data.get("password_hash"):
                    data["password_hash"] = data["password_hash"].encode("latin1")
                if data.get("binance", {}).get("api_key_encrypted"):
                    data["binance"]["api_key_encrypted"] = data["binance"][
                        "api_key_encrypted"
                    ].encode("latin1")
                if data.get("binance", {}).get("secret_key_encrypted"):
                    data["binance"]["secret_key_encrypted"] = data["binance"][
                        "secret_key_encrypted"
                    ].encode("latin1")
                if data.get("cmc", {}).get("api_key_encrypted"):
                    data["cmc"]["api_key_encrypted"] = data["cmc"][
                        "api_key_encrypted"
                    ].encode("latin1")

                return AppSettings.parse_obj(data)
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            logger.error(f"Failed to load or validate config file: {e}", exc_info=True)
            logger.error(
                "Please check the format of config.json or delete it to generate a new default."
            )
            # Fallback to default settings on error
            return AppSettings()

    def save_settings(self, settings: AppSettings):
        """Encrypts sensitive fields and saves the settings to the JSON file.

        Before saving, this method checks for any plaintext API keys provided
        in the settings model, encrypts them, and clears the plaintext versions.
        It then serializes the settings to JSON, handling byte encoding,
        and updates the in-memory settings.

        Args:
            settings: The AppSettings object to save.
        """
        # Encrypt API keys if they are provided
        if settings.binance.api_key:
            settings.binance.api_key_encrypted = self.encrypt(settings.binance.api_key)
        if settings.binance.secret_key:
            settings.binance.secret_key_encrypted = self.encrypt(
                settings.binance.secret_key
            )
        if settings.cmc.api_key:
            settings.cmc.api_key_encrypted = self.encrypt(settings.cmc.api_key)

        # Create a serializable dictionary, excluding plain text keys
        # and encoding bytes to strings for JSON
        data_to_save = settings.dict(
            exclude={"binance": {"api_key", "secret_key"}, "cmc": {"api_key"}}
        )

        # Convert bytes to a string representation for JSON serialization
        if data_to_save.get("password_hash"):
            data_to_save["password_hash"] = data_to_save["password_hash"].decode(
                "latin1"
            )
        if data_to_save.get("binance", {}).get("api_key_encrypted"):
            data_to_save["binance"]["api_key_encrypted"] = data_to_save["binance"][
                "api_key_encrypted"
            ].decode("latin1")
        if data_to_save.get("binance", {}).get("secret_key_encrypted"):
            data_to_save["binance"]["secret_key_encrypted"] = data_to_save["binance"][
                "secret_key_encrypted"
            ].decode("latin1")
        if data_to_save.get("cmc", {}).get("api_key_encrypted"):
            data_to_save["cmc"]["api_key_encrypted"] = data_to_save["cmc"][
                "api_key_encrypted"
            ].decode("latin1")

        with open(self.config_path, "w") as f:
            json.dump(data_to_save, f, indent=4)

        # Update the in-memory settings
        self.settings = settings

    def get_settings(self) -> AppSettings:
        """Returns the current, in-memory application settings.

        Returns:
            The current AppSettings instance.
        """
        return self.settings

    def encrypt(self, plain_text: str) -> bytes:
        """Encrypts a string using the Fernet instance.

        Args:
            plain_text: The string to encrypt.

        Returns:
            The encrypted ciphertext as bytes.
        """
        return self.fernet.encrypt(plain_text.encode())

    def decrypt(self, cipher_text: bytes) -> str:
        """Decrypts a byte string using the Fernet instance.

        Handles cases where decryption fails (e.g., wrong key) gracefully.

        Args:
            cipher_text: The encrypted bytes to decrypt.

        Returns:
            The decrypted plaintext string, or an empty string if decryption fails.
        """
        if not cipher_text:
            return ""
        try:
            return self.fernet.decrypt(cipher_text).decode()
        except InvalidToken:
            logger.error(
                "Failed to decrypt data. The MASTER_KEY may have changed.",
                exc_info=True,
            )
            return ""


# --- Singleton Instance ---
# This makes it easy to access the config manager from anywhere in the app.
config_manager = ConfigManager()


def get_config_manager() -> ConfigManager:
    """Returns the singleton instance of the ConfigManager.

    This function is intended for use as a FastAPI dependency.
    """
    return config_manager


def get_settings() -> AppSettings:
    """Returns the settings from the singleton ConfigManager instance.

    This function is intended for use as a FastAPI dependency.
    """
    return config_manager.get_settings()
