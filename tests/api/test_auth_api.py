import pytest
from rest_framework import status
from django.contrib.auth import get_user_model

from otp.services import OTPService
from otp.choices import OtpPurpose

User = get_user_model()


@pytest.mark.api
@pytest.mark.django_db
class TestAuthenticationAPI:
    # ----------------------------------------------------------------------
    # Registration Tests
    # ----------------------------------------------------------------------
    def test_register_success(self, api_client, fake_redis_client):
        email = "brandnew@example.com"
        otp = OTPService.generate(user=email, purpose=OtpPurpose.REGISTRATION)

        payload = {
            "first_name": "Brand",
            "last_name": "New",
            "email": email,
            "password": "StrongPassword123!",
            "otp": otp,
        }
        response = api_client.post("/v1/auth/register/", payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["success"] is True
        assert response.data["message"] == "User registered successfully"
        assert response.data["data"]["email"] == email
        assert "access" in response.data["data"]
        assert "refresh" in response.data["data"]

        # Confirm user was created in DB
        assert User.objects.filter(email=email).exists() is True

    def test_register_invalid_otp_fails(self, api_client, fake_redis_client):
        email = "bad_otp@example.com"
        OTPService.generate(user=email, purpose=OtpPurpose.REGISTRATION)

        payload = {
            "first_name": "Bad",
            "last_name": "Otp",
            "email": email,
            "password": "StrongPassword123!",
            "otp": "000000",
        }
        response = api_client.post("/v1/auth/register/", payload, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["success"] is False
        assert "Invalid registration data" in response.data["message"]
        assert User.objects.filter(email=email).exists() is False

    def test_register_duplicate_email_fails(self, api_client, test_user, fake_redis_client):
        otp = OTPService.generate(user=test_user.email, purpose=OtpPurpose.REGISTRATION)
        payload = {
            "first_name": "Duplicate",
            "last_name": "User",
            "email": test_user.email,
            "password": "StrongPassword123!",
            "otp": otp,
        }
        response = api_client.post("/v1/auth/register/", payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ----------------------------------------------------------------------
    # Login Tests
    # ----------------------------------------------------------------------
    def test_login_success(self, api_client, test_user, test_password):
        payload = {
            "email": test_user.email,
            "password": test_password,
        }
        response = api_client.post("/v1/auth/login/", payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        # TokenObtainPairView default response provides access and refresh
        data = response.data
        token_data = data.get("data") or data
        assert "access" in token_data
        assert "refresh" in token_data

    def test_login_invalid_password_fails(self, api_client, test_user):
        payload = {
            "email": test_user.email,
            "password": "WrongPassword999!",
        }
        response = api_client.post("/v1/auth/login/", payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_inactive_user_fails(self, api_client, user_factory, test_password):
        inactive_user = user_factory(email="inactive@example.com", is_active=False)
        payload = {
            "email": inactive_user.email,
            "password": test_password,
        }
        response = api_client.post("/v1/auth/login/", payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # ----------------------------------------------------------------------
    # Token Verify & Refresh Tests
    # ----------------------------------------------------------------------
    def test_token_verify_success(self, api_client, user_tokens):
        response = api_client.post("/v1/auth/token/verify/", {"token": user_tokens["access"]}, format="json")
        assert response.status_code == status.HTTP_200_OK

    def test_token_verify_invalid_token_fails(self, api_client):
        response = api_client.post("/v1/auth/token/verify/", {"token": "invalid.jwt.token"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_refresh_success(self, api_client, user_tokens):
        response = api_client.post("/v1/auth/token/refresh/", {"refresh": user_tokens["refresh"]}, format="json")
        assert response.status_code == status.HTTP_200_OK
        data = response.data.get("data") or response.data
        assert "access" in data

    def test_token_refresh_invalid_token_fails(self, api_client):
        response = api_client.post("/v1/auth/token/refresh/", {"refresh": "invalid-refresh-token"}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # ----------------------------------------------------------------------
    # Current User Profile (Verify) Tests
    # ----------------------------------------------------------------------
    def test_verify_user_authenticated(self, authenticated_client, test_user):
        response = authenticated_client.get("/v1/auth/verify/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert response.data["data"]["email"] == test_user.email
        assert response.data["data"]["id"] == test_user.id

    def test_verify_user_unauthenticated_fails(self, api_client):
        response = api_client.get("/v1/auth/verify/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    # ----------------------------------------------------------------------
    # Logout Tests
    # ----------------------------------------------------------------------
    def test_logout_success_blacklists_token(self, authenticated_client, user_tokens, api_client):
        response = authenticated_client.post("/v1/auth/logout/", {"refresh": user_tokens["refresh"]}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "Logged out successfully" in response.data["message"]

        # Attempting to refresh with the blacklisted token must fail with 401
        refresh_response = api_client.post("/v1/auth/token/refresh/", {"refresh": user_tokens["refresh"]}, format="json")
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_missing_refresh_token_fails(self, authenticated_client):
        response = authenticated_client.post("/v1/auth/logout/", {}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ----------------------------------------------------------------------
    # Change Password Tests
    # ----------------------------------------------------------------------
    def test_change_password_success(self, authenticated_client, test_user, test_password):
        new_pwd = "BrandNewPassword123!"
        payload = {
            "old_password": test_password,
            "new_password": new_pwd,
        }
        response = authenticated_client.post("/v1/auth/password/change/", payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True

        test_user.refresh_from_db()
        assert test_user.check_password(new_pwd) is True

    def test_change_password_wrong_old_password_fails(self, authenticated_client, test_user):
        payload = {
            "old_password": "WrongOldPassword!",
            "new_password": "BrandNewPassword123!",
        }
        response = authenticated_client.post("/v1/auth/password/change/", payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Current password is incorrect" in response.data["message"]

    # ----------------------------------------------------------------------
    # Reset Password Tests
    # ----------------------------------------------------------------------
    def test_reset_password_with_otp_success(self, api_client, test_user, fake_redis_client):
        otp = OTPService.generate(user=test_user.email, purpose=OtpPurpose.PASSWORD_RESET)
        new_pwd = "CompletelyResetPassword123!"

        payload = {
            "email": test_user.email,
            "otp": otp,
            "new_password": new_pwd,
        }
        response = api_client.post("/v1/auth/password/reset/", payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True

        test_user.refresh_from_db()
        assert test_user.check_password(new_pwd) is True

    def test_reset_password_invalid_otp_fails(self, api_client, test_user, fake_redis_client):
        OTPService.generate(user=test_user.email, purpose=OtpPurpose.PASSWORD_RESET)
        payload = {
            "email": test_user.email,
            "otp": "999999",
            "new_password": "NewPassword123!",
        }
        response = api_client.post("/v1/auth/password/reset/", payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid or expired OTP" in response.data["message"]
