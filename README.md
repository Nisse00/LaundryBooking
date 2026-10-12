# Botan laundry booking

Booking system for the laundry room in Föreningen Botan, Lund.

- **Frontend** – React + TypeScript + Vite, in `frontend/`
- **Backend** – a small Flask API with a SQLite database, in `backend/`

```
frontend/
  package.json         scripts and dependencies
  index.html           the single HTML page
  src/
    main.tsx, App.tsx  entry point and routes
    index.css          all styles
    api.ts             client for the backend
    slots.ts           time slots, their colours and the booking limit
    assets/            images imported by the code
    pages/             one file per route: /, /login, /create-account, /reset-password,
                       /calendar, /admin
    components/        pieces used by the pages
backend/
  server.py            the API
  tests/               pytest tests
```

The config files in `frontend/` (`vite.config.ts`, `tsconfig*.json`,
`eslint.config.js`, `.prettierrc.json`) have to stay next to `package.json`:
the tools look for them there.

## Getting started

Install the dependencies once, from the project root:

```bash
npm install --prefix frontend
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements-dev.txt
```

All commands are then run from the `frontend/` folder. Start both servers with:

```bash
cd frontend
npm run dev:full
```

- Frontend: http://localhost:5173
- Backend: http://localhost:5001 (Vite proxies `/api` to it, so the browser only talks to port 5173)

Both servers reload automatically when you save a file. The backend scripts use
`backend/.venv` directly, so the virtual environment does not need to be activated.

Other scripts:

- `npm run dev` / `npm run dev:frontend` – only the frontend
- `npm run dev:backend` – only the backend
- `npm run build` – type-check and build the frontend into `frontend/dist/`
- `npm run lint` – run ESLint on the frontend
- `npm run format` – format the frontend with Prettier (`format:check` only checks)
- `npm run test:backend` – run the backend tests (pytest)
- `npm run lint:backend` – lint and format-check the backend (ruff)

Run `npm run build`, `npm run lint`, `npm run format:check`, `npm run test:backend`
and `npm run lint:backend` before committing.

## Booking rules

- Each day has three time slots: 08:00-12:00, 12:00-16:00 and 16:00-20:00.
- You can book in the current month and the next one, never in the past.
- Each user can hold three upcoming bookings at a time; cancel one to book another.
- A slot can only be booked by one user. This is enforced by a unique index in
  the database, so two simultaneous requests can never both succeed.
- Logged-in users can see who has booked a slot; visitors cannot.

All rules are enforced by the backend; the frontend only mirrors them.

To slow down password guessing, ten wrong passwords for one username block
logging in to that account for up to 15 minutes.

## Admins

An admin can cancel anyone's booking from the calendar, and delete accounts
(for example when someone moves out) under **Menu → Manage users**. The first
admin is appointed from the command line, in `backend/`:

```bash
.venv/bin/flask --app server set-admin USERNAME
```

Add `--remove` to take the role away again.

### Forgotten passwords

There is no email in the system, so an admin helps out: **Reset password** on
the Manage users page shows a one-time code, valid for 24 hours. The user
enters it under **Forgot your password?** on the log in page and chooses a new
password. An admin who is locked out themselves gets a code with:

```bash
.venv/bin/flask --app server reset-code USERNAME
```

## Backend configuration

Environment variables, all optional:

| Variable                | Default                                 | Purpose                                      |
| ----------------------- | --------------------------------------- | -------------------------------------------- |
| `SECRET_KEY`            | random, stored in `backend/.secret_key` | Signs the session cookie                     |
| `LAUNDRY_DATABASE`      | `backend/laundry.db`                    | Path to the SQLite database                  |
| `LAUNDRY_BACKUP_DIR`    | `backend/backups/`                      | Where `flask backup` puts its copies         |
| `SESSION_COOKIE_SECURE` | off                                     | Set to `1` in production (HTTPS only cookie) |
| `INVITE_CODE`           | none                                    | Code needed to create an account             |
| `FLASK_DEBUG`           | off                                     | Auto-reload; the `dev` scripts turn it on    |

Set `INVITE_CODE` in production and share the code within the building. Without
it, anyone who finds the site can create an account and book time slots.

The database is created on first start and is not checked in to git.

## Backups

Every account and booking lives in the one database file, so back it up. This
copies it to the backup folder, one file per day, and keeps the latest 14
(change with `--keep`). It is safe to run while the server is in use:

```bash
.venv/bin/flask --app server backup
```

Run it daily on the server, for example with this line in `crontab -e`
(adjust the path):

```
15 3 * * * cd /srv/laundry/backend && .venv/bin/flask --app server backup
```

The copies end up on the same disk as the database. Also sync the backup
folder to another machine or to cloud storage, or a broken disk takes both.
To restore, stop the server and replace the database file with a backup.

## Running in production

`Dockerfile` and `docker-compose.yml` set up the whole site: Caddy serves the
built frontend over HTTPS (it fetches the certificate itself) and forwards
`/api` to the Flask app, which runs under gunicorn. The database is kept on a
Docker volume, so it survives updates.

You need a server with Docker, and a domain name pointing to it. On the server:

```bash
cp .env.example .env
```

Fill in the three values in `.env`, then start everything:

```bash
docker compose up -d --build
```

Run the same command again after `git pull` to update. Commands from the
sections above are run inside the container, for example:

```bash
docker compose exec api flask --app server set-admin USERNAME
```

```bash
docker compose exec api flask --app server backup
```

For the daily backup, put `cd /path/to/LaundryBooking && docker compose exec -T
api flask --app server backup` in the server's crontab. The copies are in the
`laundry_data` volume, under `backups/`.

Without Docker: serve `frontend/dist/` and forward `/api` to the Flask app from
the same domain, run it with `gunicorn --preload "server:create_app()"` (not
`python3 server.py`), and set `SECRET_KEY`, `INVITE_CODE` and
`SESSION_COOKIE_SECURE=1`. Only `backend/requirements.txt` is needed there.
