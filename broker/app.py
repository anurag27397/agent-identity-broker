from fastapi import FastAPI
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    keycloak_url: str = "http://keycloak:8080"
    keycloak_realm: str = "agent-broker"
    keycloak_client_id: str = "broker"
    keycloak_client_secret: str = "broker-secret-change-me"
    log_level: str = "INFO"


settings = Settings()

app = FastAPI(
    title="Agent Identity Broker",
    version="0.1.0",
    description="Identity governance for AI agents",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "agent-identity-broker",
        "version": "0.1.0",
        "docs": "/docs",
    }
