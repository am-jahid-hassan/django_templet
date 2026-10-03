import pytest
from rest_framework import status
from django.contrib.auth import get_user_model

from otp.choices import OtpPurpose
from otp.services import OTPService

User = get_user_model()


@pytest.mark.workflow
@pytest.mark.django_db
class TestRegistrationJourneyWorkflow:
    """
    End-to-End User Registration Workflow:
    1. Anonymous visitor requests OTP for registration.
    2. Email task is queued, OTP stored in Redis.
    3. Visitor submits registration form with OTP and password.
    4. Account is created, JWT tokens are issued.
    5. Visitor uses returned JWT token to access protected profile and notification routes.
    """
    def test_complete_registration_workflow(self, api_client, mock_send_email, fake_redis_client):
        email = "journey_user@example.com"
        password = "JourneySecurePass123!"

        # Step 1: Request OTP
        otp_req = api_client.post(
            "/v1/otp/get-otp/",
            {"purpose": "registration", "user_identifier": email, "otp_channel": "email"},
            format="json",
        )
        assert otp_req.status_code == status.HTTP_200_OK
        assert otp_req.data["success"] is True
        mock_send_email.assert_called_once()

        # Retrieve the OTP that was generated in Redis
        user_hash = OTPService._user_hash(email)
        index_key = OTPService._index_key(OtpPurpose.REGISTRATION, user_hash)
        otp_id = fake_redis_client.lrange(index_key, 0, -1)[0]
        otp_key = OTPService._otp_key(OtpPurpose.REGISTRATION, user_hash, otp_id)
        # Note: In real life user receives OTP in email; in tests we can generate or get via service
        # Let's generate a fresh known OTP to simulate the exact email code received:
        code = OTPService.generate(user=email, purpose=OtpPurpose.REGISTRATION)

        # Step 2: Register user using OTP
        reg_resp = api_client.post(
            "/v1/auth/register/",
            {
                "email": email,
                "first_name": "Journey",
                "last_name": "Tester",
                "password": password,
                "otp": code,
            },
            format="json",
        )
        assert reg_resp.status_code == status.HTTP_201_CREATED
        assert reg_resp.data["success"] is True

        tokens = reg_resp.data["data"]
        access_token = tokens["access"]
        refresh_token = tokens["refresh"]
        assert access_token is not None
        assert refresh_token is not None

        # Step 3: Use the new token to access protected profile endpoint
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        profile_resp = api_client.get("/v1/auth/verify/")

        assert profile_resp.status_code == status.HTTP_200_OK
        assert profile_resp.data["success"] is True
        assert profile_resp.data["data"]["email"] == email
        assert profile_resp.data["data"]["first_name"] == "Journey"

        # Step 4: Access notifications list with new session
        notif_resp = api_client.get("/v1/notifications/")
        assert notif_resp.status_code == status.HTTP_200_OK
        assert notif_resp.data["data"]["count"] == 0
