path = r'C:\Users\Administrator\Desktop\AI_Intelligence_baseline_scaffold\AI Intelligence\Research intelligence v2\tests\test_api.py'
with open(path, 'r') as f:
    content = f.read()

# Replace test_rag_with_valid_token_and_actor_context_passes_auth
old1 = '''def test_rag_with_valid_token_and_actor_context_passes_auth():
    """RAG endpoint with valid token and actor context passes auth (DB not configured).

    Auth and actor context headers are accepted (not 401/400).
    DB is not configured so RAG execution fails at connection level,
    but that\'s a different layer.
    """
    from unittest.mock import patch

    from oau_ai.db.session import get_database_url

    with patch.object(
        get_database_url,
        "__call__",
        return_value="postgresql+psycopg://fake:fake@localhost:5432/fake",
    ):
        client = TestClient(app)
        response = client.post(
            "/api/v2/rag/ask",
            json={"question": "What is machine learning?"},
            headers={
                "Authorization": "Bearer test-internal-token-123",
                "x-user-id": "user-123",
                "x-roles": "student,researcher",
                "x-department": "Computer Science",
                "x-trace-id": "trace-abc-123",
            },
        )
    # Auth and actor context are accepted (not 401/400).
    assert response.status_code not in (400, 401)'''

new1 = '''def test_rag_with_valid_token_and_actor_context_passes_auth():
    """RAG endpoint with valid token and actor context passes auth (DB not configured).

    Auth and actor context headers are accepted (not 401/400).
    DB is not configured so RAG execution fails at connection level,
    but that\'s a different layer.
    """
    from unittest.mock import patch

    from oau_ai.db.session import get_database_url

    with patch(
        "oau_ai.db.session.get_database_url",
        return_value="postgresql+psycopg://fake:fake@localhost:5432/fake",
    ):
        client = TestClient(app)
        response = client.post(
            "/api/v2/rag/ask",
            json={"question": "What is machine learning?"},
            headers={
                "Authorization": "Bearer test-internal-token-123",
                "x-user-id": "user-123",
                "x-roles": "student,researcher",
                "x-department": "Computer Science",
                "x-trace-id": "trace-abc-123",
            },
        )
    # Auth and actor context are accepted (not 401/400).
    assert response.status_code not in (400, 401)'''

content = content.replace(old1, new1)

# Replace test_rag_with_x_roles_defaults_to_student
old2 = '''def test_rag_with_x_roles_defaults_to_student():
    """RAG endpoint defaults roles to ['student'] when x-roles header is missing."""
    from oau_ai.db.session import get_database_url

    with patch.object(
        get_database_url,
        "__call__",
        return_value="postgresql+psycopg://fake:fake@localhost:5432/fake",
    ):
        client = TestClient(app)
        response = client.post(
            "/api/v2/rag/ask",
            json={"question": "Hello"},
            headers={
                "Authorization": "Bearer test-internal-token-123",
                "x-user-id": "user-123",
                "x-department": "Computer Science",
            },
        )
    # Missing x-roles should default to ["student"], not 400/401
    assert response.status_code not in (400, 401)'''

new2 = '''def test_rag_with_x_roles_defaults_to_student():
    """RAG endpoint defaults roles to ['student'] when x-roles header is missing."""
    from oau_ai.db.session import get_database_url

    with patch(
        "oau_ai.db.session.get_database_url",
        return_value="postgresql+psycopg://fake:fake@localhost:5432/fake",
    ):
        client = TestClient(app)
        response = client.post(
            "/api/v2/rag/ask",
            json={"question": "Hello"},
            headers={
                "Authorization": "Bearer test-internal-token-123",
                "x-user-id": "user-123",
                "x-department": "Computer Science",
            },
        )
    # Missing x-roles should default to ["student"], not 400/401
    assert response.status_code not in (400, 401)'''

content = content.replace(old2, new2)

with open(path, 'w') as f:
    f.write(content)
print('Done writing test_api.py')
print('Contains new-style patch:', '"oau_ai.db.session.get_database_url"' in content)
print('Contains old-style patch.object:', 'patch.object(get_database_url' in content)