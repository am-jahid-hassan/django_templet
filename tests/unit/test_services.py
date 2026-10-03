import pytest
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.conf import settings

from otp.services import OTPService
from otp.choices import OtpPurpose, OtpChannel
from notifications.services import NotificationService
from authentication.services import change_password, reset_password

User = get_user_model()


@pytest.mark.unit
class TestOTPServiceUnit:
    def test_otp_generate_returns_valid_string_and_stores_hash(self, fake_redis_client):
        identifier = "user@example.com"
        otp = OTPService.generate(user=identifier, purpose=OtpPurpose.REGISTRATION)

        assert isinstance(otp, str)
        assert len(otp) == settings.CONFIG.OTP_LENGTH

        # Verify hash is stored in redis
        user_hash = OTPService._user_hash(identifier)
        index_key = OTPService._index_key(OtpPurpose.REGISTRATION, user_hash)
        otp_ids = fake_redis_client.lrange(index_key, 0, -1)
        assert len(otp_ids) == 1

        otp_key = OTPService._otp_key(OtpPurpose.REGISTRATION, user_hash, otp_ids[0])
        stored_hash = fake_redis_client.get(otp_key)
        assert stored_hash == OTPService._hash_otp(otp)

    def test_otp_verification_success_deletes_otp(self, fake_redis_client):
        identifier = "verify_user@example.com"
        otp = OTPService.generate(user=identifier, purpose=OtpPurpose.PASSWORD_RESET)

        # Successful verification
        is_valid = OTPService.verify(user=identifier, purpose=OtpPurpose.PASSWORD_RESET, submitted_otp=otp)
        assert is_valid is True

        # OTP is single-use: subsequent verification with same OTP must fail
        assert OTPService.verify(user=identifier, purpose=OtpPurpose.PASSWORD_RESET, submitted_otp=otp) is False

    def test_otp_verification_failure_with_wrong_code(self, fake_redis_client):
        identifier = "wrong_code@example.com"
        OTPService.generate(user=identifier, purpose=OtpPurpose.REGISTRATION)

        assert OTPService.verify(user=identifier, purpose=OtpPurpose.REGISTRATION, submitted_otp="000000") is False

    def test_consecutive_generate_invalidates_previous_otp(self, fake_redis_client):
        identifier = "override@example.com"
        otp_first = OTPService.generate(user=identifier, purpose=OtpPurpose.REGISTRATION)
        otp_second = OTPService.generate(user=identifier, purpose=OtpPurpose.REGISTRATION)

        assert otp_first != otp_second

        # First OTP should no longer be valid
        assert OTPService.verify(user=identifier, purpose=OtpPurpose.REGISTRATION, submitted_otp=otp_first) is False
        # Second OTP should be valid
        assert OTPService.verify(user=identifier, purpose=OtpPurpose.REGISTRATION, submitted_otp=otp_second) is True

    def test_otp_lockout_after_max_attempts(self, fake_redis_client):
        identifier = "bruteforce@example.com"
        valid_otp = OTPService.generate(user=identifier, purpose=OtpPurpose.REGISTRATION)

        # Submit max failed attempts
        max_attempts = settings.CONFIG.MAX_VERIFY_ATTEMPTS
        for _ in range(max_attempts):
            OTPService.verify(user=identifier, purpose=OtpPurpose.REGISTRATION, submitted_otp="999999")

        # Now even the correct OTP is rejected due to brute-force lockout
        assert OTPService.verify(user=identifier, purpose=OtpPurpose.REGISTRATION, submitted_otp=valid_otp) is False

    @patch("emails.tasks.send_email_task.delay")
    def test_otp_send_dispatches_email_task_with_masked_body(self, mock_delay, fake_redis_client):
        identifier = "send_test@example.com"
        OTPService.send(user=identifier, purpose=OtpPurpose.REGISTRATION, channel=OtpChannel.EMAIL)

        mock_delay.assert_called_once()
        kwargs = mock_delay.call_args.kwargs
        assert kwargs["to_emails"] == [identifier]
        assert "******" in kwargs["log_body"]


@pytest.mark.unit
@pytest.mark.django_db
class TestNotificationServiceUnit:
    def test_send_notification_creates_db_record(self, test_user):
        notif = NotificationService.send(
            user=test_user,
            title="Service Alert",
            body="Maintenance planned",
        )
        assert notif.pk is not None
        assert notif.user == test_user
        assert notif.is_read is False

    def test_unread_count_accurate(self, test_user, notification_factory):
        assert NotificationService.unread_count(test_user) == 0

        notification_factory(user=test_user, is_read=False)
        notification_factory(user=test_user, is_read=False)
        notification_factory(user=test_user, is_read=True)

        assert NotificationService.unread_count(test_user) == 2

    def test_mark_read_single_notification(self, test_user, notification_factory):
        notif = notification_factory(user=test_user, is_read=False)
        success = NotificationService.mark_read(notif.id, test_user)

        assert success is True
        notif.refresh_from_db()
        assert notif.is_read is True
        assert notif.read_at is not None

        # Trying to mark an already read notification returns False (0 updated)
        assert NotificationService.mark_read(notif.id, test_user) is False

    def test_mark_all_read(self, test_user, notification_factory):
        notification_factory(user=test_user, is_read=False)
        notification_factory(user=test_user, is_read=False)
        notification_factory(user=test_user, is_read=False)

        count = NotificationService.mark_all_read(test_user)
        assert count == 3
        assert NotificationService.unread_count(test_user) == 0


@pytest.mark.unit
@pytest.mark.django_db
class TestAuthServicesUnit:
    def test_change_password_service(self, test_user):
        new_pwd = "NewSecureP@ssw0rd999!"
        change_password(test_user, new_pwd)
        test_user.refresh_from_db()
        assert test_user.check_password(new_pwd) is True

    def test_reset_password_service(self, test_user):
        new_pwd = "ResetP@ssw0rd888!"
        reset_password(test_user.email, new_pwd)
        test_user.refresh_from_db()
        assert test_user.check_password(new_pwd) is True
