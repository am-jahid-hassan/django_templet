import pytest
from unittest.mock import patch
from rest_framework import status


@pytest.mark.api
@pytest.mark.django_db
class TestHealthCheckAPI:
    def test_health_check_healthy_status_200(self, api_client):
        response = api_client.get("/health/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"status": "healthy"}

    def test_health_check_db_failure_status_503(self, api_client):
        with patch("core.views.connection.cursor", side_effect=Exception("DB Down")):
            response = api_client.get("/health/")
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert response.data == {"status": "unhealthy"}

    def test_health_dashboard_in_debug_mode(self):
        from django.test import RequestFactory
        from core.views import HealthReportView
        factory = RequestFactory()
        req = factory.get("/")
        response = HealthReportView.as_view()(req)
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response["Content-Type"]
