"""Tests for centralized configuration module."""

import pytest

from garmin_mcp.config import (
    DEFAULT_DB_NAME,
    DEFAULT_MAX_OUTPUT_SIZE,
    GarminConfig,
    get_config,
)


class TestGarminConfig:
    """Tests for GarminConfig dataclass."""

    @pytest.mark.unit
    def test_from_env_creates_config(self):
        config = GarminConfig.from_env()
        assert config.data_dir is not None
        assert config.result_dir is not None
        assert config.db_path is not None
        assert config.max_output_size == DEFAULT_MAX_OUTPUT_SIZE

    @pytest.mark.unit
    def test_default_max_output_size(self):
        assert DEFAULT_MAX_OUTPUT_SIZE == 10240

    @pytest.mark.unit
    def test_config_is_frozen(self, tmp_path):
        config = GarminConfig(
            data_dir=tmp_path,
            result_dir=tmp_path,
            db_path=tmp_path / DEFAULT_DB_NAME,
        )
        with pytest.raises(AttributeError):
            config.max_output_size = 999  # type: ignore[misc]

    @pytest.mark.unit
    def test_validate_missing_dirs(self, tmp_path):
        config = GarminConfig(
            data_dir=tmp_path / "nonexistent",
            result_dir=tmp_path,
            db_path=tmp_path / "nonexistent" / DEFAULT_DB_NAME,
        )
        warnings = config.validate()
        assert len(warnings) >= 1
        assert "does not exist" in warnings[0]

    @pytest.mark.unit
    def test_validate_invalid_max_output_size(self, tmp_path):
        config = GarminConfig(
            data_dir=tmp_path,
            result_dir=tmp_path,
            db_path=tmp_path / DEFAULT_DB_NAME,
            max_output_size=-1,
        )
        warnings = config.validate()
        assert any("max_output_size" in w for w in warnings)

    @pytest.mark.unit
    def test_validate_all_ok(self, tmp_path):
        db_dir = tmp_path / "database"
        db_dir.mkdir()
        config = GarminConfig(
            data_dir=tmp_path,
            result_dir=tmp_path,
            db_path=db_dir / DEFAULT_DB_NAME,
        )
        warnings = config.validate()
        assert warnings == []

    @pytest.mark.unit
    def test_custom_credentials(self, tmp_path):
        config = GarminConfig(
            data_dir=tmp_path,
            result_dir=tmp_path,
            db_path=tmp_path / DEFAULT_DB_NAME,
            garmin_email="test@example.com",
            garmin_password="secret",
        )
        assert config.garmin_email == "test@example.com"
        assert config.garmin_password == "secret"


class TestGetConfig:
    """Tests for get_config singleton."""

    @pytest.mark.unit
    def test_returns_config_instance(self):
        # Clear cache for test isolation
        get_config.cache_clear()
        config = get_config()
        assert isinstance(config, GarminConfig)

    @pytest.mark.unit
    def test_returns_same_instance(self):
        get_config.cache_clear()
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    @pytest.mark.unit
    def test_db_path_ends_with_duckdb(self):
        get_config.cache_clear()
        config = get_config()
        assert str(config.db_path).endswith(".duckdb")
