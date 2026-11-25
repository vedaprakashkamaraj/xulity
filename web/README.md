# xuity

A tiny Flask website for uploading, browsing and downloading software.

## Run locally

```sh
cd web
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8000.

## Configuration

Environment variables:

| Variable | Default | Meaning |
|:---|:---|:---|
| `XUITY_HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` on a server. |
| `XUITY_PORT` | `8000` | Port. |
| `XUITY_MAX_UPLOAD_MB` | `500` | Maximum upload size. |
| `XUITY_SECRET_KEY` | dev value | Set a random value in production. |
| `XUITY_ADMIN_PASSWORD` | unset | Enables password-protected delete buttons. |

Example:

```sh
XUITY_HOST=0.0.0.0 XUITY_SECRET_KEY="$(openssl rand -hex 32)" \
XUITY_ADMIN_PASSWORD="choose-one" python app.py
```

Uploads live in `web/uploads/` and metadata in `web/data/xuity.db`; both are gitignored. Delete the files there to reset the site.

> For public hosting, put it behind a proper web server (gunicorn + nginx/Caddy) and use HTTPS. Do not expose Flask's development server directly to the internet.
