"""Flask API for the laundry booking system."""

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

import click
from flask import Blueprint, Flask, current_app, g, jsonify, request, session
from flask.cli import with_appcontext
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY_FILE = BASE_DIR / ".secret_key"

# "Today" is decided by the clock in Lund, wherever the server happens to run
TIMEZONE = ZoneInfo("Europe/Stockholm")
# Time slots 1-3 are 08:00-12:00, 12:00-16:00 and 16:00-20:00
SLOTS = (1, 2, 3)
MIN_PASSWORD_LENGTH = 8
MAX_ACTIVE_BOOKINGS = 3
RESET_CODE_LIFETIME = timedelta(hours=24)
# After this many wrong passwords for one username, logging in to it is
# blocked until the oldest attempt is older than the window
MAX_FAILED_LOGINS = 10
FAILED_LOGIN_WINDOW = timedelta(minutes=15)
HASH_PREFIXES = ("scrypt:", "pbkdf2:")

SCHEMA = """
    CREATE TABLE IF NOT EXISTS laundry_users (
        username TEXT NOT NULL PRIMARY KEY,
        password TEXT NOT NULL,
        is_admin INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        booking_date TEXT NOT NULL,
        booking_time INTEGER NOT NULL,
        FOREIGN KEY (username) REFERENCES laundry_users(username)
    );
    -- One-time codes for choosing a new password, handed out by an admin.
    -- Only a hash of the code is stored; expires_at is a Unix timestamp.
    CREATE TABLE IF NOT EXISTS password_resets (
        username TEXT NOT NULL PRIMARY KEY,
        code_hash TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        FOREIGN KEY (username) REFERENCES laundry_users(username)
    );
    -- Wrong passwords, to slow down guessing; attempted_at is a Unix timestamp.
    -- The username need not exist.
    CREATE TABLE IF NOT EXISTS failed_logins (
        username TEXT NOT NULL,
        attempted_at INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS failed_logins_username ON failed_logins (username);
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
        BACKUP_DIR=os.environ.get("LAUNDRY_BACKUP_DIR", BASE_DIR / "backups"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        # Creating an account requires this code when it is set
        INVITE_CODE=os.environ.get("INVITE_CODE", ""),
    )
    app.config.update(config or {})
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = load_secret_key()

    with closing(connect(app.config["DATABASE"])) as conn:
        conn.executescript(SCHEMA)
        # Databases created before there were admins lack the column
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(laundry_users)")]
        if "is_admin" not in columns:
            conn.execute("ALTER TABLE laundry_users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")

    app.teardown_appcontext(close_db)
    app.register_blueprint(api)
    app.cli.add_command(set_admin)
    app.cli.add_command(reset_code)
    app.cli.add_command(backup)
    return app


@click.command("set-admin")
@click.argument("username")
@click.option("--remove", is_flag=True, help="Take the admin role away instead.")
@with_appcontext
def set_admin(username, remove):
    """Make USERNAME an admin: flask --app server set-admin USERNAME"""
    updated = (
        get_db()
        .execute(
            "UPDATE laundry_users SET is_admin = ? WHERE username = ?",
            (0 if remove else 1, username),
        )
        .rowcount
    )
    if not updated:
        raise click.ClickException(f"There is no user called {username!r}.")
    click.echo(f"{username} is {'no longer' if remove else 'now'} an admin.")


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


@click.command("backup")
@click.option("--keep", default=14, show_default=True, help="Number of backups to keep.")
@with_appcontext
def backup(keep):
    """Copy the database to the backup folder, one file per day.

    Safe to run while the server is in use. Meant for a daily cron job.
    """
    folder = Path(current_app.config["BACKUP_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"laundry-{today().isoformat()}.db"
    with closing(sqlite3.connect(target)) as copy:
        get_db().backup(copy)
    # The date in the name makes alphabetical order the same as by age
    for old in sorted(folder.glob("laundry-*.db"))[: -max(keep, 1)]:
        old.unlink()
    click.echo(f"Backed up to {target}")


@click.command("reset-code")
@click.argument("username")
@with_appcontext
def reset_code(username):
    """Print a code that lets USERNAME choose a new password.

    For when an admin has forgotten their own password; otherwise use the
    Manage users page.
    """
    code = create_reset_code(username)
    if code is None:
        raise click.ClickException(f"There is no user called {username!r}.")
    click.echo(f"Reset code for {username}: {code}")


def hash_reset_code(code):
    # The code is long and random, so a fast hash is enough
    return hashlib.sha256(code.encode()).hexdigest()


def create_reset_code(username):
    """Store a new reset code for the user, replacing any old one. None if no such user."""
    db = get_db()
    if not db.execute("SELECT 1 FROM laundry_users WHERE username = ?", (username,)).fetchone():
        return None
    code = secrets.token_urlsafe(9)
    db.execute(
        "INSERT OR REPLACE INTO password_resets (username, code_hash, expires_at) VALUES (?, ?, ?)",
        (username, hash_reset_code(code), int(time.time() + RESET_CODE_LIFETIME.total_seconds())),
    )
    return code


def error(message, status):
    return jsonify({"message": message}), status


def logged_in_user():
    """The row of the logged-in user, or None.

    Looked up on every request, so a deleted account is logged out and a
    change of the admin role takes effect immediately.
    """
    if "user" not in g:
        g.user = None
        if "username" in session:
            g.user = (
                get_db()
                .execute(
                    "SELECT username, is_admin FROM laundry_users WHERE username = ?",
                    (session["username"],),
                )
                .fetchone()
            )
            if g.user is None:
                session.clear()
    return g.user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if logged_in_user() is None:
            return error("You must be logged in to do that.", 401)
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not logged_in_user()["is_admin"]:
            return error("Only an admin can do that.", 403)
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


def today():
    return datetime.now(TIMEZONE).date()


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
    if day < today():
        return "You cannot book or cancel a time slot in the past."
    if day > last_bookable_day(today()):
        return "You can only book this month and the next."
    return None


@api.get("/registration")
def registration():
    """Tells the create-account form whether to ask for an invite code."""
    return jsonify({"inviteCodeRequired": bool(current_app.config["INVITE_CODE"])})


@api.post("/register")
def register():
    username, password = credentials()
    if not username or not password:
        return error("Username and password are required.", 400)
    invite_code = current_app.config["INVITE_CODE"]
    if invite_code:
        given = (request.get_json(silent=True) or {}).get("inviteCode")
        if not isinstance(given, str) or not hmac.compare_digest(
            given.strip().encode(), invite_code.encode()
        ):
            return error("Wrong invite code.", 403)
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
    return jsonify({"username": username, "isAdmin": False}), 201


@api.post("/login")
def login():
    username, password = credentials()
    db = get_db()
    window_start = int(time.time() - FAILED_LOGIN_WINDOW.total_seconds())
    (failures,) = db.execute(
        "SELECT COUNT(*) FROM failed_logins WHERE username = ? AND attempted_at > ?",
        (username, window_start),
    ).fetchone()
    if failures >= MAX_FAILED_LOGINS:
        minutes = int(FAILED_LOGIN_WINDOW.total_seconds() // 60)
        return error(f"Too many failed attempts. Wait up to {minutes} minutes and try again.", 429)

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
        db.execute("DELETE FROM failed_logins WHERE attempted_at <= ?", (window_start,))
        db.execute(
            "INSERT INTO failed_logins (username, attempted_at) VALUES (?, ?)",
            (username, int(time.time())),
        )
        return error("Wrong username or password.", 401)

    db.execute("DELETE FROM failed_logins WHERE username = ?", (username,))
    log_in(username)
    return current_user()


@api.post("/reset-password")
def reset_password():
    """Choose a new password with a one-time code from an admin."""
    username, password = credentials()
    code = (request.get_json(silent=True) or {}).get("code")
    if not username or not password or not isinstance(code, str):
        return error("Username, reset code and new password are required.", 400)
    if len(password) < MIN_PASSWORD_LENGTH:
        return error(f"The password must be at least {MIN_PASSWORD_LENGTH} characters.", 400)

    db = get_db()
    # Deleting is the check: a code can only ever be used once
    used = db.execute(
        "DELETE FROM password_resets WHERE username = ? AND code_hash = ? AND expires_at > ?",
        (username, hash_reset_code(code.strip()), int(time.time())),
    ).rowcount
    if not used:
        return error("Wrong username or reset code, or the code has expired.", 400)

    db.execute(
        "UPDATE laundry_users SET password = ? WHERE username = ?",
        (generate_password_hash(password), username),
    )
    db.execute("DELETE FROM failed_logins WHERE username = ?", (username,))
    log_in(username)
    return current_user()


@api.post("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


@api.get("/user")
def current_user():
    user = logged_in_user()
    return jsonify(
        {
            "username": user["username"] if user else None,
            "isAdmin": bool(user and user["is_admin"]),
        }
    )


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
            (today().isoformat(),),
        )
        .fetchall()
    )
    user = logged_in_user()
    username = user["username"] if user else None
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
            (username, today().isoformat()),
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

    # An admin may cancel anyone's booking
    user = logged_in_user()
    deleted = (
        get_db()
        .execute(
            "DELETE FROM bookings WHERE booking_date = ? AND booking_time = ?"
            " AND (username = ? OR ?)",
            (booking_date, slot, user["username"], user["is_admin"]),
        )
        .rowcount
    )
    if not deleted:
        return error("Booking not found, or it is not yours.", 404)
    return jsonify({"message": "Booking cancelled"})


@api.get("/users")
@admin_required
def list_users():
    rows = (
        get_db()
        .execute(
            "SELECT u.username, u.is_admin, COUNT(b.id) AS active_bookings"
            " FROM laundry_users u"
            " LEFT JOIN bookings b ON b.username = u.username AND b.booking_date >= ?"
            " GROUP BY u.username ORDER BY u.username COLLATE NOCASE",
            (today().isoformat(),),
        )
        .fetchall()
    )
    return jsonify(
        {
            "users": [
                {
                    "username": row["username"],
                    "isAdmin": bool(row["is_admin"]),
                    "activeBookings": row["active_bookings"],
                }
                for row in rows
            ]
        }
    )


# `path` so that a username containing a slash still matches
@api.post("/users/<path:username>/reset-code")
@admin_required
def create_user_reset_code(username):
    """A code the admin passes on to someone who has forgotten their password."""
    code = create_reset_code(username)
    if code is None:
        return error("User not found.", 404)
    hours = int(RESET_CODE_LIFETIME.total_seconds() // 3600)
    return jsonify({"code": code, "validHours": hours}), 201


@api.delete("/users/<path:username>")
@admin_required
def delete_user(username):
    """Remove an account and all its bookings, e.g. when someone moves out."""
    if username == logged_in_user()["username"]:
        return error("You cannot delete your own account.", 400)

    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("DELETE FROM bookings WHERE username = ?", (username,))
        db.execute("DELETE FROM password_resets WHERE username = ?", (username,))
        deleted = db.execute("DELETE FROM laundry_users WHERE username = ?", (username,)).rowcount
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise

    if not deleted:
        return error("User not found.", 404)
    return jsonify({"message": "User deleted"})


if __name__ == "__main__":
    create_app().run(host="localhost", port=5001, debug=os.environ.get("FLASK_DEBUG") == "1")
