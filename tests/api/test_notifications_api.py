import pytest
from rest_framework import status

from notifications.models import Notification


@pytest.mark.api
@pytest.mark.django_db
class TestNotificationsAPI:
    def test_list_notifications_paginated(self, authenticated_client, test_user, notification_factory):
        # Create 5 notifications for test_user
        for i in range(5):
            notification_factory(user=test_user, title=f"Notification {i}")

        response = authenticated_client.get("/v1/notifications/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert response.data["message"] == "Notifications retrieved"

        results_data = response.data["data"]
        assert results_data["count"] == 5
        assert len(results_data["results"]) == 5

    def test_list_notifications_user_isolation(self, authenticated_client, test_user, user_factory, notification_factory):
        other_user = user_factory(email="other_owner@example.com")
        notification_factory(user=other_user, title="Other's Secret")
        notification_factory(user=test_user, title="My Alert")

        response = authenticated_client.get("/v1/notifications/")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["data"]["results"]
        assert len(results) == 1
        assert results[0]["title"] == "My Alert"

    def test_list_notifications_unauthenticated_fails(self, api_client):
        response = api_client.get("/v1/notifications/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unread_count(self, authenticated_client, test_user, notification_factory):
        notification_factory(user=test_user, is_read=False)
        notification_factory(user=test_user, is_read=False)
        notification_factory(user=test_user, is_read=True)

        response = authenticated_client.get("/v1/notifications/unread-count/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert response.data["data"]["count"] == 2

    def test_mark_single_notification_read(self, authenticated_client, test_user, notification_factory):
        notif = notification_factory(user=test_user, is_read=False)

        response = authenticated_client.patch(f"/v1/notifications/{notif.id}/read/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "Notification marked as read" in response.data["message"]

        notif.refresh_from_db()
        assert notif.is_read is True
        assert notif.read_at is not None

    def test_mark_notification_read_already_read_returns_404(self, authenticated_client, test_user, notification_factory):
        notif = notification_factory(user=test_user, is_read=True)
        response = authenticated_client.patch(f"/v1/notifications/{notif.id}/read/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_cannot_mark_another_users_notification_read(self, authenticated_client, user_factory, notification_factory):
        other_user = user_factory(email="another_victim@example.com")
        other_notif = notification_factory(user=other_user, is_read=False)

        response = authenticated_client.patch(f"/v1/notifications/{other_notif.id}/read/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        other_notif.refresh_from_db()
        assert other_notif.is_read is False

    def test_mark_all_read(self, authenticated_client, test_user, notification_factory):
        for _ in range(3):
            notification_factory(user=test_user, is_read=False)

        response = authenticated_client.patch("/v1/notifications/read-all/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert response.data["data"]["updated"] == 3

        # Verify in DB
        assert Notification.objects.filter(user=test_user, is_read=False).count() == 0
