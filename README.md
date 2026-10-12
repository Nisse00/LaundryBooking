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
    pages/             one file per route: /, /login, /create-account, /calendar, /admin
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

## Admins

An admin can cancel anyone's booking from the calendar, and delete accounts
(for example when someone moves out) under **Menu → Manage users**. The first
admin is appointed from the command line, in `backend/`:

```bash
.venv/bin/flask --app server set-admin USERNAME
```

Add `--remove` to take the role away again.

## Backend configuration

Environment variables, all optional:

| Variable                | Default                                 | Purpose                                      |
| ----------------------- | --------------------------------------- | -------------------------------------------- |
| `SECRET_KEY`            | random, stored in `backend/.secret_key` | Signs the session cookie                     |
| `LAUNDRY_DATABASE`      | `backend/laundry.db`                    | Path to the SQLite database                  |
| `SESSION_COOKIE_SECURE` | off                                     | Set to `1` in production (HTTPS only cookie) |
| `INVITE_CODE`           | none                                    | Code needed to create an account             |
| `FLASK_DEBUG`           | off                                     | Auto-reload; the `dev` scripts turn it on    |

Set `INVITE_CODE` in production and share the code within the building. Without
it, anyone who finds the site can create an account and book time slots.

The database is created on first start and is not checked in to git.

In production, serve `frontend/dist/` and forward `/api` to the Flask app from the
same domain (run it with a WSGI server, e.g. `gunicorn "server:create_app()"`, not
`python3 server.py`). Only `backend/requirements.txt` is needed there.
