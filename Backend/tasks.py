import os
import time
import shutil
import json
from typing import Dict, Any, List

import pydicom
import pytesseract
import fitz  # PyMuPDF
from PIL import Image
from celery import shared_task
from fhir.resources.patient import Patient
from fhir.resources.observation import Observation
from fhir.resources.bundle import Bundle

# --- Tesseract Path (Windows) ---
# UPDATE THIS PATH IF NEEDED FOR YOUR TEAM'S MACHINE
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# --- Helper Functions ---
def _process_dicom(file_path: str) -> Dict[str, Any]:
    try:
        ds = pydicom.dcmread(file_path, force=True)
        return {
            "PatientID": str(ds.get("PatientID", "N/A")),
            "PatientName": str(ds.get("PatientName", "N/A")),
            "AccessionNumber": str(ds.get("AccessionNumber", "N/A")),
            "StudyDate": str(ds.get("StudyDate", "N/A")),
            "Modality": str(ds.get("Modality", "N/A")),
        }
    except Exception as e:
        return {"error": str(e)}

def _process_pdf(file_path: str) -> str:
    try:
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        return f"PDF Error: {e}"

def _process_image_ocr(file_path: str) -> str:
    try:
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img)
        return text
    except Exception as e:
        return f"OCR Error: {e}"

def _run_validation_engine(claim_data, dicom_meta, lab_text, file_paths, ocr_results) -> Dict[str, Any]:
    """
    The 'Agentic' Zero-Trust Engine.
    """
    failures = []
    
    # RULE 1: Identity Verification (CRITICAL)
    verified_id = str(claim_data.get("verified_patient_id")).strip()
    dicom_id = str(dicom_meta.get("PatientID")).strip()
    
    if dicom_meta.get("error"):
         failures.append({"confidence": "CRITICAL", "reason": f"DICOM Corrupt: {dicom_meta['error']}"})
    elif verified_id != dicom_id:
        failures.append({"confidence": "CRITICAL", "reason": f"Patient ID Mismatch: Form({verified_id}) vs DICOM({dicom_id})"})

    # RULE 2: Clinical Consistency (HIGH)
    diag = claim_data.get("doctor_diagnosis", "").lower()
    lab = lab_text.lower()
    if ("critical" in diag or "fracture" in diag) and "normal" in lab:
         failures.append({"confidence": "HIGH", "reason": "Lab report says 'Normal' but Diagnosis is Critical."})

    # RULE 3: Fraud Detection - Geotag (MEDIUM)
    # If a patient photo was uploaded but NO geotag string was provided, flag it.
    if file_paths.get("patient_photo") and not claim_data.get("patient_geotag"):
        failures.append({"confidence": "MEDIUM", "reason": "Patient photo provided, but GPS geotag data is missing."})

    # RULE 4: Consent Verification (CRITICAL)
    # Must have EITHER a digital payload OR an uploaded image
    if not claim_data.get("consent_data") and not file_paths.get("consent_image"):
         failures.append({"confidence": "CRITICAL", "reason": "Missing Patient Consent (Payload or Image required)."})

    if not failures: return {"status": "PASSED"}
    if any(f["confidence"] == "CRITICAL" for f in failures): return {"status": "FAILED_CRITICAL", "failures": failures}
    if any(f["confidence"] == "HIGH" for f in failures): return {"status": "FLAGGED_HIGH", "failures": failures}
    return {"status": "PASSED_MEDIUM", "failures": failures}

def _generate_mock_fhir(claim_data) -> Dict[str, Any]:
    """Generates a valid FHIR Bundle."""
    try:
        patient = Patient(id=claim_data["verified_patient_id"])
        obs = Observation(
            status="final",
            code={"text": "Diagnosis"},
            valueString=claim_data["doctor_diagnosis"],
            subject={"reference": f"Patient/{patient.id}"}
        )
        bundle = Bundle(
            type="transaction",
            entry=[
                {"resource": patient, "request": {"method": "POST", "url": "Patient"}},
                {"resource": obs, "request": {"method": "POST", "url": "Observation"}}
            ]
        )
        return json.loads(bundle.json())
    except Exception as e:
        return {"error": f"FHIR Generation Failed: {e}"}

# --- MAIN CELERY TASK ---
@shared_task(bind=True, name="tasks.process_claim_async")
def process_claim_async(self, claim_data: Dict[str, Any], file_paths: Dict[str, str]):
    """
    Background task to process all files and run validation.
    """
    results = {"status": "PROCESSING", "steps_completed": [], "ocr_results": {}}
    
    try:
        # 1. DICOM Processing (Heavy I/O)
        self.update_state(state='PROCESSING', meta={'step': 'Processing DICOM...'})
        results["dicom_metadata"] = _process_dicom(file_paths["dicom"])
        results["steps_completed"].append("DICOM")

        # 2. Optional OCR Tasks (Heavy CPU)
        # We loop through possible optional files and OCR them if they exist
        for key, label in [("lab_pdf", "LAB_PDF"), ("identity_doc", "IDENTITY_OCR"), ("consent_image", "CONSENT_OCR")]:
            if file_paths.get(key):
                self.update_state(state='PROCESSING', meta={'step': f'Reading {label}...'})
                
                if key == "lab_pdf":
                    # Use specialized PDF reader
                    text = _process_pdf(file_paths[key])
                    # Special case: save lab text separately for validation engine
                    results["lab_report_text"] = text
                else:
                    # Use generic Image OCR for identity/consent images
                    text = _process_image_ocr(file_paths[key])
                
                results["ocr_results"][key] = text
                results["steps_completed"].append(label)

        # Ensure lab text exists even if file wasn't provided, to avoid KeyErrors
        if "lab_report_text" not in results:
            results["lab_report_text"] = "N/A"

        # 3. Run "Zero-Trust" Validation Engine (CPU)
        self.update_state(state='VALIDATING', meta={'step': 'Running AI Validation Agents...'})
        val_res = _run_validation_engine(claim_data, results["dicom_metadata"], results["lab_report_text"], file_paths, results["ocr_results"])
        results["validation_result"] = val_res
        
        # 4. Generate FHIR Bundle (Simulated)
        if val_res["status"] in ["PASSED", "FLAGGED_HIGH", "PASSED_MEDIUM"]:
             results["fhir_bundle"] = _generate_mock_fhir(claim_data)

        # 5. Final Status Determination
        if val_res["status"] == "FAILED_CRITICAL":
            results["status"] = "FAILED"
        elif val_res["status"] == "FLAGGED_HIGH":
             results["status"] = "FLAGGED" # Needs override
        else:
            results["status"] = "COMPLETED"

        return results

    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
    finally:
        # Cleanup: In a real app, we'd delete temp files here.
        # For demo, we might want to keep them to show they were uploaded.
        pass