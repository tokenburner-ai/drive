#!/usr/bin/env python3
"""Upload seed files to the drive S3 bucket and index them in DynamoDB.

Run once after first deploy:
    AWS_PROFILE=tokenburner python3 seed.py

For a named-suffix deployment (e.g. test):
    AWS_PROFILE=tokenburner python3 seed.py --suffix -test
"""

import os
import sys
import time
import boto3

SUFFIX  = sys.argv[sys.argv.index('--suffix') + 1] if '--suffix' in sys.argv else ''

session = boto3.Session(profile_name=os.environ.get('AWS_PROFILE', 'tokenburner'))
ACCOUNT = session.client('sts').get_caller_identity()['Account']
BUCKET  = f"tokendrive-files-{ACCOUNT}{SUFFIX}"
TABLE   = f"tokendrive-index{SUFFIX}"
PREFIX  = "drive/"

SEED_DIR = os.path.join(os.path.dirname(__file__), "seed_files")

MIME_MAP = {
    'md':   'text/plain',
    'pdf':  'application/pdf',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}

def main():
    region = os.environ.get('AWS_REGION', 'us-west-2')
    s3  = session.client('s3', region_name=region)
    ddb = session.resource('dynamodb', region_name=region).Table(TABLE)

    files = sorted(f for f in os.listdir(SEED_DIR) if not f.startswith('.'))
    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    for filename in files:
        ext  = filename.rsplit('.', 1)[-1].lower()
        mime = MIME_MAP.get(ext, 'application/octet-stream')
        key  = PREFIX + filename
        path = os.path.join(SEED_DIR, filename)
        size = os.path.getsize(path)

        s3.upload_file(path, BUCKET, key, ExtraArgs={'ContentType': mime})

        ddb.put_item(Item={
            'pk': f'folder#{PREFIX}',
            'sk': filename,
            'type': 'file',
            'key': key,
            'size': size,
            'last_modified': now,
            'ext': ext,
        })

        print(f"  ✓ {filename:30s}  ({size:,} bytes)")

    print(f"\nIndexed {len(files)} files in {TABLE} and uploaded to s3://{BUCKET}/{PREFIX}")

if __name__ == '__main__':
    main()
