from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator


class Role(str, Enum):
    admin = "Admin"
    developer = "Developer"
    reporter = "Reporter"


class Component(str, Enum):
    authentication = "Authentication"
    api = "API"
    backend = "Backend"
    database = "Database"
    frontend = "Frontend"
    infrastructure = "Infrastructure"
    ui = "UI"


class Priority(str, Enum):
    critical = "Critical"
    high = "High"
    medium = "Medium"
    low = "Low"


class Severity(str, Enum):
    critical = "Critical"
    major = "Major"
    minor = "Minor"
    trivial = "Trivial"


class BugStatus(str, Enum):
    new = "New"
    open = "Open"
    in_progress = "In Progress"
    resolved = "Resolved"
    closed = "Closed"
    duplicate = "Duplicate"


PRIORITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def _password_ok(value: str) -> str:
    if len(value.encode()) > 72:
        raise ValueError("Password must be 72 bytes or fewer.")
    if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise ValueError("Password must include a letter and a number.")
    return value


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=10)

    _check_password = field_validator("password")(_password_ok)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=10)

    _check_password = field_validator("password")(_password_ok)


class RoleUpdate(BaseModel):
    role: Role


class Environment(BaseModel):
    os: str = Field(default="", max_length=100)
    browser: str = Field(default="", max_length=100)
    app_version: str = Field(default="", max_length=50)


class BugText(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=10, max_length=10000)
    steps_to_reproduce: str = Field(default="", max_length=10000)
    expected_behavior: str = Field(default="", max_length=5000)
    actual_behavior: str = Field(default="", max_length=5000)
    stack_trace: str = Field(default="", max_length=20000)

    @field_validator("title", "description")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Enter at least a few words.")
        return value


class BugCreate(BugText):
    component: Component | None = None
    severity: Severity | None = None
    environment: Environment = Environment()


class BugUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=200)
    description: str | None = Field(default=None, min_length=10, max_length=10000)
    steps_to_reproduce: str | None = Field(default=None, max_length=10000)
    expected_behavior: str | None = Field(default=None, max_length=5000)
    actual_behavior: str | None = Field(default=None, max_length=5000)
    stack_trace: str | None = Field(default=None, max_length=20000)
    environment: Environment | None = None
    component: Component | None = None
    priority: Priority | None = None
    severity: Severity | None = None
    status: BugStatus | None = None
    assigned_developer: str | None = None


class DuplicateSearch(BaseModel):
    text: str = Field(min_length=10, max_length=20000)


class DuplicateConfirm(BaseModel):
    bug_id: str
    is_duplicate: bool
    matched_bug_id: str | None = Field(default=None, description="Required when is_duplicate is true.")


class TriageDecision(BaseModel):
    component: Component
    priority: Priority
    severity: Severity
    assigned_developer: str | None = None


class DeveloperCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    skills: list[str] = Field(default_factory=list, max_length=30)
    assigned_components: list[Component] = Field(default_factory=list)
