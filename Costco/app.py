import os
import json
import pandas as pd
import requests
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from io import StringIO
from datetime import datetime

# ===============================================================
# COSTCO NIGHT MERCH SCHEDULER (FLASK VERSION)
# LLM + Deterministic Engine + Web UI
# ===============================================================

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Needed for flashing messages

LLM_MODEL = "llama3"
LLM_URL = "http://localhost:11434/api/generate"

UNTRAINED = 0
REQUIRED_ROLE_LINES = 15

DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]

ROLE_SKILL_MAP = {
    "DOCK": "dock",
    "EPJ": "epj",
    "WALLS": "walls",
    "DDD": "ddd",
    "FREEZER": "freezer_driver",
    "FREEZER_STOCKER": "freezer_stocker",
    "WALLS_STOCKER": "walls_stocker",
    "BEER": "beer_stocker",
}

SUPERVISOR_NAME = "Jacob"

rank_cols = [
    "dock", "epj", "walls", "ddd",
    "freezer_driver", "freezer_stocker",
    "walls_stocker", "beer_stocker",
]

# Store data in memory
skills_df = None
schedule_df = None
last_text_output = ""


# ===============================================================
# LLM CALL
# ===============================================================

def run_local_llm(prompt: str) -> str:
    resp = requests.post(
        LLM_URL,
        json={"model": LLM_MODEL, "prompt": prompt, "stream": False}
    )
    resp.raise_for_status()
    return resp.json()["response"]


# ===============================================================
# DATA FUNCTIONS
# ===============================================================

def melt_schedule(df):
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={c: c.capitalize() for c in df.columns if c != "name"})
    return df.melt(id_vars=["name"], var_name="day", value_name="available")


def get_available(day, schedule_long):
    return schedule_long[
        (schedule_long["day"] == day.capitalize()) &
        (schedule_long["available"] == 1)
    ]["name"].tolist()


def sorted_available_df(day, schedule_long):
    available = get_available(day, schedule_long)
    df = skills_df[skills_df["name"].isin(available)].copy()
    df["avg_rank"] = df[rank_cols].replace(UNTRAINED, 10).mean(axis=1)
    return df.sort_values("avg_rank")


def best_candidates_for_day(day, schedule_long):
    df = sorted_available_df(day, schedule_long)

    def top(df_local, col):
        tmp = df_local[df_local[col] > 0][["name", col]]
        return tmp.sort_values(col).head(5).to_dict(orient="records")

    out = {}
    for role, col in ROLE_SKILL_MAP.items():
        out[role] = top(df, col)
    return out


# ===============================================================
# VALIDATION
# ===============================================================

def validate_day(day_block, available_today):
    if not day_block.strip():
        return False

    lines = [l for l in day_block.splitlines() if ":" in l]
    if len(lines) != REQUIRED_ROLE_LINES:
        return False

    used = {}

    for line in lines:
        role, name = line.split(":", 1)
        name = name.strip()

        if name == "UNFILLED":
            continue

        if name not in available_today:
            return False

        used[name] = used.get(name, 0) + 1

    return all(v == 1 for v in used.values())


# ===============================================================
# DETERMINISTIC
# ===============================================================

def deterministic(day, schedule_long):
    available = get_available(day, schedule_long)
    df = skills_df[skills_df["name"].isin(available)].copy()

    df["avg_rank"] = df[rank_cols].replace(UNTRAINED, 10).mean(axis=1)
    df = df.sort_values("avg_rank")
    remaining = df.copy()

    def pick(col):
        nonlocal remaining
        tmp = remaining.sort_values(col)
        for _, r in tmp.iterrows():
            if r[col] > 0:
                name = r["name"]
                remaining = remaining[remaining["name"] != name]
                return name
        return "UNFILLED"

    def pick_avg():
        nonlocal remaining
        if remaining.empty:
            return "UNFILLED"
        name = remaining.iloc[0]["name"]
        remaining = remaining[remaining["name"] != name]
        return name

    out = []
    out.append(f"=== {day} ===")
    out.append("DRIVERS")
    out.append(f"DOCK: {pick('dock')}")
    out.append(f"EPJ: {pick('epj')}")
    out.append(f"WALLS: {pick('walls')}")
    out.append(f"FREEZER: {pick('freezer_driver')}")
    out.append(f"DDD: {pick('ddd')}")
    out.append(f"FLOAT: {pick_avg()}")

    out.append("\nSTOCKERS")
    for _ in range(5): out.append(f"FREEZER: {pick('freezer_stocker')}")
    for _ in range(3): out.append(f"WALLS: {pick('walls_stocker')}")
    out.append(f"BEER: {pick('beer_stocker')}")

    return "\n".join(out), remaining["name"].tolist()


# ===============================================================
# HYBRID SCHEDULER
# ===============================================================

def run_scheduler():
    schedule_long = melt_schedule(schedule_df)

    example = json.dumps(best_candidates_for_day("WEDNESDAY", schedule_long), indent=2)

    template = """
DRIVERS
DOCK: ______
EPJ: ______
WALLS: ______
FREEZER: ______
DDD: ______
FLOAT: ______

STOCKERS
FREEZER: ______
FREEZER: ______
FREEZER: ______
FREEZER: ______
FREEZER: ______
WALLS: ______
WALLS: ______
WALLS: ______
BEER: ______
"""

    prompt = f"""
You are an expert Costco scheduler.
Generate a schedule Mon–Sun.
No duplicates. Use only available employees.

Example candidates:
{example}

TEMPLATES:
""" + "\n".join([f"=== {day} ===\n{template}" for day in DAYS])

    try:
        llm_output = run_local_llm(prompt)
    except Exception:
        llm_output = ""

    # Parse
    day_blocks = {}
    cur_day = None
    cur_text = []

    for line in llm_output.splitlines():
        s = line.strip()
        if s.startswith("===") and s.endswith("==="):
            if cur_day:
                day_blocks[cur_day] = "\n".join(cur_text)
            cur_day = s.replace("=", "").strip()
            cur_text = [s]
        else:
            cur_text.append(line)

    if cur_day:
        day_blocks[cur_day] = "\n".join(cur_text)

    # Validate or fallback
    final_lines = []

    for day in DAYS:
        avail = get_available(day, schedule_long)
        block = day_blocks.get(day, "")

        if block and validate_day(block, avail):
            final_lines.append(block)
            extras = []
        else:
            block, extras = deterministic(day, schedule_long)
            final_lines.append(block)

        final_lines.append("EXTRAS: " + (", ".join(extras) if extras else "NONE"))
        final_lines.append("")

    return "\n".join(final_lines)


# ===============================================================
# ROUTES
# ===============================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    global skills_df, schedule_df

    if "skills" in request.files:
        f = request.files["skills"]
        if f.filename:
            skills_df = pd.read_csv(f)
            skills_df["name"] = skills_df["name"].str.strip()
            flash("Skills CSV loaded.")

    if "schedule" in request.files:
        f = request.files["schedule"]
        if f.filename:
            schedule_df = pd.read_csv(f)
            schedule_df["name"] = schedule_df["name"].str.strip()
            flash("Weekly Schedule CSV loaded.")

    return redirect(url_for("index"))


@app.route("/run")
def run():
    global last_text_output
    if skills_df is None or schedule_df is None:
        flash("Upload both CSV files first!")
        return redirect(url_for("index"))

    last_text_output = run_scheduler()
    table = convert_to_table(last_text_output)  # Build HTML table

    return render_template("result.html", table=table, raw_output=last_text_output)


@app.route("/download")
def download():
    global last_text_output
    buffer = StringIO(last_text_output)
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="text/plain",
        download_name="schedule.txt",
        as_attachment=True
    )


# ===============================================================
# Convert schedule text → HTML table
# ===============================================================

def convert_to_table(schedule_text):
    """
    Returns an HTML table similar to your Google Sheets layout.
    """
    parsed = {d: {} for d in DAYS}
    role_order = []

    current_day = None
    current_section = None
    freezer_count = 0
    walls_count = 0

    for line in schedule_text.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("===") and line.endswith("==="):
            current_day = line.replace("=", "").strip()
            freezer_count = 0
            walls_count = 0
            continue

        if line in ["DRIVERS", "STOCKERS"]:
            current_section = line
            continue

        if line.startswith("EXTRAS:"):
            parsed[current_day]["STOCKERS_EXTRAS"] = line.split(":", 1)[1].strip()
            if "STOCKERS_EXTRAS" not in role_order:
                role_order.append("STOCKERS_EXTRAS")
            continue

        if ":" in line and current_day:
            role, worker = line.split(":", 1)
            role = role.strip()
            worker = worker.strip()

            if current_section == "STOCKERS":
                if role == "FREEZER":
                    freezer_count += 1
                    role_key = f"FREEZER_{freezer_count}"
                elif role == "WALLS":
                    walls_count += 1
                    role_key = f"WALLS_{walls_count}"
                else:
                    role_key = role
            else:
                role_key = role

            full_key = f"{current_section}_{role_key}"

            if full_key not in role_order:
                role_order.append(full_key)

            parsed[current_day][full_key] = worker

    # Build HTML
    html = "<table class='table table-bordered table-dark text-center'>"

    # Header row
    html += "<tr><th></th>"
    for day in DAYS:
        html += f"<th>{day}</th>"
    html += "</tr>"

    last_group = None

    for full_key in role_order:
        group, role_key = full_key.split("_", 1)

        if group != last_group:
            html += f"<tr class='table-secondary'><th colspan='{len(DAYS)+1}'>{group}</th></tr>"
            last_group = group

        html += "<tr>"
        html += f"<th>{role_key}</th>"
        for day in DAYS:
            name = parsed[day].get(full_key, "")
            html += f"<td>{name}</td>"
        html += "</tr>"

    html += "</table>"
    return html


# ===============================================================
# START FLASK
# ===============================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001)
