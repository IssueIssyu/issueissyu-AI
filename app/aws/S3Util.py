import boto3
from app.core.config import settings
from fastapi import UploadFile
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime

