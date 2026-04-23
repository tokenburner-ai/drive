"""Shared AWS boto3 session.

In Lambda: uses default credentials (IAM role).
Locally: uses the 'tokenburner' AWS profile.
"""

import os
import boto3

AWS_REGION = os.environ.get('AWS_REGION_NAME', os.environ.get('AWS_REGION', 'us-west-2'))
_in_lambda = 'AWS_LAMBDA_FUNCTION_NAME' in os.environ


def get_session():
    if _in_lambda:
        return boto3.Session(region_name=AWS_REGION)
    return boto3.Session(region_name=AWS_REGION, profile_name='tokenburner')


def get_client(service, region=None):
    return get_session().client(service, region_name=region or AWS_REGION)
