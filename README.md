# EC2 Instance Resizer Automation

This project automates EC2 instance resizing based on CPU usage with safety checks, approval workflows, rollback capabilities, and optional notifications.

## Features
- CloudWatch CPU analysis
- AI-based upgrade/downgrade recommendation
- Safety checks:
  - Dry-run validation
  - Architecture compatibility check
  - Instance type validation
  - Manual approval via GitHub Environments
- Rollback workflow for safe restoration
- Optional SNS/Slack notifications

## Usage
- Edit `input.json` with your instance ID, region, and target type.
- Trigger `EC2 Safe Resizer` workflow manually from GitHub Actions.
- For rollback, trigger `EC2 Rollback` workflow.

## Requirements
- AWS credentials stored as GitHub Secrets.
   - AWS_ACCESS_KEY_ID
   - AWS_DEFAULT_REGION
   - AWS_SECRET_ACCESS_KEY
   - S3_BUCKET_NAME
- AWS EC2 and CloudWatch permissions.
- GitHub token variable
   - PERSONAL_ACCESS_TOKEN
- AI API Key Variable
   - GROQ_API_KEY


## AI options
openai
groq -- We are using this for this project.

