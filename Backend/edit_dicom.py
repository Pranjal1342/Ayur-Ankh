import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import UID
import datetime

# --- CONFIGURATION ---
# 1. Path to your downloaded sample DICOM file
INPUT_FILE = "sample.dcm"  # <-- RENAME THIS to your actual file name

# 2. Name for the new, edited file
OUTPUT_FILE = "test_patient_good.dcm"

# 3. The Patient ID you want to inject (MUST match your form input)
NEW_PATIENT_ID = "PATIENT_GOOD_001"
NEW_PATIENT_NAME = "Test^Patient"

# ---------------------

try:
    # 1. Read the existing DICOM file
    print(f"Reading {INPUT_FILE}...")
    ds = pydicom.dcmread(INPUT_FILE, force=True)

    # 2. Edit the fields
    print(f"Changing PatientID from '{ds.PatientID}' to '{NEW_PATIENT_ID}'...")
    ds.PatientID = NEW_PATIENT_ID
    ds.PatientName = NEW_PATIENT_NAME

    # Optional: Update study date to today just to be neat
    dt = datetime.datetime.now()
    ds.StudyDate = dt.strftime('%Y%m%d')
    ds.StudyTime = dt.strftime('%H%M%S')

    # 3. Save as a new file
    # We need to ensure standard File Meta Information exists for it to be valid
    if not hasattr(ds, 'file_meta'):
        # Create minimal file meta if it doesn't exist
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = UID('1.2.840.10008.5.1.4.1.1.2')
        file_meta.MediaStorageSOPInstanceUID = UID('1.2.3')
        file_meta.ImplementationClassUID = UID('1.2.3.4')
        ds.file_meta = file_meta
        ds.is_little_endian = True
        ds.is_implicit_VR = True

    ds.save_as(OUTPUT_FILE)
    print(f"SUCCESS! Saved new DICOM file to: {OUTPUT_FILE}")
    print("Use this file for your 'Good' test case.")

except FileNotFoundError:
    print(f"ERROR: Could not find {INPUT_FILE}. Make sure it's in the same folder as this script.")
except Exception as e:
    print(f"An error occurred: {e}")