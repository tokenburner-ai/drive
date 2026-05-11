# Token Drive

Personal file storage for the
[tokenburner](https://github.com/tokenburner-ai/stack) suite. Lambda +
CloudFront + S3 + DynamoDB. Zero idle cost.

## Install

```bash
git clone https://github.com/tokenburner-ai/stack.git
cd stack
python3 tokenburner.py install --features drive
```

## Standalone

The base stack must be deployed first. Then:

```bash
cd cdk
AWS_PROFILE=<profile> \
  CDK_DEFAULT_ACCOUNT=$(AWS_PROFILE=<profile> aws sts get-caller-identity --query Account --output text) \
  CDK_DEFAULT_REGION=us-west-2 \
  npx cdk deploy tokenburner-drive --require-approval never
```

See [`tokenburner.md`](./tokenburner.md) for the full feature spec.
