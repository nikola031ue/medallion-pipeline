import glob
import os

os.environ["HOME"] = "/tmp"
os.environ["KAGGLE_CACHE"] = "/tmp/kaggle"

import boto3
import kagglehub

BUCKET = os.environ["BUCKET_NAME"]
BRONZE_KEY = os.environ["BRONZE_KEY"]
KAGGLE_DATASET = os.environ["KAGGLE_DATASET"]

s3 = boto3.client("s3")


def lambda_handler(event, context):
    dataset_path = kagglehub.dataset_download(KAGGLE_DATASET)
    print(f"Dataset downloaded to: {dataset_path}")

    csv_files = glob.glob(os.path.join(dataset_path, "**/*.csv"), recursive=True)
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {dataset_path}")

    csv_path = csv_files[0]
    print(f"Uploading: {csv_path}")

    with open(csv_path, "rb") as f:
        s3.put_object(
            Bucket=BUCKET,
            Key=BRONZE_KEY,
            Body=f.read(),
            ContentType="text/csv",
        )

    print(f"Uploaded → s3://{BUCKET}/{BRONZE_KEY}")
