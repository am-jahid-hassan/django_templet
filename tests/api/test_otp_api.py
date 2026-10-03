import pytest
from unittest.mock import patch
from rest_framework import status

from otp.choices import OtpPurpose, OtpChannel

GET_OTP_URL = "/v1/otp/get-otp/"


@pytest.mark.api
@pytest.mark.django_db
class TestOtpAPI:
    def test_request_otp_registration_happy_path(self, api_client, mock_send_email):
        payload = {
            "purpose": "registration",
            "user_identifier": "newbie@example.com",
            "otp_channel": "email",
        }
        response = api_client.post(GET_OTP_URL, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "OTP sent successfully" in response.data["message"]
        mock_send_email.assert_called_once()

    def test_request_otp_registration_duplicate_email_fails(self, api_client, test_user, mock_send_email):
        payload = {
            "purpose": "registration",
            "user_identifier": test_user.email,
        }
        response = api_client.post(GET_OTP_URL, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["success"] is False
        assert "already exists" in response.data["message"]
        mock_send_email.assert_not_called()

    def test_request_otp_missing_purpose_fails(self, api_client):
        response = api_client.post(GET_OTP_URL, {"user_identifier": "some@email.com"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Missing required field(s): purpose" in response.data["message"]

    def test_request_otp_invalid_purpose_fails(self, api_client):
        response = api_client.post(GET_OTP_URL, {"purpose": "invalid_purpose", "user_identifier": "some@email.com"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "valid value" in response.data["message"]

    def test_request_otp_password_reset_user_not_found(self, api_client):
        payload = {
            "purpose": "password_reset",
            "user_identifier": "ghost@example.com",
        }
        response = api_client.post(GET_OTP_URL, payload, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "User not found" in response.data["message"]

    def test_request_otp_password_reset_existing_user_success(self, api_client, test_user, mock_send_email):
        payload = {
            "purpose": "password_reset",
            "user_identifier": test_user.email,
        }
        response = api_client.post(GET_OTP_URL, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        mock_send_email.assert_called_once()

    def test_request_otp_auth_required_purpose_anonymous_fails(self, api_client):
        payload = {
            "purpose": "change_email",
        }
        response = api_client.post(GET_OTP_URL, payload, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Authentication required" in response.data["message"]

    def test_request_otp_auth_required_purpose_authenticated_success(self, authenticated_client, test_user, mock_send_email):
        payload = {
            "purpose": "change_email",
        }
        response = authenticated_client.post(GET_OTP_URL, payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        mock_send_email.assert_called_once()
