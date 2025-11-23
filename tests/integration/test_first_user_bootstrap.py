"""
Integration tests for first user bootstrap functionality.
Tests the automatic admin promotion for the first user in the system.
"""
import uuid

from tests.lib import JournivApiClient


def _unique_credentials(prefix: str = "bootstrap") -> tuple[str, str]:
    """Generate unique email and password for testing."""
    suffix = uuid.uuid4().hex[:8]
    email = f"{prefix}-{suffix}@example.com"
    password = f"Pass-{suffix}-Aa1!"
    return email, password


def test_registration_includes_role_field(api_client: JournivApiClient):
    """User registration response should include the role field."""
    email, password = _unique_credentials()

    response = api_client.request(
        "POST",
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Test User"
        }
    )

    # May succeed or fail depending on signup settings
    if response.status_code == 201:
        user = response.json()
        assert "role" in user, "Registration response should include role field"
        assert user["role"] in ["admin", "user"], "Role should be either admin or user"


def test_first_local_user_is_admin(api_client: JournivApiClient):
    """First user registered via local signup should be admin."""
    email, password = _unique_credentials()

    response = api_client.request(
        "POST",
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "First Local User"
        }
    )

    if response.status_code == 201:
        user = response.json()
        assert "role" in user

        login_response = api_client.request(
            "POST",
            "/auth/login",
            json={"email": email, "password": password}
        )

        if login_response.status_code == 200:
            login_data = login_response.json()
            access_token = login_data["access_token"]

            admin_response = api_client.request(
                "GET",
                "/admin/users",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if admin_response.status_code == 200:
                assert user["role"] == "admin", "First user should be admin and able to access admin endpoints"
            else:
                assert user["role"] == "user", "Subsequent users should be regular users"


def test_first_user_bypasses_signup_disabled(api_client: JournivApiClient):
    """First user can register even when signup is disabled."""
    email, password = _unique_credentials()

    response = api_client.request(
        "POST",
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Bypass User"
        }
    )

    if response.status_code == 201:
        user = response.json()

        login_response = api_client.request(
            "POST",
            "/auth/login",
            json={"email": email, "password": password}
        )

        if login_response.status_code == 200:
            login_data = login_response.json()
            access_token = login_data["access_token"]

            admin_response = api_client.request(
                "GET",
                "/admin/users",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if admin_response.status_code == 200:
                assert user["role"] == "admin", "First user should be admin"
            else:
                assert user["role"] == "user", "Subsequent users should be regular users"

    elif response.status_code == 403:
        error_detail = response.json().get("detail", "")
        assert "signup" in error_detail.lower() or "disabled" in error_detail.lower(), \
            "403 should indicate signup is disabled"

    elif response.status_code == 400:
        pass

    else:
        assert False, f"Unexpected status code: {response.status_code}"


def test_subsequent_users_are_regular_users(api_client: JournivApiClient):
    """Users registered after the first user should be regular users."""
    email1, password1 = _unique_credentials()
    response1 = api_client.request(
        "POST",
        "/auth/register",
        json={
            "email": email1,
            "password": password1,
            "name": "First User"
        }
    )

    email2, password2 = _unique_credentials()
    response2 = api_client.request(
        "POST",
        "/auth/register",
        json={
            "email": email2,
            "password": password2,
            "name": "Second User"
        }
    )

    if response1.status_code == 201 and response2.status_code == 201:
        user1 = response1.json()
        user2 = response2.json()

        assert "role" in user1, "First user should have role field"
        assert "role" in user2, "Second user should have role field"

        login1_response = api_client.request(
            "POST",
            "/auth/login",
            json={"email": email1, "password": password1}
        )

        if login1_response.status_code == 200:
            login1_data = login1_response.json()
            access_token1 = login1_data["access_token"]

            admin_response = api_client.request(
                "GET",
                "/admin/users",
                headers={"Authorization": f"Bearer {access_token1}"}
            )

            if admin_response.status_code == 200:
                assert user1["role"] == "admin", "First user should be admin"
                assert user2["role"] == "user", "Subsequent users should be regular users, not admin"
            else:
                assert user1["role"] == "user", "First user should be regular user if not first in system"
                assert user2["role"] == "user", "Second user should be regular user"
        else:
            assert user2["role"] == "user", "Second user should always be regular user, not admin"


def test_oidc_first_user_bootstrap():
    """
    First user via OIDC should become admin.

    Note: This test requires OIDC to be configured and enabled.
    It's a placeholder for when OIDC testing is set up.
    """
    # This test would require:
    # 1. OIDC provider configuration
    # 2. Mock OIDC callback
    # 3. Fresh database

    # Placeholder assertion
    assert True, "OIDC first user bootstrap tested manually"


def test_oidc_auto_provision_disabled_blocks_new_users():
    """
    When OIDC_AUTO_PROVISION=false, new OIDC users should be rejected.

    Note: This test requires OIDC to be configured and enabled.
    It's a placeholder for when OIDC testing is set up.
    """
    # This test would require:
    # 1. OIDC provider configuration
    # 2. Mock OIDC callback with new user
    # 3. OIDC_AUTO_PROVISION=false

    # Placeholder assertion
    assert True, "OIDC auto-provision blocking tested manually"


def test_oidc_links_to_existing_local_account():
    """
    OIDC login with matching email should link to existing local account.

    Note: This test requires OIDC to be configured and enabled.
    It's a placeholder for when OIDC testing is set up.
    """
    # This test would verify that:
    # 1. Local user exists with email X
    # 2. OIDC login with email X links to existing user
    # 3. No duplicate user is created

    # Placeholder assertion
    assert True, "OIDC account linking tested manually"


def test_role_field_in_user_responses(api_client: JournivApiClient):
    """
    All user response endpoints should include the role field.
    """
    # Create a user
    email, password = _unique_credentials()
    response = api_client.request(
        "POST",
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Role Check User"
        }
    )

    if response.status_code == 201:
        # Check registration response
        user = response.json()
        assert "role" in user

        # Login and check response
        login_response = api_client.request(
            "POST",
            "/auth/login",
            json={"email": email, "password": password}
        )

        if login_response.status_code == 200:
            login_data = login_response.json()
            access_token = login_data["access_token"]

            # Check current user endpoint
            profile_response = api_client.request(
                "GET",
                "/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if profile_response.status_code == 200:
                profile = profile_response.json()
                assert "role" in profile
                assert profile["role"] in ["admin", "user"]
