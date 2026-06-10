import json
import os
import re
import smtplib
import time
from html import unescape
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
from flask import Flask, jsonify, render_template, request, session

app = Flask(__name__)
app.secret_key = os.urandom(24)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file provided"}), 400
    try:
        if f.filename.endswith(".csv"):
            df = pd.read_csv(f)
        else:
            df = pd.read_excel(f)
        df = df.fillna("")
        rows = df.to_dict(orient="records")
        headers = list(df.columns)
        session["rows"] = rows
        session["headers"] = headers
        return jsonify({"headers": headers, "rows": rows[:3], "total": len(rows)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/send", methods=["POST"])
def send():
    data = request.json
    gmail = data.get("gmail", "").strip()
    app_password = data.get("app_password", "").strip()
    sender_name = data.get("sender_name", "").strip() or gmail
    subject_tmpl = data.get("subject", "")
    body_tmpl = data.get("body", "")
    col_map = data.get("col_map", {})
    delay = float(data.get("delay", 4))
    test_only = data.get("test_only", False)
    rows = session.get("rows", [])
    headers = session.get("headers", [])

    if not gmail or not app_password:
        return jsonify({"error": "Gmail credentials missing"}), 400
    if not rows:
        return jsonify({"error": "No data loaded — please upload your Excel file first"}), 400

    def html_to_plain(html_text):
        text = re.sub(r"<\s*br\s*/?>", "\n", html_text, flags=re.IGNORECASE)
        text = re.sub(r"</\s*p\s*>", "\n\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<\s*li\s*>", "- ", text, flags=re.IGNORECASE)
        text = re.sub(r"</\s*li\s*>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", "", text)
        text = unescape(text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def fill(tmpl, row):
        for h in headers:
            tmpl = tmpl.replace("{{" + h + "}}", str(row.get(h, "")))
        return tmpl

    targets = [rows[0]] if test_only else rows
    results = []

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail, app_password)
            for i, row in enumerate(targets):
                if test_only:
                    to = gmail
                    cc = ""
                    to_name = "You"
                else:
                    to = row.get(col_map.get("Email", "Email"), "")
                    cc = row.get(col_map.get("Lead Email", "Lead Email"), "")
                    to_name = row.get(col_map.get("Name", "Name"), "")

                subject = fill(subject_tmpl, row)
                body_html = fill(body_tmpl, row)
                body_plain = html_to_plain(body_html)

                if not to:
                    results.append(
                        {"to": "?", "status": "skipped", "reason": "No email address"})
                    continue

                msg = MIMEMultipart()
                msg["From"] = f"{sender_name} <{gmail}>"
                msg["To"] = to
                if cc and not test_only:
                    msg["Cc"] = cc
                msg["Subject"] = subject
                msg.attach(MIMEText(body_plain, "plain", "utf-8"))
                msg.attach(MIMEText(body_html, "html", "utf-8"))

                recipients = [to]
                if cc and not test_only:
                    recipients.append(cc)
                server.sendmail(gmail, recipients, msg.as_string())
                results.append({"to": to, "name": to_name,
                               "cc": cc, "status": "sent"})

                if i < len(targets) - 1:
                    time.sleep(delay)

        return jsonify({"results": results, "total": len(targets)})

    except smtplib.SMTPAuthenticationError:
        return jsonify({"error": "Authentication failed — check your Gmail address and App Password"}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("\n  Mail Merge running at → http://localhost:5000\n")
    app.run(debug=False, port=5000)
