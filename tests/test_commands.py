import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from nanobot.cli.commands import app

runner = CliRunner()


def _mock_sunday_auth():
    """Return context managers that mock the Sunday auth flow for onboard tests."""
    mock_token_resp = MagicMock()
    mock_token_resp.access = "mock_access"
    mock_token_resp.refresh = "mock_refresh"
    mock_token_resp.user.email = "test@example.com"

    mock_client = MagicMock()
    mock_client.get_encryption_meta = AsyncMock(
        return_value=MagicMock(salt=None, verifier=None),
    )
    mock_client.list_identities = AsyncMock(return_value=[])
    mock_client.close = AsyncMock()

    return (
        patch("nanobot.cli.commands.device_code_flow", new_callable=AsyncMock, return_value=mock_token_resp),
        patch("nanobot.cli.commands.SundayClient", return_value=mock_client),
        patch("nanobot.cli.commands.generate_identity_md", new_callable=AsyncMock),
        patch("nanobot.cli.commands.CryptoBox"),
    )


@pytest.fixture
def mock_paths():
    """Mock config/workspace paths and Sunday auth for test isolation."""
    sunday_patches = _mock_sunday_auth()

    with patch("nanobot.config.loader.get_config_path") as mock_cp, \
         patch("nanobot.config.loader.save_config") as mock_sc, \
         patch("nanobot.config.loader.load_config") as mock_lc, \
         patch("nanobot.utils.helpers.get_workspace_path") as mock_ws, \
         sunday_patches[0], sunday_patches[1], sunday_patches[2], sunday_patches[3]:

        base_dir = Path("./test_onboard_data")
        if base_dir.exists():
            shutil.rmtree(base_dir)
        base_dir.mkdir()

        config_file = base_dir / "config.json"
        workspace_dir = base_dir / "workspace"

        mock_cp.return_value = config_file
        mock_ws.return_value = workspace_dir
        mock_sc.side_effect = lambda config: config_file.write_text("{}")

        yield config_file, workspace_dir

        if base_dir.exists():
            shutil.rmtree(base_dir)


def test_onboard_fresh_install(mock_paths):
    """No existing config — should create from scratch."""
    config_file, workspace_dir = mock_paths

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0
    assert "Created config" in result.stdout
    assert "Created workspace" in result.stdout
    assert "SundayAgent is ready" in result.stdout
    assert config_file.exists()
    assert (workspace_dir / "AGENTS.md").exists()
    assert (workspace_dir / "memory" / "MEMORY.md").exists()


def test_onboard_existing_config_refresh(mock_paths):
    """Config exists, user declines overwrite — should refresh (load-merge-save)."""
    config_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard"], input="n\n")

    assert result.exit_code == 0
    assert "Config already exists" in result.stdout
    assert "existing values preserved" in result.stdout
    assert workspace_dir.exists()
    assert (workspace_dir / "AGENTS.md").exists()


def test_onboard_existing_config_overwrite(mock_paths):
    """Config exists, user confirms overwrite — should reset to defaults."""
    config_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard"], input="y\n")

    assert result.exit_code == 0
    assert "Config already exists" in result.stdout
    assert "Config reset to defaults" in result.stdout
    assert workspace_dir.exists()


def test_onboard_existing_workspace_safe_create(mock_paths):
    """Workspace exists — should not recreate, but still add missing templates."""
    config_file, workspace_dir = mock_paths
    workspace_dir.mkdir(parents=True)
    config_file.write_text("{}")

    result = runner.invoke(app, ["onboard"], input="n\n")

    assert result.exit_code == 0
    assert "Created workspace" not in result.stdout
    assert "Created AGENTS.md" in result.stdout
    assert (workspace_dir / "AGENTS.md").exists()
