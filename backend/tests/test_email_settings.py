"""Email for label requests: the setup on the Settings tab, and the mail sent when a line is requested."""
import smtplib

import pytest

from tests.conftest import login

SENT: list[dict] = []


class FakeSMTP:
    fail_login = False
    fail_connect = False

    def __init__(self, host, port, timeout=0, context=None):
        if FakeSMTP.fail_connect:
            raise ConnectionRefusedError("refused")
        self.host, self.port, self.tls, self.user = host, port, False, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        self.tls = True

    def login(self, user, pw):
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad")
        self.user, self.pw = user, pw

    def send_message(self, msg):
        SENT.append({"host": self.host, "port": self.port, "tls": self.tls, "user": self.user, "pw": getattr(self, "pw", None),
                     "from": msg["From"], "to": msg["To"], "subject": msg["Subject"], "body": msg.get_content()})


@pytest.fixture(autouse=True)
def smtp(monkeypatch):
    SENT.clear()
    FakeSMTP.fail_login = FakeSMTP.fail_connect = False
    monkeypatch.setattr("app.mailer.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("app.mailer.smtplib.SMTP_SSL", FakeSMTP)


CFG = {"enabled": True, "host": "smtp.sawo.test", "port": 587, "security": "starttls", "username": "labels@sawo.test",
       "password": "s3cret!", "sender_name": "SO Sticker", "sender_email": "labels@sawo.test",
       "receivers": "marketing@sawo.test; design@sawo.test\nmarketing@sawo.test", "app_url": "http://pc01:8090"}


def ask(api):
    return api.post("/api/label-requests", json={"code": "RS-1", "name": "Resale Gift Box", "so": "S00124"})


def test_only_admins_see_or_change_the_email_setup(api):
    login(api, "bob")
    assert api.get("/api/settings/email").status_code == 403
    assert api.put("/api/settings/email", json=CFG).status_code == 403
    assert api.post("/api/settings/email/test", json={}).status_code == 403


def test_the_setup_is_saved_without_ever_sending_the_password_back(api):
    login(api, "alice")
    r = api.put("/api/settings/email", json=CFG)
    assert r.status_code == 200
    out = r.json()
    assert out["receivers"] == ["marketing@sawo.test", "design@sawo.test"] and out["password_set"] is True
    assert "password" not in out and "password_enc" not in out and "s3cret" not in r.text
    assert "s3cret" not in api.get("/api/settings/email").text
    # saving again without a password keeps the saved one
    api.put("/api/settings/email", json={**CFG, "password": ""})
    api.post("/api/settings/email/test", json={})
    assert SENT[-1]["pw"] == "s3cret!"


@pytest.mark.parametrize("change,message", [
    ({"host": ""}, "SMTP server"), ({"sender_email": ""}, "sender"), ({"receivers": ""}, "at least one receiver"),
    ({"receivers": "not-an-email"}, "not a valid email"), ({"port": 993}, "for receiving mail"), ({"port": 70000}, "port"), ({"security": "weird"}, "secured"),
])
def test_a_bad_setup_is_refused_with_a_clear_message(api, change, message):
    login(api, "alice")
    r = api.put("/api/settings/email", json={**CFG, **change})
    assert r.status_code == 422 and message in r.text


def test_a_new_request_emails_the_receivers_from_the_sender(api):
    login(api, "alice")
    api.put("/api/settings/email", json=CFG)
    login(api, "bob")
    ask(api)
    assert len(SENT) == 1
    m = SENT[0]
    assert m["host"] == "smtp.sawo.test" and m["port"] == 587 and m["tls"] is True and m["user"] == "labels@sawo.test"
    assert "labels@sawo.test" in m["from"] and m["to"] == "marketing@sawo.test, design@sawo.test"
    assert m["subject"] == "Label request: RS-1 (SO S00124)"
    assert "Resale Gift Box" in m["body"] and "http://pc01:8090" in m["body"]
    ask(api)  # already requested: nobody is emailed twice
    assert len(SENT) == 1
    login(api, "alice")
    assert "Sent to 2 receiver" in api.get("/api/settings/email").json()["last_status"]


def test_nothing_is_sent_when_it_is_switched_off_or_not_set_up(api):
    login(api, "bob")
    ask(api)
    assert SENT == []
    login(api, "alice")
    api.put("/api/settings/email", json={**CFG, "enabled": False})
    login(api, "bob")
    api.post("/api/label-requests", json={"code": "ZZ-9", "name": "x", "so": "S1"})
    assert SENT == []


def test_a_mail_failure_never_breaks_the_request_and_is_shown_to_the_admin(api):
    login(api, "alice")
    api.put("/api/settings/email", json=CFG)
    FakeSMTP.fail_login = True
    login(api, "bob")
    assert ask(api).status_code == 200  # the request itself is saved
    login(api, "alice")
    assert "FAILED" in api.get("/api/settings/email").json()["last_status"] and "username or password" in api.get("/api/settings/email").json()["last_status"]


def test_the_test_button_reports_success_and_problems(api):
    login(api, "alice")
    api.put("/api/settings/email", json=CFG)
    ok = api.post("/api/settings/email/test", json={"to": "me@sawo.test"})
    assert ok.status_code == 200 and SENT[-1]["to"] == "me@sawo.test" and SENT[-1]["subject"].endswith("test email")
    # the form as it is on screen is tested without saving it first
    form = {**CFG, "host": "mail.other.test", "port": 465, "security": "ssl", "password": "typed-now"}
    api.post("/api/settings/email/test", json={"config": form})
    assert SENT[-1]["host"] == "mail.other.test" and SENT[-1]["port"] == 465 and SENT[-1]["pw"] == "typed-now"
    assert api.get("/api/settings/email").json()["host"] == "smtp.sawo.test"  # ...and nothing was saved by the test
    noname = api.post("/api/settings/email/test", json={"config": {**CFG, "sender_email": ""}})
    assert noname.status_code == 502 and "sender email address" in noname.text  # the missing field is named
    FakeSMTP.fail_connect = True
    bad = api.post("/api/settings/email/test", json={})
    assert bad.status_code == 502 and "Cannot reach the mail server" in bad.text
    assert api.post("/api/settings/email/test", json={"to": "nope"}).status_code == 422
