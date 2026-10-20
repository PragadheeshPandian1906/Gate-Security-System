import os
import sys
import mimetypes
from pathlib import Path
from dotenv import load_dotenv

# Load backend/.env
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
dotenv_path = backend_dir / ".env"
load_dotenv(dotenv_path)

from supabase import create_client

URL = os.getenv("SUPABASE_URL")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not URL or not KEY:
    print(f"ERROR: SUPABASE_URL ({URL}) or SUPABASE_SERVICE_ROLE_KEY is missing from {dotenv_path}")
    exit(1)

print(f"Connecting to Supabase Storage at {URL}...")
supabase = create_client(URL, KEY)

# Map local folder names to Supabase bucket names
DIR_BUCKET_MAP = {
    "face_images": "face-images",
    "access_evidence": "access-evidence",
    "visitor_qr": "visitor-qr",
}

storage_root = backend_dir / "storage"

# Step 1: Ensure buckets exist
print("\n--- Ensuring Supabase buckets exist ---")
try:
    existing_buckets = [b.name for b in supabase.storage.list_buckets()]
    print(f"Existing buckets in Supabase: {existing_buckets}")
except Exception as e:
    print(f"Could not list buckets: {e}")
    existing_buckets = []

for dir_name, bucket_name in DIR_BUCKET_MAP.items():
    if bucket_name not in existing_buckets:
        print(f"Creating bucket '{bucket_name}'...")
        try:
            supabase.storage.create_bucket(bucket_name, options={"public": False})
            print(f"Successfully created bucket: {bucket_name}")
        except Exception as e:
            print(f"Bucket creation note/error for '{bucket_name}': {e}")
    else:
        print(f"Bucket '{bucket_name}' already exists.")

# Step 2: Iterate through all files in storage_root and upload
print("\n--- Synchronizing local files to Supabase Storage ---")
synced_count = 0
failed_count = 0

for dir_name, bucket_name in DIR_BUCKET_MAP.items():
    local_dir = storage_root / dir_name
    if not local_dir.exists():
        continue

    for file_path in local_dir.rglob("*"):
        if file_path.is_file():
            # Relative path within the local folder (e.g. enrollments/photo.jpg or face_queries/verify.jpg)
            relative_key = str(file_path.relative_to(local_dir)).replace("\\", "/")
            mime_type, _ = mimetypes.guess_type(file_path.name)
            content_type = mime_type or "application/octet-stream"
            
            data = file_path.read_bytes()
            print(f"Uploading [{bucket_name}] {relative_key} ({len(data)} bytes, {content_type})...")
            try:
                supabase.storage.from_(bucket_name).upload(
                    relative_key,
                    data,
                    {"content-type": content_type, "x-upsert": "true"}
                )
                print(f"  -> SUCCESS: {bucket_name}/{relative_key}")
                synced_count += 1
            except Exception as e:
                print(f"  -> FAILED {bucket_name}/{relative_key}: {e}")
                failed_count += 1

print(f"\n--- Sync Complete: {synced_count} uploaded, {failed_count} failed ---")

# Step 3: Backfill Database records
print("\n--- Updating Database storage_path columns ---")
from app.db.session import get_session_factory
from app.models.people import CampusPerson, FaceProfile, FaceVerification, AlprVerification

db = get_session_factory()()
updated_db_records = 0

# Face Profiles
profiles = db.query(FaceProfile).all()
for p in profiles:
    if p.image_path and not p.image_storage_path:
        fname = Path(p.image_path).name
        p.image_storage_path = f"face-images/enrollments/{fname}"
        updated_db_records += 1
        print(f"Updated FaceProfile {p.id} -> {p.image_storage_path}")

# Face Verifications
f_verifs = db.query(FaceVerification).all()
for v in f_verifs:
    if v.query_image_path and not v.query_image_storage_path:
        fname = Path(v.query_image_path).name
        v.query_image_storage_path = f"access-evidence/face_queries/{fname}"
        updated_db_records += 1
        print(f"Updated FaceVerification {v.id} -> {v.query_image_storage_path}")

# ALPR Verifications
a_verifs = db.query(AlprVerification).all()
for a in a_verifs:
    if a.query_image_path and not a.query_image_storage_path:
        fname = Path(a.query_image_path).name
        a.query_image_storage_path = f"access-evidence/plate_queries/{fname}"
        updated_db_records += 1
        print(f"Updated AlprVerification {a.id} -> {a.query_image_storage_path}")

db.commit()
db.close()
print(f"Database update complete: {updated_db_records} records linked to Supabase Storage.")

