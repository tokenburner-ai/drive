"""Extract EXIF metadata and generate AI descriptions via Bedrock."""
import base64
import hashlib
import json
import os
from datetime import datetime

import boto3
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

from config import AWS_PROFILE, AWS_REGION, BEDROCK_MODEL


def file_sha256(filepath):
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_exif(filepath):
    """Extract EXIF metadata from an image file."""
    try:
        img = Image.open(filepath)
        exif_data = img._getexif()
        if not exif_data:
            return {}
        result = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if isinstance(value, bytes):
                continue  # skip binary blobs
            if isinstance(value, str) and len(value) > 500:
                continue  # skip huge strings
            result[str(tag)] = str(value)
        return result
    except Exception:
        return {}


def extract_gps(filepath):
    """Extract GPS coordinates from EXIF if present."""
    try:
        img = Image.open(filepath)
        exif_data = img._getexif()
        if not exif_data:
            return None
        gps_info = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for gps_tag_id in value:
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_info[gps_tag] = value[gps_tag_id]
        if not gps_info:
            return None
        # Convert to decimal degrees
        def to_degrees(val):
            d, m, s = val
            return float(d) + float(m) / 60 + float(s) / 3600
        if "GPSLatitude" in gps_info and "GPSLongitude" in gps_info:
            lat = to_degrees(gps_info["GPSLatitude"])
            lon = to_degrees(gps_info["GPSLongitude"])
            if gps_info.get("GPSLatitudeRef", "N") == "S":
                lat = -lat
            if gps_info.get("GPSLongitudeRef", "E") == "W":
                lon = -lon
            return {"lat": lat, "lon": lon}
    except Exception:
        return None


def get_date_taken(exif, filepath):
    """Get date taken from EXIF or fall back to file mtime."""
    for field in ["DateTimeOriginal", "DateTime", "DateTimeDigitized"]:
        if field in exif:
            try:
                return datetime.strptime(exif[field], "%Y:%m:%d %H:%M:%S").isoformat()
            except ValueError:
                pass
    # Fall back to file modification time
    return datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()


def ai_describe(filepath, bedrock_client=None):
    """Use Bedrock Claude Vision to generate rich metadata for an image."""
    if bedrock_client is None:
        session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
        bedrock_client = session.client("bedrock-runtime")

    # Read and encode image
    with open(filepath, "rb") as f:
        image_data = f.read()

    # Determine media type
    ext = os.path.splitext(filepath)[1].lower()
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp",
    }
    media_type = media_types.get(ext, "image/jpeg")

    # Skip if file is too large for vision (>20MB)
    if len(image_data) > 20_000_000:
        return {"description": "File too large for AI processing", "tags": [], "era_estimate": "unknown"}

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.b64encode(image_data).decode(),
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a personal photo being archived. Provide:\n"
                            "1. A one-sentence description of the scene\n"
                            "2. A list of 5-10 keyword tags (people count, objects, setting, mood, activity)\n"
                            "3. Estimated era/decade based on photo quality, clothing, technology visible\n"
                            "4. Indoor or outdoor\n"
                            "5. Any text visible in the image\n\n"
                            "Respond in JSON: {\"description\": \"...\", \"tags\": [...], "
                            "\"era_estimate\": \"...\", \"setting\": \"indoor|outdoor|unknown\", "
                            "\"visible_text\": \"...\"}"
                        ),
                    },
                ],
            }
        ],
    })

    response = bedrock_client.invoke_model(
        modelId=BEDROCK_MODEL,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]

    # Parse JSON from response (handle markdown code blocks)
    if "```" in text:
        text = text.split("```json")[-1].split("```")[0] if "```json" in text else text.split("```")[1].split("```")[0]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {"description": text.strip(), "tags": [], "era_estimate": "unknown"}


def build_metadata(filepath, dropbox_path):
    """Build complete metadata for a file."""
    sha256 = file_sha256(filepath)
    exif = extract_exif(filepath)
    gps = extract_gps(filepath)
    date_taken = get_date_taken(exif, filepath)
    file_size = os.path.getsize(filepath)
    ext = os.path.splitext(filepath)[1].lower()

    meta = {
        "sha256": sha256,
        "source": "dropbox",
        "source_path": dropbox_path,
        "date_taken": date_taken,
        "file_size": file_size,
        "extension": ext,
        "imported_at": datetime.utcnow().isoformat(),
    }

    if exif:
        meta["exif"] = {
            k: v for k, v in exif.items()
            if k in ("Make", "Model", "LensModel", "FocalLength",
                     "ExposureTime", "FNumber", "ISOSpeedRatings",
                     "ImageWidth", "ImageLength")
        }

    if gps:
        meta["gps"] = gps

    # AI description for supported image formats
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        try:
            ai_meta = ai_describe(filepath)
            meta["ai"] = ai_meta
        except Exception as e:
            meta["ai_error"] = str(e)

    return meta
