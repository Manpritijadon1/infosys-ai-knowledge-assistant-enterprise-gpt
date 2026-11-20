import uuid
import pytest
from fastapi.testclient import TestClient
from backend.api.main import app
from backend.database.models import Document, DocumentChunk, Role, User
from backend.database.seed_roles import DEFAULT_ROLES
from backend.auth.security import hash_password
from tests.access_control_tests.conftest import TestingSessionLocal, client


def create_user_helper(role_name: str, password: str = "Password123!") -> tuple[str, str, str]:
    email = f"phase2_{uuid.uuid4().hex[:8]}@infosys.com"
    with TestingSessionLocal() as session:
        role = session.query(Role).filter(Role.name == role_name).first()
        user = User(
            full_name=f"{role_name} User",
            email=email,
            hashed_password=hash_password(password),
            role_id=role.id,
            is_active=True,
        )
        session.add(user)
        session.commit()

    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    return email, password, res.json()["access_token"]


class TestPhase2PasswordAndDocuments:
    """Phase 2 Password Security & Document Management RBAC Test Suite."""

    def test_01_seed_roles_contains_only_admin_and_employee(self):
        assert "Employer" not in DEFAULT_ROLES
        assert {"Admin", "Employee"}.issubset(DEFAULT_ROLES)
        assert len(DEFAULT_ROLES) == 2

    def test_02_password_change_rejects_incorrect_current_password(self):
        _, _, token = create_user_helper("Employee", "InitialPass123!")
        res = client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "WrongPassword999!", "new_password": "NewValidPassword123!"},
        )
        assert res.status_code == 400
        assert "Current password is incorrect" in res.json()["detail"]

    def test_03_password_change_rejects_same_password(self):
        _, current_pw, token = create_user_helper("Employee", "SamePassword123!")
        res = client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": current_pw, "new_password": current_pw},
        )
        assert res.status_code == 400
        assert "New password cannot be the same as current password" in res.json()["detail"]

    def test_04_password_change_rejects_short_new_password(self):
        _, current_pw, token = create_user_helper("Employee", "CurrentPass123!")
        res = client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": current_pw, "new_password": "short"},
        )
        assert res.status_code == 422

    def test_05_password_change_success_and_login_flow(self):
        email, old_pw, token = create_user_helper("Employee", "OldPassword123!")
        new_pw = "NewSecurePassword456!"

        change_res = client.post(
            "/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": old_pw, "new_password": new_pw},
        )
        assert change_res.status_code == 200
        assert change_res.json()["message"] == "Password updated successfully"

        assert client.post("/auth/login", json={"email": email, "password": old_pw}).status_code == 401
        assert "access_token" in client.post("/auth/login", json={"email": email, "password": new_pw}).json()

    def test_06_employee_and_admin_can_list_documents(self):
        _, _, emp_token = create_user_helper("Employee")
        _, _, admin_token = create_user_helper("Admin")

        with TestingSessionLocal() as session:
            admin_user = session.query(User).filter(User.role.has(name="Admin")).first()
            doc = Document(
                document_id="DOC-TEST-P2",
                title="Test Policy Manual",
                filename="test_policy.pdf",
                department="HR",
                document_type="Policy",
                storage_key="/tmp/nonexistent_test.pdf",
                access_scope="all_users",
                uploaded_by=admin_user.id,
            )
            session.add(doc)
            session.flush()
            session.add_all([
                DocumentChunk(document_id=doc.id, chunk_index=0, page_number=1, content="Chunk 1"),
                DocumentChunk(document_id=doc.id, chunk_index=1, page_number=3, content="Chunk 2"),
            ])
            session.commit()

        for token in [emp_token, admin_token]:
            res = client.get("/documents", headers={"Authorization": f"Bearer {token}"})
            assert res.status_code == 200
            if token == emp_token:
                matched = next((d for d in res.json() if d["document_id"] == "DOC-TEST-P2"), None)
                assert matched and matched["title"] == "Test Policy Manual"
                assert matched["page_count"] == 3 and matched["chunk_count"] == 2

    def test_07_employee_cannot_delete_document(self):
        _, _, emp_token = create_user_helper("Employee")
        with TestingSessionLocal() as session:
            doc_id = session.query(Document).first().id

        res = client.delete(f"/documents/{doc_id}", headers={"Authorization": f"Bearer {emp_token}"})
        assert res.status_code == 403
        assert res.json()["detail"] == "Admin access required"

    def test_08_unauthenticated_cannot_delete_document(self):
        assert client.delete("/documents/1").status_code == 401

    def test_09_admin_delete_nonexistent_document_returns_404(self):
        _, _, admin_token = create_user_helper("Admin")
        res = client.delete("/documents/999999", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 404
        assert res.json()["detail"] == "Document not found"

    def test_10_admin_can_delete_document_and_cascade_chunks(self):
        _, _, admin_token = create_user_helper("Admin")

        with TestingSessionLocal() as session:
            admin_user = session.query(User).filter(User.role.has(name="Admin")).first()
            doc = Document(
                document_id="DOC-TO-DELETE",
                title="Disposable Document",
                filename="disposable.pdf",
                department="General",
                document_type="Memo",
                storage_key="/tmp/disposable.pdf",
                access_scope="all_users",
                uploaded_by=admin_user.id,
            )
            session.add(doc)
            session.flush()
            session.add(DocumentChunk(document_id=doc.id, chunk_index=0, page_number=1, content="Disposable chunk"))
            session.commit()
            target_id = doc.id

        res = client.delete(f"/documents/{target_id}", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        assert res.json()["message"] == "Document deleted successfully"

        with TestingSessionLocal() as session:
            assert session.query(Document).filter_by(id=target_id).first() is None
            assert session.query(DocumentChunk).filter_by(document_id=target_id).count() == 0