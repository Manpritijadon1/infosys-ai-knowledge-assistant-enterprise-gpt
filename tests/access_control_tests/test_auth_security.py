import io
import uuid
import pytest
from backend.database.models import User
from backend.database.seed_admin import provision_admin
from tests.access_control_tests.conftest import TestingSessionLocal, client


def generate_unique_email(prefix: str = "test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@infosys.com"


class TestAuthenticationAndSecurity:
    """Phase 1 Security & Authentication Test Suite."""

    def test_01_valid_user_login_and_jwt_retrieval(self):
        email, pwd = generate_unique_email("login"), "SecurePassword123!"
        assert client.post("/auth/register", json={"full_name": "Valid User", "email": email, "password": pwd}).status_code == 201

        res = client.post("/auth/login", json={"email": email, "password": pwd})
        assert res.status_code == 200
        data = res.json()
        assert data["access_token"] and data["token_type"] == "bearer"
        assert data["user"]["email"] == email.lower() and data["user"]["role"] == "Employee"

    def test_02_invalid_password_rejection(self):
        email, pwd = generate_unique_email("bad_pass"), "CorrectPassword123!"
        client.post("/auth/register", json={"full_name": "User", "email": email, "password": pwd})

        res = client.post("/auth/login", json={"email": email, "password": "WrongPassword999!"})
        assert res.status_code == 401
        assert "Invalid email or password" in res.json()["detail"]

    def test_03_unregistered_email_login_rejection(self):
        res = client.post("/auth/login", json={"email": generate_unique_email("nonexistent"), "password": "AnyPassword123!"})
        assert res.status_code == 401
        assert "Invalid email or password" in res.json()["detail"]

    def test_04_duplicate_registration_handling(self):
        email = generate_unique_email("dup")
        payload = {"full_name": "User", "email": email, "password": "Password123!"}
        assert client.post("/auth/register", json=payload).status_code == 201

        res = client.post("/auth/register", json=payload)
        assert res.status_code == 400
        assert "Email is already registered" in res.json()["detail"]

    def test_05_public_registration_strictly_assigns_employee_role(self):
        email = generate_unique_email("priv_esc")
        res = client.post("/auth/register", json={"full_name": "Attacker", "email": email, "password": "Password123!", "role": "Admin"})
        assert res.status_code == 201 and res.json()["role"] == "Employee"

        with TestingSessionLocal() as db:
            user = db.query(User).filter_by(email=email.lower()).first()
            assert user and user.role.name == "Employee"

    def test_06_admin_provisioning_script_flow(self):
        admin_email, admin_pass = generate_unique_email("sys_admin"), "AdminSuperSecret2026!"
        with TestingSessionLocal() as db:
            admin = provision_admin(full_name="Admin", email=admin_email, password=admin_pass, db=db)
            assert admin.id and admin.role.name == "Admin"

            with pytest.raises(ValueError, match="already exists"):
                provision_admin(full_name="Dup", email=admin_email, password="OtherPassword123!", db=db)

            with pytest.raises(ValueError, match="at least 8 characters"):
                provision_admin(full_name="Short", email=generate_unique_email("short"), password="short", db=db)

    def test_07_employee_receiving_403_on_document_upload(self):
        email, pwd = generate_unique_email("emp_up"), "EmployeePassword123!"
        client.post("/auth/register", json={"full_name": "Emp", "email": email, "password": pwd})
        token = client.post("/auth/login", json={"email": email, "password": pwd}).json()["access_token"]

        res = client.post(
            "/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            data={"title": "Doc", "department": "HR", "document_type": "Policy"},
            files={"file": ("test.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        )
        assert res.status_code == 403
        assert "Admin access required" in res.json()["detail"]

    def test_08_admin_authorized_for_document_upload_route(self):
        email, pwd = generate_unique_email("adm_up"), "AuthorizedAdmin2026!"
        with TestingSessionLocal() as db:
            provision_admin(full_name="Admin", email=email, password=pwd, db=db)

        token = client.post("/auth/login", json={"email": email, "password": pwd}).json()["access_token"]
        res = client.get("/admin/test", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.json()["role"] == "Admin" and res.json()["message"] == "Admin access granted"