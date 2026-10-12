import sqlite3
import threading
from datetime import UTC, date, datetime, timedelta

import pytest

import server
from server import MAX_ACTIVE_BOOKINGS, create_app, last_bookable_day

API = "/api/laundry"
PASSWORD = "correct horse"


def day(offset):
    return (server.today() + timedelta(days=offset)).isoformat()


@pytest.fixture
def app(tmp_path):
    return create_app({"DATABASE": tmp_path / "test.db", "SECRET_KEY": "test", "TESTING": True})


@pytest.fixture
def client(app):
    return app.test_client()


def register(app, username):
    """A separate client (own cookie jar) logged in as a new user."""
    client = app.test_client()
    response = client.post(f"{API}/register", json={"username": username, "password": PASSWORD})
    assert response.status_code == 201
    return client


def register_admin(app, username):
    client = register(app, username)
    result = app.test_cli_runner().invoke(args=["set-admin", username])
    assert result.exit_code == 0, result.output
    return client


def book(client, booking_date, slot):
    return client.post(f"{API}/bookings", json={"date": booking_date, "slot": slot})


class TestAccounts:
    def test_register_logs_in(self, app):
        anna = register(app, "anna")
        assert anna.get(f"{API}/user").get_json() == {"username": "anna", "isAdmin": False}

    def test_username_is_trimmed(self, client):
        client.post(f"{API}/register", json={"username": " anna ", "password": PASSWORD})
        assert client.get(f"{API}/user").get_json()["username"] == "anna"

    def test_duplicate_username_is_rejected(self, app, client):
        register(app, "anna")
        response = client.post(f"{API}/register", json={"username": "anna", "password": PASSWORD})
        assert response.status_code == 409

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"username": "anna"},
            {"username": "", "password": PASSWORD},
            {"username": "anna", "password": "short"},
            {"username": 1, "password": PASSWORD},
        ],
    )
    def test_invalid_registration_is_rejected(self, client, payload):
        assert client.post(f"{API}/register", json=payload).status_code == 400

    def test_invite_code_is_required_when_configured(self, tmp_path):
        app = create_app(
            {"DATABASE": tmp_path / "test.db", "SECRET_KEY": "test", "INVITE_CODE": "botan"}
        )
        client = app.test_client()
        account = {"username": "anna", "password": PASSWORD}
        assert client.get(f"{API}/registration").get_json() == {"inviteCodeRequired": True}
        assert client.post(f"{API}/register", json=account).status_code == 403
        wrong = {**account, "inviteCode": "guess"}
        assert client.post(f"{API}/register", json=wrong).status_code == 403
        right = {**account, "inviteCode": " botan "}
        assert client.post(f"{API}/register", json=right).status_code == 201

    def test_no_invite_code_by_default(self, client):
        assert client.get(f"{API}/registration").get_json() == {"inviteCodeRequired": False}

    def test_password_is_stored_hashed(self, app):
        register(app, "anna")
        with sqlite3.connect(app.config["DATABASE"]) as conn:
            (stored,) = conn.execute("SELECT password FROM laundry_users").fetchone()
        assert PASSWORD not in stored

    def test_login_and_logout(self, app, client):
        register(app, "anna")
        credentials = {"username": "anna", "password": PASSWORD}
        assert client.post(f"{API}/login", json=credentials).status_code == 200
        assert client.get(f"{API}/user").get_json()["username"] == "anna"
        assert client.post(f"{API}/logout").status_code == 200
        assert client.get(f"{API}/user").get_json() == {"username": None, "isAdmin": False}

    @pytest.mark.parametrize(
        "credentials",
        [
            {"username": "anna", "password": "wrong password"},
            {"username": "nobody", "password": PASSWORD},
            {},
        ],
    )
    def test_bad_login_is_rejected(self, app, client, credentials):
        register(app, "anna")
        assert client.post(f"{API}/login", json=credentials).status_code == 401

    def test_legacy_plaintext_password_is_upgraded_on_login(self, app, client):
        with sqlite3.connect(app.config["DATABASE"]) as conn:
            conn.execute(
                "INSERT INTO laundry_users (username, password) VALUES ('old', 'plaintext')"
            )
        credentials = {"username": "old", "password": "plaintext"}
        assert client.post(f"{API}/login", json=credentials).status_code == 200
        with sqlite3.connect(app.config["DATABASE"]) as conn:
            (stored,) = conn.execute("SELECT password FROM laundry_users").fetchone()
        assert stored != "plaintext"
        assert app.test_client().post(f"{API}/login", json=credentials).status_code == 200


class TestBookings:
    def test_requires_login(self, client):
        assert book(client, day(1), 1).status_code == 401
        assert client.delete(f"{API}/bookings/{day(1)}/1").status_code == 401

    def test_book_and_list(self, app):
        anna, bert = register(app, "anna"), register(app, "bert")
        assert book(anna, day(1), 2).status_code == 201
        booking = {"date": day(1), "slot": 2, "bookedBy": "anna"}
        assert anna.get(f"{API}/bookings").get_json() == {"bookings": [{**booking, "mine": True}]}
        assert bert.get(f"{API}/bookings").get_json() == {"bookings": [{**booking, "mine": False}]}

    def test_names_are_hidden_when_logged_out(self, app, client):
        book(register(app, "anna"), day(1), 2)
        assert client.get(f"{API}/bookings").get_json() == {
            "bookings": [{"date": day(1), "slot": 2, "mine": False, "bookedBy": None}]
        }

    def test_slot_can_only_be_booked_once(self, app):
        anna, bert = register(app, "anna"), register(app, "bert")
        assert book(anna, day(1), 1).status_code == 201
        assert book(bert, day(1), 1).status_code == 409

    def test_limited_number_of_active_bookings(self, app):
        anna = register(app, "anna")
        for offset in range(1, MAX_ACTIVE_BOOKINGS + 1):
            assert book(anna, day(offset), 1).status_code == 201
        assert book(anna, day(MAX_ACTIVE_BOOKINGS + 1), 1).status_code == 409
        assert anna.delete(f"{API}/bookings/{day(1)}/1").status_code == 200
        assert book(anna, day(MAX_ACTIVE_BOOKINGS + 1), 1).status_code == 201

    def test_past_bookings_do_not_count_towards_the_limit(self, app):
        anna = register(app, "anna")
        with sqlite3.connect(app.config["DATABASE"]) as conn:
            for slot in (1, 2, 3):
                conn.execute(
                    "INSERT INTO bookings (username, booking_date, booking_time)"
                    " VALUES ('anna', ?, ?)",
                    (day(-1), slot),
                )
        assert book(anna, day(1), 1).status_code == 201

    def test_cancel_then_book_again(self, app):
        anna = register(app, "anna")
        book(anna, day(1), 1)
        assert anna.delete(f"{API}/bookings/{day(1)}/1").status_code == 200
        assert book(anna, day(2), 3).status_code == 201

    def test_cannot_cancel_someone_elses_booking(self, app):
        anna, bert = register(app, "anna"), register(app, "bert")
        book(anna, day(1), 1)
        assert bert.delete(f"{API}/bookings/{day(1)}/1").status_code == 404
        assert len(anna.get(f"{API}/bookings").get_json()["bookings"]) == 1

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"date": "not-a-date", "slot": 1},
            {"date": day(1), "slot": 0},
            {"date": day(1), "slot": 4},
            {"date": day(1), "slot": "1"},
            {"date": day(1), "slot": True},
            {"date": day(-1), "slot": 1},
            {"date": day(70), "slot": 1},
        ],
    )
    def test_invalid_booking_is_rejected(self, app, payload):
        anna = register(app, "anna")
        assert anna.post(f"{API}/bookings", json=payload).status_code == 400

    def test_past_bookings_are_not_listed(self, app, client):
        register(app, "anna")
        with sqlite3.connect(app.config["DATABASE"]) as conn:
            conn.execute(
                "INSERT INTO bookings (username, booking_date, booking_time) VALUES ('anna', ?, 1)",
                (day(-1),),
            )
        assert client.get(f"{API}/bookings").get_json() == {"bookings": []}

    def test_simultaneous_requests_for_one_slot(self, app):
        clients = [register(app, f"user{i}") for i in range(8)]
        statuses = []
        threads = [
            threading.Thread(target=lambda c=c: statuses.append(book(c, day(1), 1).status_code))
            for c in clients
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sorted(statuses) == [201] + [409] * 7


class TestAdmin:
    def test_set_admin_command(self, app):
        anna = register_admin(app, "anna")
        assert anna.get(f"{API}/user").get_json() == {"username": "anna", "isAdmin": True}
        assert app.test_cli_runner().invoke(args=["set-admin", "anna", "--remove"]).exit_code == 0
        assert anna.get(f"{API}/user").get_json() == {"username": "anna", "isAdmin": False}
        assert app.test_cli_runner().invoke(args=["set-admin", "nobody"]).exit_code != 0

    def test_existing_database_gets_the_admin_column(self, tmp_path):
        database = tmp_path / "old.db"
        with sqlite3.connect(database) as conn:
            conn.execute(
                "CREATE TABLE laundry_users (username TEXT NOT NULL PRIMARY KEY,"
                " password TEXT NOT NULL)"
            )
            conn.execute("INSERT INTO laundry_users VALUES ('old', 'plaintext')")
        client = create_app({"DATABASE": database, "SECRET_KEY": "test"}).test_client()
        response = client.post(f"{API}/login", json={"username": "old", "password": "plaintext"})
        assert response.get_json() == {"username": "old", "isAdmin": False}

    def test_admin_pages_are_for_admins_only(self, app, client):
        bert = register(app, "bert")
        assert client.get(f"{API}/users").status_code == 401
        assert bert.get(f"{API}/users").status_code == 403
        assert bert.delete(f"{API}/users/bert").status_code == 403

    def test_admin_can_cancel_someone_elses_booking(self, app):
        anna, bert = register_admin(app, "anna"), register(app, "bert")
        book(bert, day(1), 1)
        assert anna.delete(f"{API}/bookings/{day(1)}/1").status_code == 200
        assert bert.get(f"{API}/bookings").get_json() == {"bookings": []}

    def test_list_users(self, app):
        anna, bert = register_admin(app, "anna"), register(app, "bert")
        book(bert, day(1), 1)
        assert anna.get(f"{API}/users").get_json() == {
            "users": [
                {"username": "anna", "isAdmin": True, "activeBookings": 0},
                {"username": "bert", "isAdmin": False, "activeBookings": 1},
            ]
        }

    def test_delete_user(self, app):
        anna, bert = register_admin(app, "anna"), register(app, "odd/name bert")
        book(bert, day(1), 1)
        assert anna.delete(f"{API}/users/odd%2Fname%20bert").status_code == 200
        assert anna.get(f"{API}/bookings").get_json() == {"bookings": []}
        # The deleted user's session stops working
        assert bert.get(f"{API}/user").get_json() == {"username": None, "isAdmin": False}
        assert book(bert, day(1), 1).status_code == 401
        assert anna.delete(f"{API}/users/odd%2Fname%20bert").status_code == 404

    def test_admin_cannot_delete_themselves(self, app):
        anna = register_admin(app, "anna")
        assert anna.delete(f"{API}/users/anna").status_code == 400


class TestPasswordReset:
    NEW_PASSWORD = "battery staple"

    def reset(self, client, username, code, password=NEW_PASSWORD):
        payload = {"username": username, "code": code, "password": password}
        return client.post(f"{API}/reset-password", json=payload)

    def code_for(self, admin, username):
        response = admin.post(f"{API}/users/{username}/reset-code")
        assert response.status_code == 201
        return response.get_json()["code"]

    def test_reset_with_code_from_admin(self, app, client):
        anna = register_admin(app, "anna")
        register(app, "bert")
        code = self.code_for(anna, "bert")
        assert self.reset(client, "bert", code).status_code == 200
        assert client.get(f"{API}/user").get_json()["username"] == "bert"

        fresh = app.test_client()
        old = {"username": "bert", "password": PASSWORD}
        new = {"username": "bert", "password": self.NEW_PASSWORD}
        assert fresh.post(f"{API}/login", json=old).status_code == 401
        assert fresh.post(f"{API}/login", json=new).status_code == 200

    def test_code_works_only_once(self, app, client):
        anna = register_admin(app, "anna")
        code = self.code_for(anna, "anna")
        assert self.reset(client, "anna", code).status_code == 200
        assert self.reset(client, "anna", code).status_code == 400

    def test_new_code_replaces_the_old_one(self, app, client):
        anna = register_admin(app, "anna")
        first, second = self.code_for(anna, "anna"), self.code_for(anna, "anna")
        assert self.reset(client, "anna", first).status_code == 400
        assert self.reset(client, "anna", second).status_code == 200

    def test_wrong_code_or_user_is_rejected(self, app, client):
        anna = register_admin(app, "anna")
        register(app, "bert")
        code = self.code_for(anna, "bert")
        assert self.reset(client, "bert", "guess").status_code == 400
        assert self.reset(client, "anna", code).status_code == 400
        assert self.reset(client, "bert", code, password="short").status_code == 400
        assert client.post(f"{API}/reset-password", json={}).status_code == 400
        # None of the failed attempts used the code up
        assert self.reset(client, "bert", code).status_code == 200

    def test_expired_code_is_rejected(self, app, client, monkeypatch):
        anna = register_admin(app, "anna")
        code = self.code_for(anna, "anna")
        later = server.time.time() + server.RESET_CODE_LIFETIME.total_seconds() + 1
        monkeypatch.setattr(server.time, "time", lambda: later)
        assert self.reset(client, "anna", code).status_code == 400

    def test_only_admins_can_create_codes(self, app, client):
        anna, bert = register_admin(app, "anna"), register(app, "bert")
        assert client.post(f"{API}/users/bert/reset-code").status_code == 401
        assert bert.post(f"{API}/users/bert/reset-code").status_code == 403
        assert anna.post(f"{API}/users/nobody/reset-code").status_code == 404

    def test_reset_code_command(self, app, client):
        register(app, "anna")
        result = app.test_cli_runner().invoke(args=["reset-code", "anna"])
        assert result.exit_code == 0, result.output
        code = result.output.strip().rsplit(" ", 1)[-1]
        assert self.reset(client, "anna", code).status_code == 200
        assert app.test_cli_runner().invoke(args=["reset-code", "nobody"]).exit_code != 0


@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 10, 11), date(2026, 11, 30)),
        (date(2026, 12, 31), date(2027, 1, 31)),
        (date(2028, 1, 31), date(2028, 2, 29)),
    ],
)
def test_last_bookable_day(today, expected):
    assert last_bookable_day(today) == expected


def test_today_follows_swedish_time(monkeypatch):
    class LateEveningUTC(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 7, 1, 22, 30, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(server, "datetime", LateEveningUTC)
    assert server.today() == date(2026, 7, 2)
