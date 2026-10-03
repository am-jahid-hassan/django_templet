import pytest
from rest_framework import status
from django.contrib.auth import get_user_model

from otp.choices import OtpPurpose
from otp.services import OTPService

User = get_user_model()


@pytest.mark.workflow
@pytest.mark.django_db
class TestPasswordRecoveryWorkflow:
    """
    End-to-End Password Recovery & Reset Workflow:
    1. User requests password reset OTP.
    2. Email task dispatched with code.
    3. User attempts reset with invalid code -> rejected.
    4. User resets with valid OTP and new strong password -> succeeds.
    5. Old password no longer works.
    6. User successfully authenticates with new password.
    """
    def test_complete_password_recovery_workflow(self, api_client, test_user, test_password, mock_send_email, fake_redis_client):
        new_password = "RecoveredPassword!2026"

        # 1. Request reset OTP
        req_resp = api_client.post(
            "/v1/otp/get-otp/",
            {"purpose": "password_reset", "user_identifier": test_user.email},
            format="json",
        )
        assert req_resp.status_code == status.HTTP_200_OK
        mock_send_email.assert_called_once()

        # Generate a valid code for verification
        valid_otp = OTPService.generate(user=test_user.email, purpose=OtpPurpose.PASSWORD_RESET)

        # 2. Attempt with wrong OTP
        wrong_attempt = api_client.post(
            "/v1/auth/password/reset/",
            {"email": test_user.email, "otp": "000000", "new_password": new_password},
            format="json",
        )
        assert wrong_attempt.status_code == status.HTTP_400_BAD_REQUEST

        # 3. Submit valid OTP
        success_reset = api_client.post(
            "/v1/auth/password/reset/",
            {"email": test_user.email, "otp": valid_otp, "new_password": new_password},
            format="json",
        )
        assert success_reset.status_code == status.HTTP_200_OK
        assert success_reset.data["success"] is True

        # 4. Old password fails
        old_login = api_client.post(
            "/v1/auth/login/",
            {"email": test_user.email, "password": test_password},
            format="json",
        )
        assert old_login.status_code == status.HTTP_401_UNAUTHORIZED

        # 5. New password succeeds
        new_login = api_client.post(
            "/v1/auth/login/",
            {"email": test_user.email, "password": new_password},
            format="json",
        )
        assert new_login.status_code == status.HTTP_200_OK
        data = new_login.data.get("data") or new_login.data
        assert "access" in data
