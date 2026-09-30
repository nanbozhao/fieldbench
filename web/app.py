"""fieldbench web app: submit benchmark jobs, poll progress, view results.

Run:  uvicorn web.app:app --host 0.0.0.0 --port 8000
Requires: pip install fastapi uvicorn ; fieldbench installed (pip install -e .)
"""
import json
import os
import sqlite3
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import fieldbench as fb
from fieldbench import openalex as fb_oa
from fieldbench.cache import Cache

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "jobs.db")
CACHE = Cache(os.path.join(BASE, "..", "data", "cache"))
EXECUTOR = ThreadPoolExecutor(max_workers=1)  # one pipeline at a time (S2 limits)

app = FastAPI(title="fieldbench")
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))


def db():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS jobs(
        id TEXT PRIMARY KEY, params TEXT, status TEXT,
        progress TEXT, result TEXT, error TEXT,
        created REAL, updated REAL)""")
    return con


def get_job(jid):
    con = db()
    row = con.execute("SELECT id,params,status,progress,result,error,created,updated"
                      " FROM jobs WHERE id=?", (jid,)).fetchone()
    con.close()
    if not row:
        return None
    return {"id": row[0], "params": json.loads(row[1]), "status": row[2],
            "progress": json.loads(row[3] or "{}"),
            "result": json.loads(row[4]) if row[4] else None,
            "error": row[5], "created": row[6], "updated": row[7]}


def set_job(jid, **kw):
    con = db()
    sets = ", ".join(f"{k}=?" for k in kw) + ", updated=?"
    con.execute(f"UPDATE jobs SET {sets} WHERE id=?",
                tuple(kw.values()) + (time.time(), jid))
    con.commit()
    con.close()


def run_pipeline(jid, params):
    def progress(stage, done, total, msg):
        set_job(jid, progress=json.dumps(
            {"stage": stage, "done": done, "total": total, "message": msg}))
    try:
        set_job(jid, status="running")
        result = fb.run(
            params["topics"], params["dois"], params["name"],
            year_from=params.get("year_from", 2022),
            year_to=params.get("year_to", 2024),
            min_topic_works=params.get("min_topic_works", 2),
            first_pub_from=params.get("first_pub_from", 2020),
            first_pub_to=params.get("first_pub_to", 2022),
            subject_oa_id=params.get("oa_id"),
            cache=CACHE, progress_cb=progress, workers=4)
        set_job(jid, status="done",
                result=json.dumps(result),
                progress=json.dumps({"stage": "done", "message": "complete"}))
    except Exception as e:
        set_job(jid, status="failed",
                error=f"{type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/topics")
def api_topics(q: str):
    try:
        return {"results": fb_oa.search_topics(q)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/jobs")
async def create_job(request: Request):
    params = await request.json()
    for k in ("topics", "dois", "name"):
        if not params.get(k):
            return JSONResponse({"error": f"missing '{k}'"}, status_code=400)
    jid = uuid.uuid4().hex[:12]
    con = db()
    con.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)",
                (jid, json.dumps(params), "queued", "{}", None, None,
                 time.time(), time.time()))
    con.commit()
    con.close()
    EXECUTOR.submit(run_pipeline, jid, params)
    return {"job_id": jid}


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    job = get_job(jid)
    if not job:
        return JSONResponse({"error": "not found"}, status_code=404)
    return job


@app.get("/job/{jid}", response_class=HTMLResponse)
def job_page(request: Request, jid: str):
    return templates.TemplateResponse("job.html", {"request": request, "job_id": jid})


@app.get("/result/{jid}", response_class=HTMLResponse)
def result_page(request: Request, jid: str):
    job = get_job(jid)
    if not job or not job["result"]:
        return templates.TemplateResponse("job.html", {"request": request, "job_id": jid})
    return templates.TemplateResponse("result.html",
                                       {"request": request, "job": job,
                                        "report": fb.markdown(job["result"])})
