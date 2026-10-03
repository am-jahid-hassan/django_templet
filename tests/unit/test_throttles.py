import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from core.throttles import AuthenticatedUserRateThrottle, TargetIdentifierRateThrottle
from authentication.throttles import LoginTargetThrottle, ResetPasswordTargetThrottle
from otp.throttles import OtpTargetRateThrottle

User = get_user_model()


@pytest.mark.unit
@pytest.mark.django_db
class TestThrottlesUnit:
    @pytest.fixture(autouse=True)
    def setup_factory(self):
        self.factory = RequestFactory()

    def test_authenticated_user_throttle_ignores_anonymous(self):
        throttle = AuthenticatedUserRateThrottle()
        req = self.factory.get("/")
        req.user = AnonymousUser()
        assert throttle.get_cache_key(req, None) is None

    def test_authenticated_user_throttle_keys_on_user_id(self, test_user):
        throttle = AuthenticatedUserRateThrottle()
        req = self.factory.get("/")
        req.user = test_user
        cache_key = throttle.get_cache_key(req, None)
        assert cache_key is not None
        assert str(test_user.pk) in cache_key

    def test_target_identifier_throttle_extracts_and_hashes_email(self):
        throttle = TargetIdentifierRateThrottle()
        req = self.factory.post("/", {"email": "Target@Example.com"}, content_type="application/json")
        req.data = {"email": "Target@Example.com"}
        req.user = AnonymousUser()

        key = throttle.get_cache_key(req, None)
        assert key is not None
        assert "target@example.com" in key

    def test_login_target_throttle_keys_on_login_email(self):
        throttle = LoginTargetThrottle()
        req = self.factory.post("/v1/auth/login/", {"email": "victim_login@test.com"}, content_type="application/json")
        req.data = {"email": "victim_login@test.com"}
        req.user = AnonymousUser()

        key = throttle.get_cache_key(req, None)
        assert key is not None
        assert "victim_login@test.com" in key

    def test_reset_password_target_throttle_keys_on_email(self):
        throttle = ResetPasswordTargetThrottle()
        req = self.factory.post("/v1/auth/password/reset/", {"email": "reset_victim@test.com"}, content_type="application/json")
        req.data = {"email": "reset_victim@test.com"}
        req.user = AnonymousUser()

        key = throttle.get_cache_key(req, None)
        assert key is not None
        assert "reset_victim@test.com" in key

    def test_otp_target_throttle_keys_on_user_identifier(self):
        throttle = OtpTargetRateThrottle()
        req = self.factory.post("/v1/otp/get-otp/", {"user_identifier": "otp_target@test.com"}, content_type="application/json")
        req.data = {"user_identifier": "otp_target@test.com"}
        req.user = AnonymousUser()

        key = throttle.get_cache_key(req, None)
        assert key is not None
        assert "otp_target@test.com" in key
