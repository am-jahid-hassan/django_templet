import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from notifications.models import Notification

User = get_user_model()


# --------------------------------------------------------------------------
# In-Memory Fake Redis Implementation for Testing
# --------------------------------------------------------------------------
class FakeRedisPipeline:
    def __init__(self, fake_redis):
        self.fake_redis = fake_redis
        self.commands = []

    def set(self, key, value, ex=None):
        self.commands.append(("set", (key, value, ex)))
        return self

    def get(self, key):
        self.commands.append(("get", (key,)))
        return self

    def delete(self, *keys):
        self.commands.append(("delete", keys))
        return self

    def rpush(self, key, *values):
        self.commands.append(("rpush", (key, *values)))
        return self

    def lrange(self, key, start, end):
        self.commands.append(("lrange", (key, start, end)))
        return self

    def lrem(self, key, count, value):
        self.commands.append(("lrem", (key, count, value)))
        return self

    def expire(self, key, seconds):
        self.commands.append(("expire", (key, seconds)))
        return self

    def execute(self):
        results = []
        for cmd, args in self.commands:
            fn = getattr(self.fake_redis, cmd)
            results.append(fn(*args))
        self.commands = []
        return results


class FakeRedisClient:
    """
    Self-contained thread-safe in-memory Redis mock supporting operations
    used by OTPService, cache, and rate-limiting.
    """
    def __init__(self):
        self.store = {}
        self.lists = {}

    def get(self, key):
        return self.store.get(str(key))

    def set(self, key, value, ex=None):
        self.store[str(key)] = str(value)
        return True

    def delete(self, *keys):
        deleted = 0
        for k in keys:
            sk = str(k)
            if sk in self.store:
                del self.store[sk]
                deleted += 1
            if sk in self.lists:
                del self.lists[sk]
                deleted += 1
        return deleted

    def incr(self, key, amount=1):
        sk = str(key)
        val = int(self.store.get(sk, 0)) + amount
        self.store[sk] = str(val)
        return val

    def rpush(self, key, *values):
        sk = str(key)
        if sk not in self.lists:
            self.lists[sk] = []
        for v in values:
            self.lists[sk].append(str(v))
        return len(self.lists[sk])

    def lrange(self, key, start, end):
        sk = str(key)
        items = self.lists.get(sk, [])
        if end == -1:
            return items[start:]
        return items[start : end + 1]

    def lrem(self, key, count, value):
        sk = str(key)
        sval = str(value)
        if sk not in self.lists:
            return 0
        original_len = len(self.lists[sk])
        self.lists[sk] = [x for x in self.lists[sk] if x != sval]
        return original_len - len(self.lists[sk])

    def llen(self, key):
        sk = str(key)
        return len(self.lists.get(sk, []))

    def lpop(self, key):
        sk = str(key)
        if sk in self.lists and self.lists[sk]:
            return self.lists[sk].pop(0)
        return None

    def expire(self, key, seconds):
        return True

    def pipeline(self):
        return FakeRedisPipeline(self)

    def flushall(self):
        self.store.clear()
        self.lists.clear()


@pytest.fixture(autouse=True)
def fake_redis_client():
    """
    Patches redis_client everywhere with an in-memory client so tests do not
    require a live Redis server running on the machine.
    """
    fake_client = FakeRedisClient()
    with patch("core.cache.redis_client.redis_client", fake_client), \
         patch("otp.services.otp.redis_client", fake_client):
        yield fake_client


@pytest.fixture(autouse=True)
def clean_django_cache():
    """Clear locmem cache before each test to prevent throttling bleed-over."""
    cache.clear()
    yield
    cache.clear()


# --------------------------------------------------------------------------
# API Client & User Fixtures
# --------------------------------------------------------------------------
@pytest.fixture
def api_client():
    """Unauthenticated DRF APIClient."""
    return APIClient()


@pytest.fixture
def test_password():
    return "TestSecurePass123!"


@pytest.fixture
def user_factory(db, test_password):
    def create_user(**kwargs):
        email = kwargs.pop("email", None)
        if not email:
            import uuid
            email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        password = kwargs.pop("password", test_password)
        first_name = kwargs.pop("first_name", "Test")
        last_name = kwargs.pop("last_name", "User")
        return User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            **kwargs,
        )
    return create_user


@pytest.fixture
def test_user(user_factory):
    return user_factory(email="testuser@example.com", first_name="Standard", last_name="User")


@pytest.fixture
def staff_user(user_factory):
    return user_factory(email="staff@example.com", first_name="Staff", last_name="Member", is_staff=True)


@pytest.fixture
def superuser(user_factory):
    return user_factory(email="admin@example.com", first_name="Super", last_name="Admin", is_staff=True, is_superuser=True)


@pytest.fixture
def user_tokens(test_user):
    refresh = RefreshToken.for_user(test_user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


@pytest.fixture
def authenticated_client(api_client, user_tokens):
    """APIClient pre-authenticated with test_user JWT access token."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {user_tokens['access']}")
    return api_client


@pytest.fixture
def staff_client(api_client, staff_user):
    """APIClient pre-authenticated with staff_user JWT access token."""
    refresh = RefreshToken.for_user(staff_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def mock_send_email():
    """Mocks asynchronous email Celery task dispatch."""
    with patch("emails.tasks.send_email_task.delay") as mock_delay:
        yield mock_delay


@pytest.fixture
def notification_factory(db):
    def create_notification(user, title="Test Notification", body="Test message body", is_read=False):
        return Notification.objects.create(
            user=user,
            title=title,
            body=body,
            is_read=is_read,
        )
    return create_notification
