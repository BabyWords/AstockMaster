# -*- coding: utf-8 -*-
"""回测任务 —— 用子进程跑，避免把 web 进程撑爆。
================================================

为什么必须子进程：一次全样本回测峰值内存约 4.0GB，pandas 不还给系统。
放进 FastAPI 进程点两次就 OOM。这里只做「起进程 / 轮询状态 / 清理旧任务」。

任务状态保存在进程内字典（服务重启即清空），并做 TTL 回收 —— 原来只增不删，
跑几十次回测后字典里全是历史结果。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid

from fastapi import HTTPException

from config import JOB_DIR, ROOT
from quant import config as qcfg

PY = sys.executable
JOB_SCRIPT = os.path.join(ROOT, "scripts", "backtest_job.py")

_JOB_TTL = 3600.0        # 完成的任务保留 1 小时（够前端轮询与回看）
_JOB_MAX = 40            # 或最多留 40 条，防内存无限增长
_jobs: dict = {}
_lock = threading.Lock()


def _gc_locked(now: float):
    """清掉过期/超量的已完成任务（调用方必须已持锁）。"""
    dead = [k for k, j in _jobs.items()
            if j.get("status") != "running" and now - j.get("finished", now) > _JOB_TTL]
    for k in dead:
        _jobs.pop(k, None)
    if len(_jobs) > _JOB_MAX:
        done = sorted((k for k, j in _jobs.items() if j.get("status") != "running"),
                      key=lambda k: _jobs[k].get("finished", 0))
        for k in done[:len(_jobs) - _JOB_MAX]:
            _jobs.pop(k, None)


def start(strategy: str, params: dict, name: str | None = None) -> dict:
    """起一个回测子进程。同时只允许一个（内存原因）。"""
    with _lock:
        _gc_locked(time.time())
        for j in _jobs.values():
            if j.get("status") == "running":
                raise HTTPException(409, "已有回测在跑，请等它完成（一次只能跑一个）")
        job_id = uuid.uuid4().hex[:12]
        _jobs[job_id] = {"status": "running", "started": time.time()}

    qcfg.ensure_dir(JOB_DIR)
    spec_p = os.path.join(JOB_DIR, f"{job_id}.spec.json")
    out_p = os.path.join(JOB_DIR, f"{job_id}.out.json")
    with open(spec_p, "w", encoding="utf-8") as f:
        json.dump({"strategy": strategy, "name": name, "params": params},
                  f, ensure_ascii=False)

    def _run():
        res = None
        try:
            proc = subprocess.run([PY, JOB_SCRIPT, spec_p, out_p],
                                  capture_output=True, text=True,
                                  timeout=1800, cwd=ROOT)
            if os.path.exists(out_p):
                with open(out_p, encoding="utf-8") as fp:
                    res = json.load(fp)
            else:
                tail = (proc.stderr or proc.stdout or "无输出")[-1200:]
                res = {"ok": False, "error": tail}
        except Exception as e:                  # noqa: BLE001
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        finally:
            for p in (spec_p, out_p):
                try:
                    os.path.exists(p) and os.remove(p)
                except OSError:
                    pass
        with _lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update({"status": "done" if res.get("ok") else "error",
                            "result": res, "finished": time.time()})

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id, "strategy": strategy, "params": params}


def status(job_id: str) -> dict:
    with _lock:
        j = _jobs.get(job_id)
        if not j:
            raise HTTPException(404, "任务不存在（服务重启后任务列表会清空）")
        out = {"status": j["status"], "elapsed": round(time.time() - j["started"], 1)}
        if "result" in j:
            out["result"] = j["result"]
    return out
