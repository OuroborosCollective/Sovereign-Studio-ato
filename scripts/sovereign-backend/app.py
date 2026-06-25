#!/usr/bin/env python3
from flask import Flask, request, jsonify
import requests
import uuid
import time
import os
import threading

app = Flask(__name__)

LLM_PROXY_KEY = os.getenv("LLM_PROXY_KEY", "")

def get_oh_key():
    if os.path.exists("/opt/secure/openhands_api_key.txt"):
        with open("/opt/secure/openhands_api_key.txt") as f:
            return f.read().strip()
    return os.getenv("OPENHANDS_API_KEY", "")

OPENHANDS_API_URL = os.getenv("OPENHANDS_API_URL", "http://127.0.0.1:3000")

jobs = {}
events_lock = threading.Lock()

def oh_headers():
    return {
        "Content-Type": "application/json",
        "X-Session-API-Key": get_oh_key()
    }

def poll_oh_events(job_id, oh_conv_id):
    """Poll OpenHands for events and update job."""
    try:
        resp = requests.get(
            f"{OPENHANDS_API_URL}/api/conversations/{oh_conv_id}/events/search?limit=50&sort_order=TIMESTAMP_DESC",
            headers=oh_headers(),
            timeout=30
        )
        if resp.ok:
            events_data = resp.json()
            events = events_data.get("items", [])
            with events_lock:
                if job_id in jobs:
                    job = jobs[job_id]
                    runtime_events = []
                    for e in events[:20]:
                        kind = e.get("kind", "")
                        msg = ""
                        level = "info"
                        
                        if kind == "ActionEvent":
                            tool = e.get("tool_name", "unknown")
                            msg = f"Agent action: {tool}"
                        elif kind == "ObservationEvent":
                            tool = e.get("tool_name", "")
                            msg = f"Tool result: {tool}"
                        elif kind == "ErrorEvent":
                            msg = e.get("message", "Error")
                            level = "error"
                        elif kind == "MessageEvent":
                            role = e.get("role", "")
                            content = e.get("message", "")
                            msg = f"{role}: {content[:100]}"
                        elif kind == "ConversationStatusEvent":
                            status = e.get("status", "")
                            msg = f"Status: {status}"
                            if status in ["stopped", "finished"]:
                                level = "success"
                        
                        runtime_events.append({
                            "at": int(time.time()),
                            "level": level,
                            "stage": "openhands",
                            "message": msg or f"Event: {kind}"
                        })
                    
                    if job["status"] == "running":
                        for e in events:
                            if e.get("kind") == "ConversationStatusEvent" and e.get("status") in ["stopped", "finished", "failed"]:
                                job["status"] = "completed"
                                runtime_events.append({
                                    "at": int(time.time()),
                                    "level": "success",
                                    "stage": "openhands",
                                    "message": "OpenHands completed"
                                })
                                break
                    
                    job["events"] = runtime_events
    except Exception as e:
        with events_lock:
            if job_id in jobs:
                jobs[job_id]["events"].append({
                    "at": int(time.time()),
                    "level": "error",
                    "stage": "openhands",
                    "message": f"Poll error: {str(e)[:50]}"
                })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": time.time()})

@app.route("/openhands/jobs", methods=["POST"])
def create_job():
    data = request.json or {}
    if not data.get("repoUrl"):
        return jsonify({"error": "repoUrl required", "status": "blocked"}), 400
    if not data.get("mission"):
        return jsonify({"error": "mission required", "status": "blocked"}), 400

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    oh_conv_id = None
    error_msg = None

    try:
        payload = {
            "workspace": {"kind": "LocalWorkspace", "working_dir": "/workspace"},
            "initial_message": {
                "content": [{"type": "text", "text": data["mission"]}],
                "run": True
            },
            "agent_settings": {
                "agent": "CodeActAgent",
                "llm_config": {
                    "model": "openai/@cf/meta/llama-3.1-8b-instruct-fp8",
                    "api_key": LLM_PROXY_KEY,
                    "base_url": "https://openhands-llm-proxy.projectouroboroscollective.workers.dev/v1"
                }
            }
        }

        create_resp = requests.post(
            f"{OPENHANDS_API_URL}/api/conversations",
            headers=oh_headers(),
            json=payload,
            timeout=30
        )

        if create_resp.status_code in (200, 201):
            oh_data = create_resp.json()
            oh_conv_id = oh_data.get("id")
        else:
            error_msg = f"API Error: {create_resp.status_code}"

    except Exception as e:
        error_msg = f"Connection error: {str(e)[:100]}"

    if error_msg:
        return jsonify({"error": error_msg, "status": "blocked"}), 502

    job = {
        "jobId": job_id,
        "status": "running" if oh_conv_id else "blocked",
        "ohConvId": oh_conv_id,
        "repoUrl": data["repoUrl"],
        "mission": data["mission"],
        "draftPrOnly": data.get("draftPrOnly", True),
        "createdAt": time.time(),
        "events": [{
            "at": int(time.time()),
            "level": "info",
            "stage": "openhands",
            "message": "Conversation started"
        }]
    }
    
    with events_lock:
        jobs[job_id] = job
    
    if oh_conv_id:
        t = threading.Thread(target=poll_oh_events, args=(job_id, oh_conv_id), daemon=True)
        t.start()
    
    return jsonify(job), 201

@app.route("/openhands/jobs/<job_id>")
def get_job(job_id):
    with events_lock:
        if job_id not in jobs:
            return jsonify({"error": "Job not found"}), 404
        
        job = jobs[job_id].copy()
        
        if job.get("ohConvId") and job["status"] == "running":
            try:
                resp = requests.get(
                    f"{OPENHANDS_API_URL}/api/conversations/{job['ohConvId']}/events/search?limit=10&sort_order=TIMESTAMP_DESC",
                    headers=oh_headers(),
                    timeout=10
                )
                if resp.ok:
                    for e in resp.json().get("items", []):
                        if e.get("kind") == "ConversationStatusEvent" and e.get("status") in ["stopped", "finished", "failed"]:
                            job["status"] = "completed"
                            break
            except:
                pass
        
        return jsonify(job)

@app.route("/openhands/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id):
    with events_lock:
        if job_id not in jobs:
            return jsonify({"error": "Job not found"}), 404
        jobs[job_id]["status"] = "blocked"
        jobs[job_id]["events"].append({
            "at": int(time.time()),
            "level": "warning",
            "stage": "openhands",
            "message": "Cancelled by user"
        })
        return jsonify(jobs[job_id])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8787)
