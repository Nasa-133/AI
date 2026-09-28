"""S3 bucket’larini zaxiralash/tiklash (restore mashqi uchun): obyektlar + SHA-256 manifest.

  s3_snapshot.py backup  --out DIR  bucket...
  s3_snapshot.py restore --src DIR  --suffix -restore
  s3_snapshot.py verify  --src DIR  --suffix -restore   # tiklangan obyektlar checksum’i manifestga teng
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import boto3


def client():  # type: ignore[no-untyped-def]
    return boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000"),
                        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "abo"),
                        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "abo_dev_password"),
                        region_name="us-east-1")


def backup(out: Path, buckets: list[str]) -> None:
    s3 = client()
    manifest: dict[str, dict[str, str]] = {}
    for bucket in buckets:
        manifest[bucket] = {}
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                target = out / bucket / obj["Key"]
                target.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(bucket, obj["Key"], str(target))
                manifest[bucket][obj["Key"]] = hashlib.sha256(target.read_bytes()).hexdigest()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps({b: len(v) for b, v in manifest.items()}))


def restore(src: Path, suffix: str) -> None:
    s3 = client()
    manifest = json.loads((src / "manifest.json").read_text())
    for bucket, objects in manifest.items():
        target = bucket + suffix
        try:
            s3.head_bucket(Bucket=target)
        except Exception:
            s3.create_bucket(Bucket=target)
        for key in objects:
            s3.upload_file(str(src / bucket / key), target, key)


def verify(src: Path, suffix: str) -> int:
    s3 = client()
    manifest = json.loads((src / "manifest.json").read_text())
    bad = 0
    for bucket, objects in manifest.items():
        for key, digest in objects.items():
            body = s3.get_object(Bucket=bucket + suffix, Key=key)["Body"].read()
            if hashlib.sha256(body).hexdigest() != digest:
                bad += 1
                print(f"checksum mos emas: {bucket}/{key}", file=sys.stderr)
    total = sum(len(v) for v in manifest.values())
    print(f"obyektlar: {total}, mos kelmagan: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["backup", "restore", "verify"])
    p.add_argument("buckets", nargs="*")
    p.add_argument("--out")
    p.add_argument("--src")
    p.add_argument("--suffix", default="-restore")
    a = p.parse_args()
    if a.action == "backup":
        backup(Path(a.out), a.buckets)
    elif a.action == "restore":
        restore(Path(a.src), a.suffix)
    else:
        raise SystemExit(verify(Path(a.src), a.suffix))
