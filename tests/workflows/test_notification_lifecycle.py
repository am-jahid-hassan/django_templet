import pytest
from rest_framework import status
from notifications.models import Notification
from notifications.services import NotificationService


@pytest.mark.workflow
@pytest.mark.django_db
class TestNotificationLifecycleWorkflow:
    """
    End-to-End Notification Lifecycle Workflow:
    1. System generates multiple events/notifications for user.
    2. User queries unread count.
    3. User queries paginated list.
    4. User marks a specific notification as read.
    5. User marks all remaining notifications as read.
    6. Confirms unread count drops to 0.
    """
    def test_complete_notification_lifecycle(self, authenticated_client, test_user):
        # 1. System generates 3 notifications
        n1 = NotificationService.send(user=test_user, title="Welcome", body="Welcome to the service")
        n2 = NotificationService.send(user=test_user, title="Security Alert", body="Password changed")
        n3 = NotificationService.send(user=test_user, title="System Update", body="Scheduled maintenance")

        # 2. Check unread count
        count_resp = authenticated_client.get("/v1/notifications/unread-count/")
        assert count_resp.status_code == status.HTTP_200_OK
        assert count_resp.data["data"]["count"] == 3

        # 3. Retrieve list
        list_resp = authenticated_client.get("/v1/notifications/")
        assert list_resp.status_code == status.HTTP_200_OK
        assert list_resp.data["data"]["count"] == 3

        # 4. Mark n1 as read
        read_resp = authenticated_client.patch(f"/v1/notifications/{n1.id}/read/")
        assert read_resp.status_code == status.HTTP_200_OK

        count_resp_2 = authenticated_client.get("/v1/notifications/unread-count/")
        assert count_resp_2.data["data"]["count"] == 2

        # 5. Mark all as read
        all_read_resp = authenticated_client.patch("/v1/notifications/read-all/")
        assert all_read_resp.status_code == status.HTTP_200_OK
        assert all_read_resp.data["data"]["updated"] == 2

        # 6. Final unread count check
        count_resp_final = authenticated_client.get("/v1/notifications/unread-count/")
        assert count_resp_final.data["data"]["count"] == 0
