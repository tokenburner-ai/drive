Token Drive — Welcome

This is your personal file drive, backed by Amazon S3 and indexed in DynamoDB.
It runs entirely in your AWS account — no third-party storage, no subscriptions.

Getting Started
---------------
- Upload files by clicking "Upload" or dragging and dropping into any folder
- Create folders with the "New Folder" button
- Click any file to preview it inline (PDF, images, Office docs, text)
- Download files with the ⬇ button
- Rename or delete files from the ⋯ menu

Access
------
Your drive is protected by an API key that was shown when you deployed.
You can share the drive URL with ?key=YOUR_KEY to grant direct access,
or bookmark it in your browser for convenience.

Cost
----
Storage:   ~$0.023/GB/month (S3 Standard)
Compute:   $0/month idle (Lambda + CloudFront free tier)
Database:  $0/month (DynamoDB on-demand, free tier covers all metadata)

Customization Options
---------------------
Prompt your AI assistant to help you with any of these:
  - Add a custom domain (e.g. drive.yourdomain.com)
  - Enable Google OAuth login instead of API key
  - Set up Dropbox / iCloud / Google Drive import
  - Add thumbnail generation for photos
  - Enable family sharing (read-only API keys)
  - Move to cheaper S3 storage tiers for archives

Files in This Folder
--------------------
README.md      — This file (Markdown)
README.pdf     — This file (PDF)
README.xlsx    — This file (Excel)
README.docx    — This file (Word)

You can delete these sample files whenever you like.
