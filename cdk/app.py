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

name_suffix          = app.node.try_get_context("name_suffix") or ""
api_keys_table_name  = app.node.try_get_context("api_keys_table_name") or None
api_keys_table_arn   = app.node.try_get_context("api_keys_table_arn") or None
stack_name = f"tokenburner-drive{name_suffix}"

DriveStack(
    app, stack_name, env=env,
    name_suffix=name_suffix,
    api_keys_table_name=api_keys_table_name,
    api_keys_table_arn=api_keys_table_arn,
)

app.synth()
