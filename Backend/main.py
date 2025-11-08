import os
import shutil
import uuid
import json
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from celery.result import AsyncResult
from celery_app import app as celery_app
from tasks import process_claim_async

app = FastAPI(title="AyurAnkh Async API")

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows ALL origins (for hackathon simplicity)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# --- In-Memory Databases ---
IMMUTABLE_LOGS = []
IDEMPOTENCY_DB = {}

@app.post("/process-claim-async/")
async def submit_claim_async(
    verified_patient_id: str = Form(...),
    doctor_diagnosis: str = Form(...),
    verified_identity_payload: Optional[str] = Form(None),
    digital_consent_payload: Optional[str] = Form(None),
    identity_document_image: Optional[UploadFile] = File(None),
    consent_form_image: Optional[UploadFile] = File(None),
    dicom_file: UploadFile = File(...),
    lab_report_pdf: Optional[UploadFile] = File(None),
    geotagged_patient_photo: Optional[UploadFile] = File(None),
    patient_geotag: Optional[str] = Form(None),
    idempotency_key: Optional[str] = Form(None)
):
    # 1. Idempotency Check
    if not idempotency_key:
         key_raw = f"{verified_patient_id}-{dicom_file.filename}-{doctor_diagnosis}"
         idempotency_key = hashlib.sha256(key_raw.encode()).hexdigest()
    
    # FIXED INDENTATION HERE
    if idempotency_key in IDEMPOTENCY_DB:
        return JSONResponse(status_code=409, content={
            "error": "Duplicate Submission Detected",
            "original_task_id": IDEMPOTENCY_DB[idempotency_key]
        })

    # 2. Create Temp Directory
    task_id = str(uuid.uuid4())
    temp_dir = os.path.join(os.getcwd(), "temp_uploads", task_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    file_paths = {}
    def save_file(up_file, key):
        path = os.path.join(temp_dir, up_file.filename)
        with open(path, "wb") as f: shutil.copyfileobj(up_file.file, f)
        file_paths[key] = path

    save_file(dicom_file, "dicom")
    if lab_report_pdf: save_file(lab_report_pdf, "lab_pdf")
    if geotagged_patient_photo: save_file(geotagged_patient_photo, "patient_photo")
    if identity_document_image: save_file(identity_document_image, "identity_doc")
    if consent_form_image: save_file(consent_form_image, "consent_image")

    # 3. Prepare Data
    identity_data = json.loads(verified_identity_payload) if verified_identity_payload else {}
    consent_data = json.loads(digital_consent_payload) if digital_consent_payload else {}

    claim_data = {
        "verified_patient_id": verified_patient_id,
        "doctor_diagnosis": doctor_diagnosis,
        "identity_data": identity_data,
        "consent_data": consent_data,
        "patient_geotag": patient_geotag
    }

    # 4. Launch Task
    process_claim_async.apply_async(args=[claim_data, file_paths], task_id=task_id)
    IDEMPOTENCY_DB[idempotency_key] = task_id

    return {"message": "Claim accepted.", "task_id": task_id, "idempotency_key": idempotency_key}

@app.get("/claim-status/{task_id}")
async def get_claim_status(task_id: str):
    res = AsyncResult(task_id, app=celery_app)
    resp = {"task_id": task_id, "status": res.status}
    if res.status in ['SUCCESS', 'FAILURE']: resp["result"] = res.result
    elif res.status in ['PROCESSING', 'VALIDATING']: resp["info"] = res.info
    return resp

@app.post("/doctor-override/")
async def doctor_override(task_id: str = Form(...), doctor_id: str = Form(...), override_reason: str = Form(...)):
    log = {"event": "OVERRIDE", "timestamp": datetime.utcnow().isoformat(), "task_id": task_id, "doctor_id": doctor_id, "reason": override_reason, "signature": hashlib.sha256(f"{task_id}{doctor_id}{override_reason}".encode()).hexdigest()}
    IMMUTABLE_LOGS.append(log)
    return {"status": "OVERRIDE_ACCEPTED", "log": log}

@app.get("/logs/")
async def view_logs(): return IMMUTABLE_LOGS

@app.post("/abdm/hce/submit-claim")
async def mock_hce_submit(payload: Dict[str, Any]):
    return {"status": "ACCEPTED", "hce_txn_id": f"HCE_{uuid.uuid4()}"}