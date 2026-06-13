"""Unit tests for AccountCredentialStore — uses mocked keyring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.imap.credential_store import SERVICE_NAME, AccountCredentialStore


class TestAccountCredentialStore:
    """Test suite for credential storage via keyring."""

    def setup_method(self) -> None:
        self.store = AccountCredentialStore()
        self.account_id = "test-account-123"

    # ── OAuth token storage ───────────────────────────────────────────

    @patch("app.services.imap.credential_store.keyring")
    def test_store_oauth_tokens(self, mock_keyring: MagicMock) -> None:
        """Store OAuth tokens should call keyring.set_password with JSON."""
        tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
        }

        self.store.store_oauth_tokens(self.account_id, tokens)

        mock_keyring.set_password.assert_called_once()
        call_args = mock_keyring.set_password.call_args
        assert call_args[0][0] == SERVICE_NAME
        assert call_args[0][1] == f"oauth:{self.account_id}"
        # The third arg should be JSON
        import json

        stored_data = json.loads(call_args[0][2])
        assert stored_data["access_token"] == "test_access_token"
        assert stored_data["refresh_token"] == "test_refresh_token"

    @patch("app.services.imap.credential_store.keyring")
    def test_get_oauth_tokens(self, mock_keyring: MagicMock) -> None:
        """Get OAuth tokens should parse JSON from keyring."""
        import json

        mock_keyring.get_password.return_value = json.dumps(
            {"access_token": "abc", "refresh_token": "def"}
        )

        result = self.store.get_oauth_tokens(self.account_id)

        assert result is not None
        assert result["access_token"] == "abc"
        assert result["refresh_token"] == "def"
        mock_keyring.get_password.assert_called_once_with(
            SERVICE_NAME, f"oauth:{self.account_id}"
        )

    @patch("app.services.imap.credential_store.keyring")
    def test_get_oauth_tokens_not_found(self, mock_keyring: MagicMock) -> None:
        """Get OAuth tokens returns None when no data stored."""
        mock_keyring.get_password.return_value = None

        result = self.store.get_oauth_tokens(self.account_id)
        assert result is None

    @patch("app.services.imap.credential_store.keyring")
    def test_get_oauth_tokens_corrupted(self, mock_keyring: MagicMock) -> None:
        """Get OAuth tokens returns None when stored data is corrupted JSON."""
        mock_keyring.get_password.return_value = "not-valid-json{{"

        result = self.store.get_oauth_tokens(self.account_id)
        assert result is None

    # ── Password storage ──────────────────────────────────────────────

    @patch("app.services.imap.credential_store.keyring")
    def test_store_password(self, mock_keyring: MagicMock) -> None:
        """Store password should call keyring.set_password."""
        self.store.store_password(self.account_id, "my_secret_password")

        mock_keyring.set_password.assert_called_once_with(
            SERVICE_NAME, f"password:{self.account_id}", "my_secret_password"
        )

    @patch("app.services.imap.credential_store.keyring")
    def test_get_password(self, mock_keyring: MagicMock) -> None:
        """Get password should return the stored password."""
        mock_keyring.get_password.return_value = "stored_password"

        result = self.store.get_password(self.account_id)
        assert result == "stored_password"

    @patch("app.services.imap.credential_store.keyring")
    def test_get_password_not_found(self, mock_keyring: MagicMock) -> None:
        """Get password returns None when not stored."""
        mock_keyring.get_password.return_value = None

        result = self.store.get_password(self.account_id)
        assert result is None

    # ── Credential deletion ───────────────────────────────────────────

    @patch("app.services.imap.credential_store.keyring")
    def test_delete_credentials(self, mock_keyring: MagicMock) -> None:
        """Delete credentials should remove both oauth and password entries."""
        self.store.delete_credentials(self.account_id)

        assert mock_keyring.delete_password.call_count == 2
        calls = mock_keyring.delete_password.call_args_list
        keys = {c[0][1] for c in calls}
        assert f"oauth:{self.account_id}" in keys
        assert f"password:{self.account_id}" in keys

    @patch("app.services.imap.credential_store.keyring")
    def test_delete_credentials_not_found(self, mock_keyring: MagicMock) -> None:
        """Delete credentials should not crash when keys don't exist."""
        import keyring as kr

        mock_keyring.delete_password.side_effect = kr.errors.PasswordDeleteError
        mock_keyring.errors = kr.errors

        # Should not raise
        self.store.delete_credentials(self.account_id)
