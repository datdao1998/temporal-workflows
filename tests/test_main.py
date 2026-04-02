"""Unit tests for the FastAPI app entry point."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app, lifespan


class TestAppSetup:
    """Tests for app configuration."""

    def test_app_title(self):
        assert app.title == "PDF Extraction Service"

    def test_router_included(self):
        paths = [route.path for route in app.routes]
        assert "/jobs" in paths
        assert "/jobs/{job_id}" in paths


class TestLifespan:
    """Tests for the startup/shutdown lifecycle."""

    @pytest.mark.asyncio
    async def test_lifespan_initializes_database(self):
        """Database engine is initialized during startup."""
        with patch("src.main.init_db") as mock_init, \
             patch("src.main.Client") as mock_client_cls:
            mock_client_cls.connect = AsyncMock(side_effect=Exception("no temporal"))
            async with lifespan(app):
                mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_connects_temporal_client(self):
        """Temporal client connection is attempted during startup."""
        mock_client = AsyncMock()
        with patch("src.main.init_db"), \
             patch("src.main.Client") as mock_client_cls:
            mock_client_cls.connect = AsyncMock(return_value=mock_client)
            async with lifespan(app):
                mock_client_cls.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifespan_temporal_failure_non_fatal(self):
        """App starts even if Temporal is unavailable."""
        with patch("src.main.init_db"), \
             patch("src.main.Client") as mock_client_cls:
            mock_client_cls.connect = AsyncMock(side_effect=ConnectionError("refused"))
            async with lifespan(app):
                pass  # Should not raise

    @pytest.mark.asyncio
    async def test_lifespan_clears_temporal_on_shutdown(self):
        """Temporal client is cleared on shutdown."""
        import src.main as main_module

        with patch("src.main.init_db"), \
             patch("src.main.Client") as mock_client_cls:
            mock_client_cls.connect = AsyncMock(return_value=AsyncMock())
            async with lifespan(app):
                assert main_module._temporal_client is not None
            assert main_module._temporal_client is None


class TestGetTemporalClient:
    @pytest.mark.asyncio
    async def test_returns_none_before_startup(self):
        import src.main as main_module
        main_module._temporal_client = None
        from src.main import get_temporal_client
        result = await get_temporal_client()
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_client_after_startup(self):
        import src.main as main_module
        sentinel = AsyncMock()
        main_module._temporal_client = sentinel
        from src.main import get_temporal_client
        result = await get_temporal_client()
        assert result is sentinel
        main_module._temporal_client = None
