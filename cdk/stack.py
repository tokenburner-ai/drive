"""Token Drive Stack — Lambda + CloudFront + S3 + DynamoDB.

Pre-requisite: tokenburner-base stack must be deployed.
Imports: tokenburner-api-keys-table-name (not used directly, reserved for future auth options)

Cost: ~$0/mo idle. S3 storage + DynamoDB on-demand are the only variable costs.
"""

import os
import aws_cdk as cdk
from aws_cdk import (
    aws_lambda as _lambda,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
)
from constructs import Construct

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


class DriveStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, *, name_suffix: str = "", **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        cdk.Tags.of(self).add("ManagedBy", "tokenburner")
        cdk.Tags.of(self).add("tokenburner:stack", "drive")

        # ── S3 bucket (file storage) ──────────────────────────────────────────
        bucket = s3.Bucket(
            self,
            "DriveFiles",
            bucket_name=f"tokendrive-files-{self.account}{name_suffix}",
            versioned=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    noncurrent_version_expiration=cdk.Duration.days(90),
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # ── DynamoDB table (folder/file index) ────────────────────────────────
        table = dynamodb.Table(
            self,
            "DriveIndex",
            table_name=f"tokendrive-index{name_suffix}",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="sk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        # ── Lambda function ───────────────────────────────────────────────────
        fn = _lambda.Function(
            self,
            "Handler",
            function_name=f"tokenburner-drive{name_suffix}",
            runtime=_lambda.Runtime.PYTHON_3_12,
            architecture=_lambda.Architecture.ARM_64,
            handler="lambda_handler.handler",
            code=_lambda.Code.from_asset(
                path=PROJECT_ROOT,
                bundling=cdk.BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    platform="linux/arm64",
                    command=[
                        "bash", "-c",
                        "pip install flask apig-wsgi boto3 -t /asset-output --quiet && "
                        "cp -r app/* /asset-output/ && "
                        "cp lambda_handler.py /asset-output/ && "
                        "cp -r static /asset-output/",
                    ],
                ),
            ),
            memory_size=512,
            timeout=cdk.Duration.seconds(30),
            environment={
                "DRIVE_BUCKET": bucket.bucket_name,
                "DRIVE_TABLE": table.table_name,
                # DRIVE_API_KEY is set post-deploy via AWS console or CLI
                # (avoids storing the key in CDK/CloudFormation output)
                "DRIVE_API_KEY": "",
            },
        )

        # IAM: S3 full access on the drive bucket
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                    "s3:ListBucket", "s3:HeadObject",
                ],
                resources=[bucket.bucket_arn, f"{bucket.bucket_arn}/*"],
            )
        )

        # IAM: DynamoDB read/write on the index table
        table.grant_read_write_data(fn)

        # Lambda function URL (CloudFront is the entry point)
        fn_url = fn.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.NONE,
        )

        # ── CloudFront distribution ───────────────────────────────────────────
        distribution = cloudfront.Distribution(
            self,
            "CDN",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.FunctionUrlOrigin(fn_url),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
            ),
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        cdk.CfnOutput(self, "DriveUrl",
            value=f"https://{distribution.distribution_domain_name}",
            description="Token Drive URL — open this in your browser",
        )
        cdk.CfnOutput(self, "DriveBucket",
            value=bucket.bucket_name,
            description="S3 bucket storing your files",
        )
        cdk.CfnOutput(self, "LambdaFunctionUrl",
            value=fn_url.url,
            description="Lambda function URL — use as origin for the website CloudFront distribution",
        )
        cdk.CfnOutput(self, "SetApiKeyCommand",
            value=(
                f"aws lambda update-function-configuration "
                f"--function-name tokenburner-drive{name_suffix} "
                f"--environment 'Variables={{DRIVE_BUCKET={bucket.bucket_name},"
                f"DRIVE_TABLE={table.table_name},"
                f"DRIVE_API_KEY=YOUR_KEY_HERE}}'"
            ),
            description="Run this command (with your chosen key) to set the API key",
        )
