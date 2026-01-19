"""

Pydantic model validation testleri.


Bu testler:

- Task modellerinin validation kurallari

- User modellerinin validation kurallari

"""

import pytest
from pydantic import ValidationError

from app.models.task import (
    TaskCreate,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskUpdate,
)
from app.models.user import UserCreate, UserLogin


class TestTaskCreate:
    """TaskCreate model testleri"""

    def test_valid_task_create(self):
        """Gecerli task olusturulabilir."""
        task = TaskCreate(
            title="Test Task",
            description="Taskin descriptionu",
            status=TaskStatus.PENDING,
            priority=TaskPriority.MEDIUM,
        )

        assert task.title == "Test Task"
        assert task.description == "Taskin descriptionu"
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.MEDIUM

    def test_task_create_with_minimal_data(self):
        """Sadece title ile task olusturulabilir.(digerleri default oldugu icin np)"""

        task = TaskCreate(title="Minimal Task")

        assert task.title == "Minimal Task"
        assert task.description is None
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.MEDIUM

    def test_task_create_empty_title_fails(self):
        """Bos title ile task olusturulamaz."""
        with pytest.raises(ValidationError) as exc_info:
            TaskCreate(title="")

        # Hata Mesaji title uyarisi vermeli
        errors = exc_info.value.errors()
        assert any("title" in str(e["loc"]) for e in errors)

    def test_task_create_title_too_long_fails(self):
        """200 karakterden uzun title kabul edilemez."""
        long_title = "a" * 201

        with pytest.raises(ValidationError) as exc_info:
            TaskCreate(title=long_title)

        errors = exc_info.value.errors()
        assert any("title" in str(e["loc"]) for e in errors)

    def test_task_create_description_too_long_fails(self):
        "1000 karakterden uzun description kabul edilmez."
        long_desciption = "huseyin" * 1000

        with pytest.raises(ValidationError) as exc_info:
            TaskCreate(title="Title", description=long_desciption)

        errors = exc_info.value.errors()
        assert any("description" in str(e["loc"]) for e in errors)

    def test_task_create_invalid_status_fails(self):
        """Gecersiz status kabul edilmez."""
        with pytest.raises(ValidationError) as exc_info:
            TaskCreate(title="Test", status="invalid_status")

    def test_task_create_invalid_priority_fails(self):
        """Gecersiz priority kabul edilmez."""
        with pytest.raises(ValidationError) as exc_info:
            TaskCreate(title="Test", priority="invalid_priority")


class TestTaskUpdate:
    """TaskUpdate model Testleri"""

    def test_task_update_all_fields_optional(self):
        """TaskUpdate'de tum alanlar opsiyonel"""
        # Bos update gecerli olmali
        update = TaskUpdate()

        assert update.title is None
        assert update.description is None
        assert update.status is None
        assert update.priority is None

    def test_task_update_partial(self):
        """Sadece bazi alanlar guncellenebilir."""
        update = TaskUpdate(title="New Title", status=TaskStatus.COMPLETED)

        assert update.title == "New Title"
        assert update.status == TaskStatus.COMPLETED
        assert update.description is None  # Guncellenmedigi icin none olmali
        assert update.priority is None


class TestUserCreate:
    """UserCreate model testleri"""

    def test_valid_user_create(self):
        """Gecerli kullanici olusturulabilir."""
        user = UserCreate(
            email="test@example.com",
            password="securepassword123",
            full_name="Test User",
        )

        assert user.email == "test@example.com"
        assert user.password == "securepassword123"
        assert user.full_name == "Test User"

    def test_user_create_without_full_name(self):
        """full_name olmadan kullanici olusturabilir."""

        user = UserCreate(email="test@example.com", password="securepassword123")

        assert user.full_name is None

    def test_user_create_invalid_email_fails(self):
        """Gecersiz Email kabul edilmez."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(email="not-an-email", password="securepassword123")

        errors = exc_info.value.errors()
        assert any("email" in str(e["loc"]) for e in errors)

    def test_user_create_short_password_fails(self):
        """8 karakterden kisa sifre kabul edilmez."""
        with pytest.raises(ValidationError) as exc_info:
            UserCreate(email="test@example.com", password="short")

        errors = exc_info.value.errors()
        assert any("password" in str(e["loc"]) for e in errors)


class TestUserLogin:
    """UserLogin model testleri"""

    def test_valid_user_login(self):
        """Gecerli login verisi olusturulabilir."""
        login = UserLogin(email="test@example.com", password="anypassword")

        assert login.email == "test@example.com"
        assert login.password == "anypassword"

    def test_user_login_invalid_email_fails(self):
        """Gecersiz email ile login denemesi basarisiz"""
        with pytest.raises(ValidationError):
            UserLogin(email="invalid", password="password")
