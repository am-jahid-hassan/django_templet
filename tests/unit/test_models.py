import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import BaseModel
from notifications.models import Notification
from logs.models import SystemLog
from activity.models import UserSession, UserActivity
from emails.models import EmailLog
from emails.choices import EmailPurpose, EmailStatus

User = get_user_model()


@pytest.mark.unit
@pytest.mark.django_db
class TestUserModel:
    def test_create_standard_user_success(self):
        user = User.objects.create_user(
            email="regular@example.com",
            password="StrongPassword123!",
            first_name="John",
            last_name="Doe",
        )
        assert user.pk is not None
        assert user.email == "regular@example.com"
        assert user.first_name == "John"
        assert user.last_name == "Doe"
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.check_password("StrongPassword123!") is True
        assert str(user) == f"{user.id} - {user.email}"

    def test_create_user_without_email_raises_error(self):
        with pytest.raises(ValueError, match="The Email field must be set"):
            User.objects.create_user(email="", password="Password123!")

    def test_create_superuser_success(self):
        admin = User.objects.create_superuser(
            email="admin@example.com",
            password="AdminPassword123!",
        )
        assert admin.pk is not None
        assert admin.is_staff is True
        assert admin.is_superuser is True

    def test_create_superuser_missing_is_staff_fails(self):
        with pytest.raises(ValueError, match="Superuser must have is_staff=True"):
            User.objects.create_superuser(
                email="bad_admin@example.com",
                password="Password123!",
                is_staff=False,
            )

    def test_create_superuser_missing_is_superuser_fails(self):
        with pytest.raises(ValueError, match="Superuser must have is_superuser=True"):
            User.objects.create_superuser(
                email="bad_admin2@example.com",
                password="Password123!",
                is_superuser=False,
            )


@pytest.mark.unit
@pytest.mark.django_db
class TestBaseModelSoftDelete:
    def test_soft_delete_and_restore_cycle(self, test_user):
        notification = Notification.objects.create(
            user=test_user,
            title="Soft Delete Test",
            body="Checking soft delete functionality",
        )
        notif_id = notification.id

        assert notification.is_deleted is False
        assert notification.deleted_at is None

        # Execute soft delete
        notification.soft_delete()
        notification.refresh_from_db()

        assert notification.is_deleted is True
        assert notification.deleted_at is not None

        # Custom manager `objects` must exclude soft-deleted records
        assert Notification.objects.filter(id=notif_id).exists() is False

        # `all_objects` manager must still find it
        assert Notification.all_objects.filter(id=notif_id).exists() is True

        # Restore
        notification.restore()
        notification.refresh_from_db()

        assert notification.is_deleted is False
        assert notification.deleted_at is None
        assert Notification.objects.filter(id=notif_id).exists() is True


@pytest.mark.unit
@pytest.mark.django_db
class TestNotificationModel:
    def test_notification_creation_and_defaults(self, test_user):
        notif = Notification.objects.create(
            user=test_user,
            title="System Alert",
            body="Your security settings were updated.",
        )
        assert notif.pk is not None
        assert notif.is_read is False
        assert notif.read_at is None
        assert "unread" in str(notif)


@pytest.mark.unit
@pytest.mark.django_db
class TestSystemLogModel:
    def test_system_log_creation(self):
        log = SystemLog.objects.create(
            log_level="INFO",
            event_name="user.login.success",
            message="User logged in successfully",
            service_name="auth_service",
            request_id="req-123456",
        )
        assert log.id is not None
        assert log.log_level == "INFO"
        assert log.event_name == "user.login.success"
        assert "user.login.success" in str(log)


@pytest.mark.unit
@pytest.mark.django_db
class TestActivityModels:
    def test_user_session_and_duration_property(self, test_user):
        session = UserSession.objects.create(
            user=test_user,
            session_key="sess-uuid-12345",
            ip_address="127.0.0.1",
            device_type="desktop",
        )
        assert session.is_active is True
        assert session.duration_seconds is None

        # Set ended_at to 10 seconds later
        session.ended_at = session.started_at + timezone.timedelta(seconds=10)
        session.save()
        assert session.duration_seconds == 10
        assert "sess-uui" in str(session)

    def test_user_activity_creation(self, test_user):
        activity = UserActivity.objects.create(
            user=test_user,
            action="login",
            service="authentication",
            path="/v1/auth/login/",
            method="POST",
            status_code=200,
        )
        assert activity.pk is not None
        assert "authentication:login [200]" in str(activity)


@pytest.mark.unit
@pytest.mark.django_db
class TestEmailLogModel:
    def test_email_log_creation(self):
        email_log = EmailLog.objects.create(
            to_emails="recipient@example.com",
            from_email="noreply@example.com",
            subject="Welcome!",
            body="<html>Welcome</html>",
            purpose=EmailPurpose.WELCOME,
            status=EmailStatus.SENT,
        )
        assert email_log.pk is not None
        assert email_log.try_count == 1
        assert "Welcome!" in str(email_log)
