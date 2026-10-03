import pytest
from unittest.mock import patch

from emails.tasks import send_email_task
from emails.models import EmailLog
from emails.choices import EmailPurpose, EmailStatus


@pytest.mark.integration
@pytest.mark.django_db
class TestCeleryEmailTasksIntegration:
    def test_send_email_task_execution_and_log_creation(self):
        with patch("django.core.mail.backends.smtp.EmailBackend.send_messages", return_value=1):
            send_email_task(
                subject="Test Celery Email",
                to_emails=["celery_user@example.com"],
                body="<p>Test body</p>",
                log_body="<p>Masked body</p>",
                purpose=EmailPurpose.WELCOME,
            )

        log = EmailLog.objects.filter(to_emails="celery_user@example.com").first()
        assert log is not None
        assert log.subject == "Test Celery Email"
        assert log.body == "<p>Masked body</p>"
        assert log.purpose == EmailPurpose.WELCOME
