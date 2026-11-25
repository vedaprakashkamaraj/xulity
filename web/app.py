#!/usr/bin/env python3
"""xuity - a small website for uploading, browsing and downloading software."""
import os
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent
UPLOAD_DIR = BASE / "uploads"
DB_PATH = BASE / "data" / "xuity.db"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH.parent.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("XUITY_SECRET_KEY", "dev-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("XUITY_MAX_UPLOAD_MB", "500")) * 1024 * 1024
ADMIN_PASSWORD = os.environ.get("XUITY_ADMIN_PASSWORD")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS files (
               id TEXT PRIMARY KEY,
               filename TEXT NOT NULL,
               stored TEXT NOT NULL,
               size INTEGER NOT NULL,
               uploaded_at REAL NOT NULL,
               description TEXT NOT NULL DEFAULT ''
           )"""
    )
    return conn


def human_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


app.jinja_env.filters["human_size"] = human_size
app.jinja_env.filters["date"] = lambda ts: datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")


@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    with db() as conn:
        if q:
            rows = conn.execute(
                "SELECT * FROM files WHERE filename LIKE ? OR description LIKE ? ORDER BY uploaded_at DESC",
                (f"%{q}%", f"%{q}%"),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM files ORDER BY uploaded_at DESC").fetchall()
        total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        bytes_total = conn.execute("SELECT COALESCE(SUM(size), 0) FROM files").fetchone()[0]
    return render_template(
        "index.html",
        files=rows,
        query=q,
        total=total,
        bytes_total=bytes_total,
        admin=bool(ADMIN_PASSWORD),
        max_mb=app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024),
    )


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a file first.", "error")
        return redirect(url_for("index"))

    original = secure_filename(f.filename)
    if not original:
        flash("That filename isn't usable.", "error")
        return redirect(url_for("index"))

    file_id = uuid.uuid4().hex
    stored = f"{file_id}-{original}"
    target = UPLOAD_DIR / stored
    f.save(target)

    with db() as conn:
        conn.execute(
            "INSERT INTO files (id, filename, stored, size, uploaded_at, description) VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, original, stored, target.stat().st_size, time.time(), request.form.get("description", "")[:500]),
        )
    flash(f"Uploaded {original}.", "ok")
    return redirect(url_for("index"))


@app.route("/download/<file_id>")
def download(file_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        abort(404)
    return send_from_directory(UPLOAD_DIR, row["stored"], as_attachment=True, download_name=row["filename"])


@app.route("/delete/<file_id>", methods=["POST"])
def delete(file_id):
    if not ADMIN_PASSWORD:
        abort(403)
    if request.form.get("password", "") != ADMIN_PASSWORD:
        flash("Wrong password.", "error")
        return redirect(url_for("index"))

    with db() as conn:
        row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
        if not row:
            abort(404)
        (UPLOAD_DIR / row["stored"]).unlink(missing_ok=True)
        conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    flash(f"Deleted {row['filename']}.", "ok")
    return redirect(url_for("index"))


@app.errorhandler(413)
def too_large(_error):
    flash("File is too large for this server.", "error")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host=os.environ.get("XUITY_HOST", "127.0.0.1"), port=int(os.environ.get("XUITY_PORT", "8000")))
