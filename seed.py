#!/usr/bin/env python3
"""Upload seed files to the drive S3 bucket.

Run once after first deploy:
    AWS_PROFILE=tokenburner python3 seed.py
"""

import os
import sys
import boto3

ACCOUNT = boto3.Session(profile_name='tokenburner').client('sts').get_caller_identity()['Account']
BUCKET  = f"tokendrive-files-{ACCOUNT}"
PREFIX  = "drive/"

SEED_DIR = os.path.join(os.path.dirname(__file__), "seed_files")

MIME_MAP = {
    'md':   'text/plain',
    'pdf':  'application/pdf',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}

def main():
    s3 = boto3.Session(profile_name='tokenburner').client('s3')
    files = sorted(os.listdir(SEED_DIR))
    for filename in files:
        ext = filename.rsplit('.', 1)[-1].lower()
        mime = MIME_MAP.get(ext, 'application/octet-stream')
        key = PREFIX + filename
        path = os.path.join(SEED_DIR, filename)
        s3.upload_file(path, BUCKET, key, ExtraArgs={'ContentType': mime})
        size = os.path.getsize(path)
        print(f"  ✓ {filename:30s}  ({size:,} bytes)  →  s3://{BUCKET}/{key}")
    print(f"\nDone. Open your drive URL and you'll see {len(files)} sample files.")

if __name__ == '__main__':
    main()
