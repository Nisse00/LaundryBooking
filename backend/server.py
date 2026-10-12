"""Flask API for the laundry booking system."""

import hmac
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from functools import wraps
from pathlib import Path

from flask import Blueprint, Flask, current_app, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY_FILE = BASE_DIR / ".secret_key"

# Time slots 1-3 are 08:00-12:00, 12:00-16:00 and 16:00-20:00
SLOTS = (1, 2, 3)
MIN_PASSWORD_LENGTH = 8
MAX_ACTIVE_BOOKINGS = 3
HASH_PREFIXES = ("scrypt:", "pbkdf2:")

SCHEMA = """
    CREATE TABLE IF NOT EXISTS laundry_users (
        username TEXT NOT NULL PRIMARY KEY,
        password TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        booking_date TEXT NOT NULL,
        booking_time INTEGER NOT NULL,
        FOREIGN KEY (username) REFERENCES laundry_users(username)
    );
    -- An index rather than a table constraint so that databases created
    -- before the constraint existed get it too. This is what prevents
    -- two people from booking the same slot.
    CREATE UNIQUE INDEX IF NOT EXISTS bookings_slot
        ON bookings (booking_date, booking_time);
"""

api = Blueprint("laundry", __name__, url_prefix="/api/laundry")


def load_secret_key():
    """Use SECRET_KEY from the environment, otherwise a random key kept on disk."""
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    if not SECRET_KEY_FILE.exists():
        SECRET_KEY_FILE.write_text(secrets.token_hex(32))
        SECRET_KEY_FILE.chmod(0o600)
    return SECRET_KEY_FILE.read_text().strip()


def create_app(config=None):
    """Application factory. `config` overrides the defaults, e.g. in tests."""
    app = Flask(__name__)
    app.config.update(
        DATABASE=os.environ.get("LAUNDRY_DATABASE", BASE_DIR / "laundry.db"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    app.config.update(config or {})
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = load_secret_key()

    with closing(connect(app.config["DATABASE"])) as conn:
        conn.executescript(SCHEMA)

    app.teardown_appcontext(close_db)
    app.register_blueprint(api)
    return app


def connect(database):
    # isolation_level=None: we control transactions ourselves (see create_booking)
    conn = sqlite3.connect(database, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def error(message, status):
    return jsonify({"message": message}), status


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            return error("You must be logged in to do that.", 401)
        return view(*args, **kwargs)

    return wrapped


def credentials():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        return "", ""
    return username.strip(), password


def log_in(username):
    session.clear()
    session["username"] = username
    session.permanent = True


def last_bookable_day(today):
    """The calendar shows this month and the next one."""
    first_of_month_after_next = (today.replace(day=1) + timedelta(days=62)).replace(day=1)
    return first_of_month_after_next - timedelta(days=1)


def parse_slot(booking_date, slot):
    """Validate a (date, slot) pair, returning an error message or None."""
    try:
        day = date.fromisoformat(booking_date)
    except (TypeError, ValueError):
        return "Invalid date."
    if isinstance(slot, bool) or slot not in SLOTS:
        return "Invalid time slot."
    today = date.today()
    if day < today:
        return "You cannot book or cancel a time slot in the past."
    if day > last_bookable_day(today):
        return "You can only book this month and the next."
    return None


@api.post("/register")
def register():
    username, password = credentials()
    if not username or not password:
        return error("Username and password are required.", 400)
    if len(password) < MIN_PASSWORD_LENGTH:
        return error(f"The password must be at least {MIN_PASSWORD_LENGTH} characters.", 400)

    try:
        get_db().execute(
            "INSERT INTO laundry_users (username, password) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
    except sqlite3.IntegrityError:
        return error("That username is already taken.", 409)

    log_in(username)
    return jsonify({"username": username}), 201


@api.post("/login")
def login():
    username, password = credentials()
    db = get_db()
    row = db.execute(
        "SELECT password FROM laundry_users WHERE username = ?", (username,)
    ).fetchone()

    valid = False
    if row is not None:
        stored = row["password"]
        if stored.startswith(HASH_PREFIXES):
            valid = check_password_hash(stored, password)
        elif hmac.compare_digest(stored.encode(), password.encode()):
            # Account from before passwords were hashed: upgrade it now
            valid = True
            db.execute(
                "UPDATE laundry_users SET password = ? WHERE username = ?",
                (generate_password_hash(password), username),
            )

    if not valid:
        return error("Wrong username or password.", 401)

    log_in(username)
    return jsonify({"username": username})


@api.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@api.get("/user")
def current_user():
    return jsonify({"username": session.get("username")})


@api.get("/bookings")
def list_bookings():
    """All bookings from today onwards. `mine` marks the caller's own.

    Who booked a slot is only revealed to logged-in users.
    """
    rows = (
        get_db()
        .execute(
            "SELECT booking_date, booking_time, username FROM bookings"
            " WHERE booking_date >= ? ORDER BY booking_date, booking_time",
            (date.today().isoformat(),),
        )
        .fetchall()
    )
    username = session.get("username")
    return jsonify(
        {
            "bookings": [
                {
                    "date": row["booking_date"],
                    "slot": int(row["booking_time"]),
                    "mine": row["username"] == username,
                    "bookedBy": row["username"] if username else None,
                }
                for row in rows
            ]
        }
    )


@api.post("/bookings")
@login_required
def create_booking():
    data = request.get_json(silent=True) or {}
    booking_date, slot = data.get("date"), data.get("slot")
    problem = parse_slot(booking_date, slot)
    if problem:
        return error(problem, 400)

    username = session["username"]
    db = get_db()
    # IMMEDIATE takes the write lock up front, so the booking limit check and
    # the insert cannot interleave with another request.
    db.execute("BEGIN IMMEDIATE")
    try:
        (active,) = db.execute(
            "SELECT COUNT(*) FROM bookings WHERE username = ? AND booking_date >= ?",
            (username, date.today().isoformat()),
        ).fetchone()
        if active >= MAX_ACTIVE_BOOKINGS:
            db.execute("ROLLBACK")
            return error(
                f"You already have {MAX_ACTIVE_BOOKINGS} active bookings."
                " Cancel one before booking another time slot.",
                409,
            )
        db.execute(
            "INSERT INTO bookings (username, booking_date, booking_time) VALUES (?, ?, ?)",
            (username, booking_date, slot),
        )
        db.execute("COMMIT")
    except sqlite3.IntegrityError:
        db.execute("ROLLBACK")
        return error("That time slot is already booked by someone else.", 409)
    except BaseException:
        db.execute("ROLLBACK")
        raise

    return jsonify({"date": booking_date, "slot": slot, "mine": True, "bookedBy": username}), 201


@api.delete("/bookings/<booking_date>/<int:slot>")
@login_required
def delete_booking(booking_date, slot):
    problem = parse_slot(booking_date, slot)
    if problem:
        return error(problem, 400)

    deleted = (
        get_db()
        .execute(
            "DELETE FROM bookings WHERE username = ? AND booking_date = ? AND booking_time = ?",
            (session["username"], booking_date, slot),
        )
        .rowcount
    )
    if not deleted:
        return error("Booking not found, or it is not yours.", 404)
    return jsonify({"message": "Booking cancelled"})


if __name__ == "__main__":
    create_app().run(host="localhost", port=5001, debug=os.environ.get("FLASK_DEBUG") == "1")
