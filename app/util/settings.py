import json
import logging
import os
import re
import subprocess
from typing import Optional

import yaml
from pydantic import BaseModel, SecretStr, constr
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def BitwardenConfig(settings: dict):
    """
    Takes a dict of settings loaded from yaml and adds the secrets from bitwarden to the settings dict.
    The bitwarden secrets are mapped to the settings dict using the bitwarden_mapping dict.
    The secrets are sourced based on a project id in the settings dict.
    """
    logger.debug("Loading secrets from Bitwarden")
    try:
        project_id = settings["bws"]["project_id"]
        if bool(re.search("[^a-z0-9-]", project_id)):
            raise ValueError("Invalid project id")
        command = ["bws", "secret", "list", project_id, "--output", "json"]
        env_vars = os.environ.copy()
        bitwarden_raw = subprocess.run(
            command, text=True, env=env_vars, capture_output=True
        ).stdout
    except Exception as e:
        logger.exception(e)
        raise e
    bitwarden_settings = parse_json_to_dict(bitwarden_raw)

    bitwarden_mapping = {
        "discord_bot_token": ("discord", "bot_token"),
        "discord_client_id": ("discord", "client_id"),
        "discord_secret": ("discord", "secret"),
        "stripe_api_key": ("stripe", "api_key"),
        "stripe_webhook_secret": ("stripe", "webhook_secret"),
        "stripe_price_id": ("stripe", "price_id"),
        "email_password": ("email", "password"),
        "jwt_secret": ("jwt", "secret"),
        "infra_wifi": ("infra", "wifi"),
        "infra_application_credential_id": ("infra", "application_credential_id"),
        "infra_configuration_credential_secret": (
            "infra",
            "application_credential_secret",
        ),
    }

    bitwarden_mapped = {}
    for bw_key, nested_keys in bitwarden_mapping.items():
        if bw_key in bitwarden_settings:
            top_key, nested_key = nested_keys
            if top_key not in bitwarden_mapped:
                bitwarden_mapped[top_key] = {}
            bitwarden_mapped[top_key][nested_key] = bitwarden_settings[bw_key]

    for top_key, nested_dict in bitwarden_mapped.items():
        if top_key in settings:
            for nested_key, value in nested_dict.items():
                settings[top_key][nested_key] = value
    return settings


settings = dict()

# Reads config from ../config/options.yml
# here = os.path.abspath(os.path.dirname(__file__))
with open("config.yml") as f:
    settings.update(yaml.load(f, Loader=yaml.FullLoader))


def parse_json_to_dict(json_string):
    data = json.loads(json_string)
    return {item["key"]: item["value"] for item in data}


# If bitwarden is enabled, add secrets to settings
if settings.get("bws").get("enable"):
    settings = BitwardenConfig(settings)

logger.debug("Final settings: %s", settings)


class DiscordConfig(BaseModel):
    """
    Represents the configuration settings for Discord integration.

    Attributes:
        bot_token (SecretStr): The secret token for the Discord bot.
        client_id (int): The client ID for the Discord application.
        guild_id (int): The ID of the HackUCF discord server.
        member_role (int): The ID of the role assigned to members.
        redirect_base (str): The base URL for redirecting after authentication.
        scope (str): The scope of permissions required for the Discord integration.
        secret (SecretStr): The secret key for the Discord oauth.
    """

    bot_token: SecretStr
    client_id: int
    guild_id: int
    member_role: int
    redirect_base: str
    scope: str
    secret: SecretStr
    enable: Optional[bool] = True


if settings.get('discord'):
    discord_config = DiscordConfig(**settings["discord"])
else:
    logger.warn("Missing discord config")


class StripeConfig(BaseModel):
    """
    Configuration class for Stripe integration.

    Attributes:
        api_key (SecretStr): The API key for Stripe.
        webhook_secret (SecretStr): The webhook secret for Stripe.
        price_id (str): The ID of the price for the product.
        url_success (str): The URL to redirect to on successful payment.
        url_failure (str): The URL to redirect to on failed payment.
    """

    api_key: SecretStr
    webhook_secret: SecretStr
    price_id: str
    url_success: str
    url_failure: str
    pause_payments: bool


stripe_config = StripeConfig(**settings["stripe"])


class EmailConfig(BaseModel):
    """
    Represents the configuration for an email.

    Attributes:
        smtp_server (str): The SMTP server address.
        email (str): The email address to send from also used as the login username.
        password (SecretStr): The password for the email account.
    """

    smtp_server: str
    email: str
    password: SecretStr
    enable: Optional[bool] = True


email_config = EmailConfig(**settings["email"])


class JwtConfig(BaseModel):
    """
    Configuration class for JWT (JSON Web Token) settings.

    Attributes:
        secret (SecretStr): The secret key used for signing and verifying JWTs.(min_length=32)
        algorithm (str): The algorithm used for JWT encryption.
        lifetime_user (int): The lifetime (in seconds) of a user JWT.
        lifetime_sudo (int): The lifetime (in seconds) of a sudo JWT.
    """

    secret: SecretStr = constr(min_length=32)
    algorithm: str
    lifetime_user: int
    lifetime_sudo: int


jwt_config = JwtConfig(**settings["jwt"])


class InfraConfig(BaseModel):
    """
    Represents the infrastructure configuration.

    Attributes:
        wifi (str): The WiFi password used in welcome messages.
        horizon (str): The url of the openstack horizon interface (also used to derive the keystone endpoint).
    """

    wifi: str
    horizon: str


infra_config = InfraConfig(**settings["infra"])


class KeycloakConfig(BaseModel):
    username: str
    password: SecretStr
    url: str
    relam: str


if settings.get('keycloak'):
    keycloak_config = KeycloakConfig(**settings["keycloak"])
else:
    keycloak_config = None
    logger.warn("Missing Keycloak Config")


class TelemetryConfig(BaseModel):
    url: Optional[str] = None
    enable: Optional[bool] = False
    env: Optional[str] = "dev"


telemetry_config = TelemetryConfig(**settings["telemetry"])


class DatabaseConfig(BaseModel):
    url: str


if settings.get('database'):
    database_config = DatabaseConfig(**settings["database"])
else:
    database_config = None
    logger.warn("Missing database config")


class RedisConfig(BaseModel):
    host: str
    port: int
    db: int

if settings.get('redis'):
    redis_config = RedisConfig(**settings["redis"])
else:
    redis_config = None
    logger.warn("Missing redis config")


class HttpConfig(BaseModel):
    domain: str


http_config = HttpConfig(**settings["http"])


class SingletonBaseSettingsMeta(type(BaseSettings), type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class Settings(BaseSettings, metaclass=SingletonBaseSettingsMeta):
    discord: DiscordConfig = discord_config
    stripe: StripeConfig = stripe_config
    email: EmailConfig = email_config
    jwt: JwtConfig = jwt_config
    database: DatabaseConfig = database_config or DatabaseConfig(url="sqlite:///:memory:")
    infra: InfraConfig = infra_config
    redis: RedisConfig = redis_config or RedisConfig(host="localhost", db=0, port=6379)
    http: HttpConfig = http_config
    keycloak: Optional[KeycloakConfig] = keycloak_config
    telemetry: Optional[TelemetryConfig] = telemetry_config
