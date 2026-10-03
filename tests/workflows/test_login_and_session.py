import pytest
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.workflow
@pytest.mark.django_db
class TestLoginAndSessionLifecycleWorkflow:
    """
    End-to-End User Authentication & Token Lifecycle Workflow:
    1. User authenticates with email/password.
    2. Receives access & refresh JWT tokens.
    3. Verifies token validity via token/verify.
    4. Accesses protected /auth/verify endpoint.
    5. Rotates refresh token via token/refresh.
    6. Logs out, blacklisting the refresh token.
    7. Confirms blacklisted token cannot be refreshed or used.
    """
    def test_complete_session_lifecycle(self, api_client, test_user, test_password):
        # 1. Login
        login_resp = api_client.post(
            "/v1/auth/login/",
            {"email": test_user.email, "password": test_password},
            format="json",
        )
        assert login_resp.status_code == status.HTTP_200_OK
        data = login_resp.data.get("data") or login_resp.data
        access_token = data["access"]
        refresh_token = data["refresh"]

        # 2. Verify access token
        verify_resp = api_client.post("/v1/auth/token/verify/", {"token": access_token}, format="json")
        assert verify_resp.status_code == status.HTTP_200_OK

        # 3. Call authenticated endpoint
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        user_resp = api_client.get("/v1/auth/verify/")
        assert user_resp.status_code == status.HTTP_200_OK
        assert user_resp.data["data"]["email"] == test_user.email

        # 4. Refresh token
        refresh_resp = api_client.post("/v1/auth/token/refresh/", {"refresh": refresh_token}, format="json")
        assert refresh_resp.status_code == status.HTTP_200_OK
        new_data = refresh_resp.data.get("data") or refresh_resp.data
        new_access = new_data["access"]
        new_refresh = new_data.get("refresh", refresh_token)

        # 5. Logout
        logout_resp = api_client.post("/v1/auth/logout/", {"refresh": new_refresh}, format="json")
        assert logout_resp.status_code == status.HTTP_200_OK
        assert logout_resp.data["success"] is True

        # 6. Verify blacklisted token is rejected
        blocked_refresh = api_client.post("/v1/auth/token/refresh/", {"refresh": new_refresh}, format="json")
        assert blocked_refresh.status_code == status.HTTP_401_UNAUTHORIZED
