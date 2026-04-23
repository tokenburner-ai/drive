#!/usr/bin/env python3
"""Token Drive CDK app."""

import os
import aws_cdk as cdk
from stack import DriveStack

app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-west-2"),
)

DriveStack(app, "tokenburner-drive", env=env)

app.synth()
