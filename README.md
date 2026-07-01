# Serein Café

A full-stack café ordering and reservation website with a separated frontend and backend.

## Project structure

```text
Cafe webssite/
├── frontend/
│   ├── assets/
│   ├── index.html
│   ├── script.js
│   └── style.css
├── backend/
│   ├── data/
│   │   └── serein.db
│   ├── .env.example
│   └── server.py
└── README.md
```

## Run the website

From the project root:

```powershell
python backend/server.py
```

Then open `http://127.0.0.1:8000`. Do not open `frontend/index.html` directly because API requests require the backend server.

## Automated email

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM` in the same PowerShell window before starting the server. Use a Gmail App Password, never the normal account password.

Without SMTP configuration, outgoing emails are recorded as `queued` in the `email_log` database table.

## Database

The SQLite database is located at `backend/data/serein.db`. Close DB Browser for SQLite before submitting orders to prevent it from holding a write lock.

## API

- `GET /api/health`
- `GET /api/menu`
- `POST /api/orders`
- `POST /api/reservations`
- `POST /api/newsletter`

## Deploy on Render

The repository includes `render.yaml`. Connect the repository as a Render Blueprint and enter the SMTP values when prompted. Render supplies the public port automatically, while the application binds to `0.0.0.0`.

The included Blueprint uses Render's free plan. Its filesystem is temporary, so SQLite records can be lost when the service restarts or redeploys. For production, attach a persistent disk and set `DATABASE_PATH` to its mounted location, or migrate the database to managed PostgreSQL.
