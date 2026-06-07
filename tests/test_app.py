import io

import pytest

import app as mail_app


@pytest.fixture
def client():
    mail_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with mail_app.app.test_client() as test_client:
        yield test_client


def _upload_csv(client, csv_text: str):
    data = {
        "file": (io.BytesIO(csv_text.encode("utf-8")), "recipients.csv"),
    }
    return client.post("/upload", data=data, content_type="multipart/form-data")


def _set_session_data(client, rows, headers):
    with client.session_transaction() as sess:
        sess["rows"] = rows
        sess["headers"] = headers


class FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.logged_in = None
        self.sent_messages = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def login(self, gmail, app_password):
        self.logged_in = (gmail, app_password)

    def sendmail(self, sender, recipients, message):
        self.sent_messages.append(
            {
                "sender": sender,
                "recipients": recipients,
                "message": message,
            }
        )


class AuthFailSMTP(FakeSMTP):
    def login(self, gmail, app_password):
        raise mail_app.smtplib.SMTPAuthenticationError(535, b"bad credentials")


def test_index_route_renders(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Mail Merge" in response.data


def test_upload_requires_file(client):
    response = client.post("/upload", data={}, content_type="multipart/form-data")

    assert response.status_code == 400
    assert response.get_json()["error"] == "No file provided"


def test_upload_csv_parses_and_returns_preview(client):
    csv_text = "Name,Email,Lead Name,Lead Email\nAlice,alice@example.com,Bob,bob@example.com\n"

    response = _upload_csv(client, csv_text)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["headers"] == ["Name", "Email", "Lead Name", "Lead Email"]
    assert payload["total"] == 1
    assert payload["rows"][0]["Name"] == "Alice"


def test_send_requires_credentials(client):
    _set_session_data(client, [{"Name": "Alice", "Email": "alice@example.com"}], ["Name", "Email"])

    response = client.post(
        "/send",
        json={
            "gmail": "",
            "app_password": "",
            "subject": "Hi {{Name}}",
            "body": "Hello",
        },
    )

    assert response.status_code == 400
    assert "Gmail credentials missing" in response.get_json()["error"]


def test_send_requires_uploaded_data(client):
    response = client.post(
        "/send",
        json={
            "gmail": "sender@gmail.com",
            "app_password": "app-pass",
            "subject": "Hi",
            "body": "Body",
        },
    )

    assert response.status_code == 400
    assert "No data loaded" in response.get_json()["error"]


def test_send_test_only_sends_to_self(monkeypatch, client):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(mail_app.smtplib, "SMTP_SSL", FakeSMTP)

    rows = [
        {
            "Name": "Alice",
            "Email": "alice@example.com",
            "Lead Name": "Bob",
            "Lead Email": "bob@example.com",
        }
    ]
    headers = ["Name", "Email", "Lead Name", "Lead Email"]
    _set_session_data(client, rows, headers)

    response = client.post(
        "/send",
        json={
            "gmail": "sender@gmail.com",
            "app_password": "app-pass",
            "sender_name": "Sender",
            "subject": "Hi {{Name}}",
            "body": "Hello {{Name}}",
            "col_map": {
                "Name": "Name",
                "Email": "Email",
                "Lead Name": "Lead Name",
                "Lead Email": "Lead Email",
            },
            "delay": 0,
            "test_only": True,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 1
    assert payload["results"][0]["status"] == "sent"
    assert payload["results"][0]["to"] == "sender@gmail.com"

    sent = FakeSMTP.instances[0].sent_messages
    assert len(sent) == 1
    assert sent[0]["recipients"] == ["sender@gmail.com"]


def test_send_all_sends_and_skips_missing_email(monkeypatch, client):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(mail_app.smtplib, "SMTP_SSL", FakeSMTP)

    rows = [
        {
            "Name": "Alice",
            "Email": "alice@example.com",
            "Lead Name": "Bob",
            "Lead Email": "bob@example.com",
        },
        {
            "Name": "Charlie",
            "Email": "",
            "Lead Name": "Dana",
            "Lead Email": "dana@example.com",
        },
    ]
    headers = ["Name", "Email", "Lead Name", "Lead Email"]
    _set_session_data(client, rows, headers)

    response = client.post(
        "/send",
        json={
            "gmail": "sender@gmail.com",
            "app_password": "app-pass",
            "sender_name": "Sender",
            "subject": "Hi {{Name}}",
            "body": "Hello {{Lead Name}}",
            "col_map": {
                "Name": "Name",
                "Email": "Email",
                "Lead Name": "Lead Name",
                "Lead Email": "Lead Email",
            },
            "delay": 0,
            "test_only": False,
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 2
    assert payload["results"][0]["status"] == "sent"
    assert payload["results"][1]["status"] == "skipped"

    sent = FakeSMTP.instances[0].sent_messages
    assert len(sent) == 1
    assert sent[0]["recipients"] == ["alice@example.com", "bob@example.com"]


def test_send_handles_authentication_error(monkeypatch, client):
    monkeypatch.setattr(mail_app.smtplib, "SMTP_SSL", AuthFailSMTP)
    _set_session_data(client, [{"Name": "Alice", "Email": "alice@example.com"}], ["Name", "Email"])

    response = client.post(
        "/send",
        json={
            "gmail": "sender@gmail.com",
            "app_password": "wrong-pass",
            "subject": "Hi {{Name}}",
            "body": "Hello",
            "delay": 0,
        },
    )

    assert response.status_code == 401
    assert "Authentication failed" in response.get_json()["error"]
