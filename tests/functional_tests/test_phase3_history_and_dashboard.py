import uuid
import pytest
from tests.access_control_tests.conftest import TestingSessionLocal, client
from backend.database.models import Document, QueryHistory, Role, User
from backend.auth.security import hash_password


def create_user_helper(role_name: str = "Employee", password: str = "Password123!") -> tuple[str, str, str, int]:
    email = f"p3_{uuid.uuid4().hex[:8]}@infosys.com"
    with TestingSessionLocal() as session:
        role = session.query(Role).filter_by(name=role_name).first()
        user = User(
            full_name=f"{role_name} User",
            email=email,
            hashed_password=hash_password(password),
            role_id=role.id,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id

    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200
    return email, password, res.json()["access_token"], user_id


class TestPhase3HistoryAndDashboard:
    """Phase 3: Database Query History Persistence & Live Analytics Test Suite."""

    def test_01_new_user_has_zero_queries_and_zero_answered_rate(self):
        _, _, token, _ = create_user_helper()

        hist = client.get("/queries/history", headers={"Authorization": f"Bearer {token}"})
        assert hist.status_code == 200 and hist.json() == []

        stats = client.get("/analytics/dashboard-stats", headers={"Authorization": f"Bearer {token}"}).json()
        assert stats["user_recent_queries_count"] == 0
        assert stats["answered_rate"] == 0.0
        assert stats["recent_queries"] == []

    def test_02_post_query_persists_query_history_in_database(self):
        _, _, token, user_id = create_user_helper()
        res = client.post(
            "/query",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "What are the rules regarding annual leaves?", "department": "HR"},
        )
        assert res.status_code == 200
        query_id = res.json()["query_id"]

        with TestingSessionLocal() as session:
            record = session.query(QueryHistory).filter_by(id=query_id).first()
            assert record and record.user_id == user_id and record.department == "HR"

    def test_03_query_history_is_isolated_between_users(self):
        _, _, token_a, _ = create_user_helper()
        _, _, token_b, _ = create_user_helper()

        client.post("/query", headers={"Authorization": f"Bearer {token_a}"}, json={"question": "User A bonus", "department": "Finance"})
        client.post("/query", headers={"Authorization": f"Bearer {token_b}"}, json={"question": "User B travel", "department": "IT"})

        res_a = client.get("/queries/history", headers={"Authorization": f"Bearer {token_a}"}).json()
        res_b = client.get("/queries/history", headers={"Authorization": f"Bearer {token_b}"}).json()

        assert any(q["question"] == "User A bonus" for q in res_a)
        assert not any(q["question"] == "User B travel" for q in res_a)
        assert any(q["question"] == "User B travel" for q in res_b)
        assert not any(q["question"] == "User A bonus" for q in res_b)

    def test_04_user_cannot_delete_another_users_query(self):
        _, _, token_a, _ = create_user_helper()
        _, _, token_b, _ = create_user_helper()

        b_id = client.post("/query", headers={"Authorization": f"Bearer {token_b}"}, json={"question": "Protected"}).json()["query_id"]

        del_res = client.delete(f"/queries/history/{b_id}", headers={"Authorization": f"Bearer {token_a}"})
        assert del_res.status_code == 404
        assert del_res.json()["detail"] == "Query history item not found"

        with TestingSessionLocal() as session:
            assert session.query(QueryHistory).filter_by(id=b_id).first() is not None

    def test_05_clear_history_clears_only_authenticated_users_records(self):
        _, _, token_a, id_a = create_user_helper()
        _, _, token_b, id_b = create_user_helper()

        with TestingSessionLocal() as session:
            session.add_all([
                QueryHistory(user_id=id_a, question="Question A1", answer="Ans 1"),
                QueryHistory(user_id=id_a, question="Question A2", answer="Ans 2"),
                QueryHistory(user_id=id_b, question="Question B1", answer="Ans 3"),
            ])
            session.commit()

        clear_res = client.delete("/queries/history", headers={"Authorization": f"Bearer {token_a}"})
        assert clear_res.status_code == 200 and clear_res.json()["deleted_count"] == 2
        assert client.get("/queries/history", headers={"Authorization": f"Bearer {token_a}"}).json() == []

        hist_b = client.get("/queries/history", headers={"Authorization": f"Bearer {token_b}"}).json()
        assert any(q["question"] == "Question B1" for q in hist_b)

    def test_06_dashboard_stats_computes_real_metrics(self):
        _, _, token, user_id = create_user_helper()

        with TestingSessionLocal() as session:
            session.add_all([
                Document(document_id="DOC-STATS-1", title="Finance", filename="fin.pdf", department="Finance", document_type="Policy", storage_key="/tmp/fin.pdf", uploaded_by=user_id),
                Document(document_id="DOC-STATS-2", title="Eng", filename="eng.pdf", department="Engineering", document_type="Manual", storage_key="/tmp/eng.pdf", uploaded_by=user_id),
                QueryHistory(user_id=user_id, question="Grounded", answer="Found", has_sufficient_evidence=True),
                QueryHistory(user_id=user_id, question="Ungrounded", answer="Not found", has_sufficient_evidence=False)
            ])
            session.commit()

        stats = client.get("/analytics/dashboard-stats", headers={"Authorization": f"Bearer {token}"}).json()
        assert stats["total_documents"] >= 2
        assert stats["total_departments"] >= 2
        assert stats["user_recent_queries_count"] == 2
        assert stats["answered_rate"] == 50.0
        assert len(stats["recent_queries"]) == 2
        assert len(stats["recent_documents"]) >= 2

    def test_07_unauthenticated_requests_are_rejected(self):
        assert client.get("/queries/history").status_code == 401
        assert client.delete("/queries/history").status_code == 401
        assert client.delete("/queries/history/1").status_code == 401
        assert client.get("/analytics/dashboard-stats").status_code == 401