# CI/CD OIDC 설정 가이드

워크플로는 `vars.AWS_ROLE_ARN` 기반 OIDC를 사용합니다. 아래 설정을 GitHub/AWS에 적용한 뒤 static access key secret을 제거하세요.

## GitHub Repository Variables

| 이름 | 예시 | 용도 |
|------|------|------|
| `AWS_ROLE_ARN` | `arn:aws:iam::123456789012:role/github-actions-issueissyu-ai` | OIDC assume role |
| `DEV_HEALTH_URL` | `https://dev-api.example.com/health` | dev EB 배포 후 스모크 |
| `PROD_HEALTH_URL` | `https://api.example.com/health` | prod EB 배포 후 스모크 |

## GitHub Repository Secrets (유지)

| 이름 | 용도 |
|------|------|
| `CI_ENV` | CI용 `.env` |
| `DEV_ENV` | dev EB `.env` |
| `PROD_ENV` | prod EB `.env` |

## 제거 대상 Secrets (OIDC 전환 후)

- `AWS_ACTION_ACCESS_KEY_ID`
- `AWS_ACTION_SECRET_ACCESS_KEY`
- `AWS_PROD_ACCESS_KEY`
- `AWS_PROD_SECRET_KEY`

## IAM Role 신뢰 정책 (Trust Policy)

`{org}`를 GitHub org/사용자명으로 바꿉니다.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::{account_id}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:{org}/issueissyu-AI:*"
        }
      }
    }
  ]
}
```

## IAM Role 권한 (최소 예시)

dev/prod EB 환경 모두에 배포할 수 있도록 `issueissyu-ai-dev`, `issueissyu-ai-prod` 애플리케이션 및 artifact S3 bucket에 대한 권한이 필요합니다.

- `elasticbeanstalk:CreateApplicationVersion`
- `elasticbeanstalk:UpdateEnvironment`
- `elasticbeanstalk:DescribeEnvironments`
- `elasticbeanstalk:DescribeApplicationVersions`
- `s3:*` (EB deployment artifact bucket)
- `cloudformation:Describe*`
- `ec2:Describe*`
- `autoscaling:Describe*`

## EB Python 플랫폼

`runtime.txt`에 `python-3.14`를 명시했습니다. dev/prod EB 환경이 Python 3.14 플랫폼을 지원하는지 확인하고, 미지원 시 플랫폼 업그레이드를 선행하세요.
