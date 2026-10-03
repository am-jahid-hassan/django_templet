import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser

from logs.middleware import LoggingContextMiddleware
from activity.middleware import ActivityTrackingMiddleware
from activity.models import UserActivity, UserSession


@pytest.mark.integration
@pytest.mark.django_db
class TestLoggingMiddlewareIntegration:
    def test_logging_middleware_injects_and_returns_request_id(self):
        factory = RequestFactory()
        req = factory.get("/health/")
        req.user = AnonymousUser()

        middleware = LoggingContextMiddleware(get_response=lambda r: HttpResponse("OK"))
        middleware.process_request(req)

        assert hasattr(req, "request_id")
        assert len(req.request_id) > 0

        resp = HttpResponse("OK")
        resp = middleware.process_response(req, resp)

        assert resp.headers.get("X-Request-ID") == req.request_id


@pytest.mark.integration
@pytest.mark.django_db
class TestActivityMiddlewareIntegration:
    def test_activity_tracking_records_activity_for_user(self, test_user):
        factory = RequestFactory()
        req = factory.get("/v1/notifications/")
        req.user = test_user
        req.request_id = "test-req-id-123"

        middleware = ActivityTrackingMiddleware(get_response=lambda r: HttpResponse("OK", status=200))
        resp = middleware(req)

        assert resp.status_code == 200

        # Verify activity was recorded
        activity = UserActivity.objects.filter(user=test_user).first()
        assert activity is not None
        assert activity.path == "/v1/notifications/"
        assert activity.status_code == 200
        assert activity.request_id == "test-req-id-123"

    def test_activity_tracking_skips_excluded_paths(self, test_user):
        factory = RequestFactory()
        req = factory.get("/admin/login/")
        req.user = test_user
        req.request_id = "admin-req-123"

        initial_count = UserActivity.objects.count()
        middleware = ActivityTrackingMiddleware(get_response=lambda r: HttpResponse("OK", status=200))
        middleware(req)

        assert UserActivity.objects.count() == initial_count
