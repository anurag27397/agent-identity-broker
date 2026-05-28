from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    keycloak_realm: str = "agent-broker"
    keycloak_client_id: str = "broker"
    keycloak_client_secret: str = "broker-secret-change-me"

    keycloak_public_url: str = "http://localhost:8080"
    keycloak_internal_url: str = "http://keycloak:8080"

    broker_public_url: str = "http://localhost:8001"

    session_secret: str = "dev-session-secret-change-me"
    session_token_ttl_seconds: int = 3600
    scoped_token_ttl_seconds: int = 60

    keys_dir: str = "/app/keys"

    log_level: str = "INFO"

    @property
    def issuer(self) -> str:
        return f"{self.keycloak_public_url}/realms/{self.keycloak_realm}"

    @property
    def authorization_endpoint(self) -> str:
        return f"{self.keycloak_public_url}/realms/{self.keycloak_realm}/protocol/openid-connect/auth"

    @property
    def token_endpoint(self) -> str:
        return f"{self.keycloak_internal_url}/realms/{self.keycloak_realm}/protocol/openid-connect/token"

    @property
    def jwks_uri(self) -> str:
        return f"{self.keycloak_internal_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"

    @property
    def redirect_uri(self) -> str:
        return f"{self.broker_public_url}/auth/callback"


settings = Settings()
