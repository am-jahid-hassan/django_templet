import io
import pytest
from PIL import Image
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.test import RequestFactory
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError, NotAuthenticated, PermissionDenied

from core.utils.response import success_response, error_response
from core.utils.exception_handler import custom_exception_handler, handle_404, handle_500
from core.utils.general import get_or_400, get_client_ip
from core.utils.image import process_image, ImageConfig
from core.utils.generators import random_string


@pytest.mark.unit
class TestResponseEnvelopeUnit:
    def test_success_response_structure(self):
        resp = success_response(message="Operation successful", data={"key": "val"}, status_code=status.HTTP_201_CREATED)
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["success"] is True
        assert resp.data["message"] == "Operation successful"
        assert resp.data["data"] == {"key": "val"}

    def test_error_response_structure_and_error_normalization(self):
        resp = error_response(
            message="Invalid request",
            errors={"email": ["This field is required."], "age": "Must be positive"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["success"] is False
        assert resp.data["message"] == "Invalid request"
        assert "email" in resp.data["errors"]
        assert resp.data["errors"]["email"] == ["This field is required."]
        assert resp.data["errors"]["age"] == ["Must be positive"]


@pytest.mark.unit
class TestExceptionHandlerUnit:
    def test_drf_validation_error_formatting(self):
        exc = DRFValidationError({"email": ["Invalid email address."]})
        context = {"request": None}
        resp = custom_exception_handler(exc, context)

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["success"] is False
        assert resp.data["message"] == "Validation failed."
        assert "email" in resp.data["errors"]

    def test_not_authenticated_formatting(self):
        exc = NotAuthenticated()
        resp = custom_exception_handler(exc, {"request": None})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert resp.data["success"] is False
        assert resp.data["message"] == "Authentication credentials were not provided."

    def test_permission_denied_formatting(self):
        exc = PermissionDenied()
        resp = custom_exception_handler(exc, {"request": None})
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert resp.data["success"] is False
        assert resp.data["message"] == "You do not have permission to perform this action."

    def test_uncaught_exception_formatting(self):
        exc = RuntimeError("Database crashed")
        resp = custom_exception_handler(exc, {"request": None})
        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert resp.data["success"] is False
        assert resp.data["message"] == "Internal server error."

    def test_handle_404_view(self):
        factory = RequestFactory()
        req = factory.get("/non-existent-url/")
        resp = handle_404(req)
        assert resp.status_code == 404
        import json
        data = json.loads(resp.content)
        assert data["success"] is False
        assert data["message"] == "The requested endpoint does not exist."

    def test_handle_500_view(self):
        factory = RequestFactory()
        req = factory.get("/server-error/")
        resp = handle_500(req)
        assert resp.status_code == 500
        import json
        data = json.loads(resp.content)
        assert data["success"] is False
        assert data["message"] == "Internal server error."


@pytest.mark.unit
class TestGetOr400Unit:
    def test_missing_required_field_returns_400(self):
        data = {"name": "Alice"}
        ok, res = get_or_400(data, keys={"name": str, "email": str}, required=["name", "email"])
        assert ok is False
        assert res.status_code == 400
        assert "email" in res.data["message"]

    def test_wrong_type_returns_400(self):
        data = {"age": "not-an-int"}
        ok, res = get_or_400(data, keys={"age": int}, required=["age"])
        assert ok is False
        assert res.status_code == 400
        assert "must be of type int" in res.data["message"]

    def test_valid_payload_returns_values_dict(self):
        data = {"name": "Bob", "age": 30}
        ok, values = get_or_400(data, keys={"name": str, "age": int}, required=["name"])
        assert ok is True
        assert values == {"name": "Bob", "age": 30}


@pytest.mark.unit
class TestGetClientIpUnit:
    def test_remote_addr_fallback(self):
        factory = RequestFactory()
        req = factory.get("/", REMOTE_ADDR="192.168.1.50")
        assert get_client_ip(req) == "192.168.1.50"

    def test_x_forwarded_for_trusted_hop(self):
        factory = RequestFactory()
        req = factory.get("/", HTTP_X_FORWARDED_FOR="203.0.113.195, 10.0.0.1", REMOTE_ADDR="10.0.0.1")
        assert get_client_ip(req) == "10.0.0.1"


@pytest.mark.unit
class TestImageProcessingUnit:
    def _create_test_image(self, width, height, format="JPEG"):
        buf = io.BytesIO()
        image = Image.new("RGB", (width, height), color="red")
        image.save(buf, format=format)
        buf.seek(0)
        return SimpleUploadedFile(f"test.{format.lower()}", buf.getvalue(), content_type=f"image/{format.lower()}")

    def test_process_image_resizes_down_correctly(self):
        file = self._create_test_image(800, 600)
        config = ImageConfig(max_width=400, max_height=400)
        processed = process_image(file, config)

        img = Image.open(processed)
        assert img.width <= 400
        assert img.height <= 400

    def test_process_image_never_upscales(self):
        file = self._create_test_image(100, 80)
        config = ImageConfig(max_width=400, max_height=400)
        processed = process_image(file, config)

        img = Image.open(processed)
        assert img.width == 100
        assert img.height == 80

    def test_unsupported_image_format_raises_validation_error(self):
        file = SimpleUploadedFile("test.gif", b"fake gif data", content_type="image/gif")
        config = ImageConfig(max_width=400, max_height=400)
        with pytest.raises(DjangoValidationError, match="Unsupported image format"):
            process_image(file, config)


@pytest.mark.unit
class TestGeneratorsUnit:
    def test_random_string_length_and_charset(self):
        s = random_string(length=12, allow_numbers=True, allow_capital=False, allow_small=False, allow_special=False)
        assert len(s) == 12
        assert s.isdigit()
