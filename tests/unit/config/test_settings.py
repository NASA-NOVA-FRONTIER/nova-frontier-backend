import pytest
from pydantic import ValidationError

from nisar_hazard_watch.config.settings import Settings, get_settings
from nisar_hazard_watch.constants.assistant import (
    DEFAULT_ASSISTANT_DAILY_TOKEN_LIMIT,
    DEFAULT_ASSISTANT_MODEL,
)
from nisar_hazard_watch.constants.environments import Environment
from nisar_hazard_watch.constants.explorations import RunnerKind
from nisar_hazard_watch.constants.limits import DEFAULT_DAILY_LIMIT_APP, DEFAULT_DAILY_LIMIT_CLIENT
from nisar_hazard_watch.constants.log_levels import LogLevel

LOCAL_ORIGIN = "http://localhost:5173"
VERCEL_ORIGIN = "https://nova-frontier-frontend.vercel.app"
RAILWAY_DATABASE_URL = "postgresql://user:p4ssw0rd-x@postgres.railway.internal:5432/railway"
EXPECTED_ASYNC_URL = "postgresql+asyncpg://user:p4ssw0rd-x@postgres.railway.internal:5432/railway"
SECRET_VALUE = "super-secret-token"
DATABASE_PASSWORD = "p4ssw0rd-x"
RAILWAY_PROXY_HOPS = 2


def test_defaults_describe_a_local_environment() -> None:
    # Arrange
    expected_origins = [LOCAL_ORIGIN]

    # Act
    settings = Settings()

    # Assert
    assert settings.environment is Environment.LOCAL
    assert settings.cors_allowed_origins == expected_origins
    assert settings.earthdata_token is None
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.trusted_proxy_hops == RAILWAY_PROXY_HOPS


def test_database_url_from_the_platform_gets_the_async_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv(name="DATABASE_URL", value=RAILWAY_DATABASE_URL)

    # Act
    settings = Settings()

    # Assert
    assert settings.database_url == EXPECTED_ASYNC_URL


def test_the_database_password_stays_out_of_the_representation_and_the_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv(name="DATABASE_URL", value=RAILWAY_DATABASE_URL)

    # Act
    settings = Settings()

    # Assert
    assert DATABASE_PASSWORD not in repr(settings)
    assert "database_url" not in settings.model_dump()


def test_origins_can_be_a_comma_separated_list(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv(name="CORS_ALLOWED_ORIGINS", value=f"{LOCAL_ORIGIN}, {VERCEL_ORIGIN} ,")

    # Act
    settings = Settings()

    # Assert
    assert settings.cors_allowed_origins == [LOCAL_ORIGIN, VERCEL_ORIGIN]


def test_origins_can_be_a_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv(name="CORS_ALLOWED_ORIGINS", value=f'["{VERCEL_ORIGIN}"]')

    # Act
    settings = Settings()

    # Assert
    assert settings.cors_allowed_origins == [VERCEL_ORIGIN]


@pytest.mark.parametrize(
    argnames="origins",
    argvalues=[
        "https://app.example.com/",
        "app.example.com",
        "https://app.example.com/path",
        "*",
        "",
        "[]",
    ],
)
def test_origins_that_browsers_would_never_match_are_rejected(
    monkeypatch: pytest.MonkeyPatch, origins: str
) -> None:
    # Arrange
    monkeypatch.setenv(name="CORS_ALLOWED_ORIGINS", value=origins)

    # Act / Assert
    with pytest.raises(expected_exception=ValidationError, match="cors_allowed_origins"):
        Settings()


def test_secrets_never_show_up_in_the_representation(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv(name="EARTHDATA_TOKEN", value=SECRET_VALUE)

    # Act
    settings = Settings()

    # Assert
    assert settings.earthdata_token is not None
    assert settings.earthdata_token.get_secret_value() == SECRET_VALUE
    assert SECRET_VALUE not in repr(settings)


@pytest.mark.parametrize(argnames="blank", argvalues=["", "   "])
def test_blank_secrets_count_as_missing(monkeypatch: pytest.MonkeyPatch, blank: str) -> None:
    # Arrange
    monkeypatch.setenv(name="EARTHDATA_TOKEN", value=blank)
    monkeypatch.setenv(name="MODAL_TOKEN_ID", value=blank)
    monkeypatch.setenv(name="FIRMS_MAP_KEY", value=blank)
    monkeypatch.setenv(name="ANTHROPIC_API_KEY", value=blank)

    # Act
    settings = Settings()

    # Assert
    assert settings.earthdata_token is None
    assert settings.modal_token_id is None
    assert settings.firms_map_key is None
    assert settings.anthropic_api_key is None


def test_the_log_level_is_accepted_in_any_case(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv(name="LOG_LEVEL", value="debug")

    # Act
    settings = Settings()

    # Assert
    assert settings.log_level is LogLevel.DEBUG


def test_an_unknown_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv(name="LOG_LEVEL", value="verbose")

    # Act / Assert
    with pytest.raises(expected_exception=ValidationError, match="log_level"):
        Settings()


@pytest.mark.parametrize(
    argnames="name",
    argvalues=[
        "CMR_HEALTH_TIMEOUT_SECONDS",
        "DATABASE_HEALTH_TIMEOUT_SECONDS",
        "HEALTH_PROBE_TIMEOUT_SECONDS",
    ],
)
@pytest.mark.parametrize(argnames="value", argvalues=["0", "-5"])
def test_timeouts_must_be_positive(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    # Arrange
    monkeypatch.setenv(name=name, value=value)

    # Act / Assert
    with pytest.raises(expected_exception=ValidationError):
        Settings()


def test_production_refuses_to_start_on_the_default_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv(name="ENVIRONMENT", value="production")

    # Act / Assert
    with pytest.raises(expected_exception=ValidationError, match="DATABASE_URL must be set"):
        Settings()


def test_production_starts_when_the_database_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv(name="ENVIRONMENT", value="production")
    monkeypatch.setenv(name="DATABASE_URL", value=RAILWAY_DATABASE_URL)

    # Act
    settings = Settings()

    # Assert
    assert settings.environment is Environment.PRODUCTION
    assert settings.database_url == EXPECTED_ASYNC_URL


def test_get_settings_is_cached() -> None:
    # Arrange
    get_settings.cache_clear()

    # Act
    first = get_settings()
    second = get_settings()

    # Assert
    assert first is second


def test_the_synthetic_runner_is_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv(name="ENVIRONMENT", value="production")
    monkeypatch.setenv(name="DATABASE_URL", value=RAILWAY_DATABASE_URL)
    monkeypatch.setenv(name="RUNNER", value="inProcess")

    # Act / Assert
    with pytest.raises(expected_exception=ValidationError, match="synthetic"):
        Settings()


def test_exploration_settings_default_to_the_gateway_and_the_agreed_limits() -> None:
    # Arrange
    expected_deadline = 480.0
    expected_eta_prior = 140.0

    # Act
    settings = Settings()

    # Assert
    assert settings.runner is RunnerKind.GATEWAY
    assert settings.exploration_deadline_seconds == expected_deadline
    assert settings.eta_prior_seconds == expected_eta_prior
    assert settings.max_active_explorations == 5
    assert settings.ml_gateway_url.startswith("https://")


@pytest.mark.parametrize(
    argnames="name",
    argvalues=["EXPLORATION_DEADLINE_SECONDS", "ASF_TIMEOUT_SECONDS", "RATE_LIMIT_PER_MINUTE"],
)
def test_exploration_limits_must_be_positive(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    # Arrange
    monkeypatch.setenv(name=name, value="0")

    # Act / Assert
    with pytest.raises(expected_exception=ValidationError):
        Settings()


def test_the_firms_key_is_a_secret_and_the_service_defaults_to_nasa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv(name="FIRMS_MAP_KEY", value=SECRET_VALUE)

    # Act
    settings = Settings()

    # Assert
    assert settings.firms_map_key is not None
    assert settings.firms_map_key.get_secret_value() == SECRET_VALUE
    assert SECRET_VALUE not in repr(settings)
    assert settings.firms_url == "https://firms.modaps.eosdis.nasa.gov"


def test_the_anthropic_key_is_a_secret_and_the_model_is_a_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    monkeypatch.setenv(name="ANTHROPIC_API_KEY", value=SECRET_VALUE)
    monkeypatch.setenv(name="ASSISTANT_MODEL", value="claude-sonnet-5-5")

    # Act
    settings = Settings()

    # Assert
    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == SECRET_VALUE
    assert SECRET_VALUE not in repr(settings)
    assert settings.assistant_model == "claude-sonnet-5-5"


def test_the_assistant_defaults_to_opus_with_a_tight_limit_and_a_daily_ceiling() -> None:
    # Act
    settings = Settings()

    # Assert
    assert settings.anthropic_api_key is None
    assert settings.assistant_model == DEFAULT_ASSISTANT_MODEL
    assert settings.assistant_rate_limit_per_minute < settings.rate_limit_per_minute
    assert settings.assistant_daily_token_limit == DEFAULT_ASSISTANT_DAILY_TOKEN_LIMIT


def test_daily_limits_default_to_the_documented_values_and_can_be_set_by_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    defaults = Settings()
    monkeypatch.setenv("DAILY_LIMIT_APP", "40")
    monkeypatch.setenv("DAILY_LIMIT_CLIENT", "3")

    # Act
    configured = Settings()

    # Assert
    assert (defaults.daily_limit_app, defaults.daily_limit_client) == (
        DEFAULT_DAILY_LIMIT_APP,
        DEFAULT_DAILY_LIMIT_CLIENT,
    )
    assert (configured.daily_limit_app, configured.daily_limit_client) == (40, 3)


def test_the_gateway_shared_secret_is_optional_hidden_and_blank_means_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    unset = Settings()
    monkeypatch.setenv("GATEWAY_SHARED_SECRET", "   ")
    blank = Settings()
    monkeypatch.setenv("GATEWAY_SHARED_SECRET", SECRET_VALUE)

    # Act
    configured = Settings()

    # Assert
    assert unset.gateway_shared_secret is None
    assert blank.gateway_shared_secret is None
    assert configured.gateway_shared_secret is not None
    assert configured.gateway_shared_secret.get_secret_value() == SECRET_VALUE
    assert SECRET_VALUE not in repr(configured)
