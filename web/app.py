import os
from functools import wraps
from datetime import datetime, timezone

from flask import Flask, render_template, request, redirect, url_for, session, flash

from config import OWNER_ID, DB_PATH, TEMPLATE_DIR, ACCOUNTS_DIR
from database import Database
from manager.processes import ProcessManager


app = Flask(__name__)
app.secret_key = os.getenv("WEB_SECRET", "change-this-secret-key")

db = Database(DB_PATH)

pm = ProcessManager(
    TEMPLATE_DIR,
    ACCOUNTS_DIR,
)


def owner_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        try:
            user_id = int(request.form.get("user_id", "0"))
        except ValueError:
            user_id = 0

        if user_id == OWNER_ID:
            session["authenticated"] = True
            return redirect(url_for("dashboard"))

        flash("❌ رقم المستخدم غير صحيح.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@owner_required
def dashboard():

    rows = db.all()

    stats = {
        "total": len(rows),
        "running": sum(r.get("status") == "running" for r in rows),
        "stopped": sum(r.get("status") == "stopped" for r in rows),
        "expired": sum(r.get("status") == "expired" for r in rows),
    }

    return render_template(
        "dashboard.html",
        rows=rows,
        stats=stats,
    )


@app.route("/install/<int:iid>")
@owner_required
def install(iid):

    row = db.get(iid)

    if not row:
        return "التنصيب غير موجود", 404

    return render_template(
        "install.html",
        row=row,
    )


@app.post("/install/<int:iid>/start")
@owner_required
def start(iid):

    row = db.get(iid)

    if not row:
        return "Not found", 404

    try:
        pm.start(iid)
        db.status(iid, "running")
        flash("🟢 تم تشغيل التنصيب.", "success")
    except Exception as e:
        db.status(iid, "error")
        flash(f"❌ {e}", "error")

    return redirect(url_for("install", iid=iid))


@app.post("/install/<int:iid>/stop")
@owner_required
def stop(iid):

    row = db.get(iid)

    if not row:
        return "Not found", 404

    try:
        pm.stop(iid)
        db.status(iid, "stopped")
        flash("⛔ تم إيقاف التنصيب.", "success")
    except Exception as e:
        flash(f"❌ {e}", "error")

    return redirect(url_for("install", iid=iid))


@app.post("/install/<int:iid>/restart")
@owner_required
def restart(iid):

    row = db.get(iid)

    if not row:
        return "Not found", 404

    try:
        pm.restart(iid)
        db.status(iid, "running")
        flash("🔄 تمت إعادة التشغيل.", "success")
    except Exception as e:
        db.status(iid, "error")
        flash(f"❌ {e}", "error")

    return redirect(url_for("install", iid=iid))


@app.post("/install/<int:iid>/ban")
@owner_required
def ban(iid):

    row = db.get(iid)

    if not row:
        return "Not found", 404

    if row["user_id"] == OWNER_ID:
        flash("❌ لا يمكن حظر المالك.", "error")
        return redirect(url_for("install", iid=iid))

    db.ban_user(row["user_id"])

    try:
        pm.stop(iid)
        db.status(iid, "stopped")
    except Exception:
        pass

    flash("🚫 تم حظر المستخدم وإيقاف التنصيب.", "success")

    return redirect(url_for("install", iid=iid))


@app.post("/install/<int:iid>/unban")
@owner_required
def unban(iid):

    row = db.get(iid)

    if not row:
        return "Not found", 404

    db.unban_user(row["user_id"])

    flash("✅ تم إلغاء الحظر.", "success")

    return redirect(url_for("install", iid=iid))


@app.post("/install/<int:iid>/extend/<int:days>")
@owner_required
def extend(iid, days):

    if days not in (30, 90, 365):
        flash("❌ مدة غير صحيحة.", "error")
        return redirect(url_for("install", iid=iid))

    row = db.get(iid)

    if not row:
        return "Not found", 404

    if row["unlimited"]:
        flash("♾️ التنصيب غير محدود.", "error")
        return redirect(url_for("install", iid=iid))

    try:
        db.extend_install(iid, days)
        flash(f"⏳ تم تمديد التنصيب {days} يوم.", "success")
    except Exception as e:
        flash(f"❌ {e}", "error")

    return redirect(url_for("install", iid=iid))


@app.post("/install/<int:iid>/delete")
@owner_required
def delete(iid):

    row = db.get(iid)

    if not row:
        return "Not found", 404

    try:
        pm.stop(iid)
    except Exception:
        pass

    db.delete(iid)

    flash("🗑️ تم حذف التنصيب.", "success")

    return redirect(url_for("dashboard"))


@app.get("/api/stats")
@owner_required
def api_stats():

    rows = db.all()

    return {
        "total": len(rows),
        "running": sum(r.get("status") == "running" for r in rows),
        "stopped": sum(r.get("status") == "stopped" for r in rows),
        "expired": sum(r.get("status") == "expired" for r in rows),
    }


if __name__ == "__main__":

    port = int(os.getenv("WEB_PORT", "10000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
