# Token Drive

A personal file drive backed by S3 + DynamoDB, deployed as a Lambda + CloudFront stack.
Zero idle cost. Runs entirely in your AWS account.

## Pre-requisites

Before deploying, verify the tokenburner base stack is deployed:

```bash
AWS_PROFILE=tokenburner aws cloudformation describe-stacks \
  --stack-name tokenburner-base \
  --query 'Stacks[0].StackStatus' --output text
```

Expected: `CREATE_COMPLETE` or `UPDATE_COMPLETE`

If not deployed, see https://github.com/tokenburner-ai/stack

## Deploy

```bash
cd cdk
pip install -r requirements.txt   # aws-cdk-lib, constructs

AWS_PROFILE=tokenburner \
  CDK_DEFAULT_ACCOUNT=$(AWS_PROFILE=tokenburner aws sts get-caller-identity --query Account --output text) \
  CDK_DEFAULT_REGION=us-west-2 \
  npx cdk deploy tokenburner-drive --require-approval never
```

The deploy takes ~2 minutes. When it completes, copy the `DriveUrl` output — that is your drive URL.

## Set your API key

The drive ships with an empty API key (open access after deploy). Set a key immediately:

```bash
AWS_PROFILE=tokenburner aws lambda update-function-configuration \
  --function-name tokenburner-drive \
  --environment "Variables={
    DRIVE_BUCKET=tokendrive-files-YOUR_ACCOUNT_ID,
    DRIVE_TABLE=tokendrive-index,
    DRIVE_API_KEY=your-secret-key-here
  }"
```

Choose any string as your key. A UUID works well:
```bash
python3 -c "import uuid; print(uuid.uuid4())"
```

## Access the drive

Open your `DriveUrl` in a browser. You'll see the key gate — paste your API key.

The key is stored in `sessionStorage` for the browser session. To stay logged in across sessions, bookmark the URL with your key appended:

```
https://YOUR_CLOUDFRONT_DOMAIN/?key=YOUR_API_KEY
```

Or pass it as a header for programmatic access:
```
X-Drive-Key: YOUR_API_KEY
```

## Seed files

On first deploy, the drive is empty. Load the sample README files to verify everything works:

```bash
AWS_PROFILE=tokenburner python3 seed.py
```

This uploads README.md, README.pdf, README.xlsx, README.docx to the drive root.
You can delete them from the UI whenever you like.

## Local development

```bash
docker compose up --build -d
# Drive at http://localhost:8082
# Set DRIVE_API_KEY in docker-compose.yml for local auth
```

## File structure

```
drive-dev/
├── CLAUDE.md             # This file
├── app/
│   ├── main.py           # Flask app entry point
│   ├── drive_api.py      # All drive routes
│   └── aws.py            # boto3 session helper
├── static/
│   └── drive.html        # Full drive UI (single file)
├── cdk/
│   ├── app.py            # CDK entry point
│   ├── stack.py          # DriveStack: Lambda + CF + S3 + DynamoDB
│   └── cdk.json
├── seed_files/           # Sample files for first deploy
├── seed.py               # Upload seed files to S3
├── lambda_handler.py     # Lambda WSGI wrapper
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## What's deployed

| Resource | Name | Cost |
|----------|------|------|
| Lambda | `tokenburner-drive` | $0/mo idle |
| CloudFront | auto-assigned domain | $0/mo idle |
| S3 | `tokendrive-files-{account}` | ~$0.023/GB/mo |
| DynamoDB | `tokendrive-index` | $0/mo (free tier) |

## Options — ask Claude to add any of these

### Custom domain
Add a subdomain like `drive.yourdomain.com`. Requires:
- A Route53 hosted zone, OR a Cloudflare DNS CNAME
- An ACM certificate for the domain

Ask Claude: *"Add drive.yourdomain.com as a custom domain for the Token Drive"*

### Google OAuth login
Replace the API key gate with Google Sign-In. Requires:
- A Google OAuth client ID (console.cloud.google.com)
- Adding `GOOGLE_CLIENT_ID` to the Lambda environment

Ask Claude: *"Replace the API key auth with Google OAuth on the Token Drive"*

### Dropbox import
Pull all files from a Dropbox account into the drive.
The `sync_cigar_lounge.py` pattern in this repo shows how to do it.

Ask Claude: *"Set up a Dropbox import for the Token Drive"*

### S3 storage tiering
Move older files to cheaper storage classes automatically.

Ask Claude: *"Add S3 Intelligent-Tiering lifecycle rules to the drive bucket"*

### Read-only sharing
Create a second API key with read-only access (no upload/delete).

Ask Claude: *"Add a read-only API key to the Token Drive for family sharing"*
