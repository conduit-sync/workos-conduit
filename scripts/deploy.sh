#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Deploy workos-conduit to AWS ECS Fargate.
# Usage: ./scripts/deploy.sh <aws-region> <ecr-uri> <ecs-cluster> <ecs-service>
set -euo pipefail

AWS_REGION="${1:?Usage: $0 <aws-region> <ecr-uri> <ecs-cluster> <ecs-service>}"
ECR_URI="${2:?}"
ECS_CLUSTER="${3:?}"
ECS_SERVICE="${4:?}"

GIT_SHA=$(git rev-parse --short HEAD)
IMAGE_TAG_SHA="${ECR_URI}:${GIT_SHA}"
IMAGE_TAG_LATEST="${ECR_URI}:latest"

echo "==> Building Docker image"
docker build -t "${IMAGE_TAG_SHA}" -t "${IMAGE_TAG_LATEST}" .

echo "==> Logging in to ECR"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_URI}"

echo "==> Pushing images"
docker push "${IMAGE_TAG_SHA}"
docker push "${IMAGE_TAG_LATEST}"

echo "==> Registering task definition"
TASK_DEF=$(aws ecs register-task-definition \
  --cli-input-json "file://infra/aws/task-definition.json" \
  --region "${AWS_REGION}" \
  --query "taskDefinition.taskDefinitionArn" \
  --output text)
echo "    Task definition: ${TASK_DEF}"

echo "==> Updating ECS service"
aws ecs update-service \
  --cluster "${ECS_CLUSTER}" \
  --service "${ECS_SERVICE}" \
  --task-definition "${TASK_DEF}" \
  --force-new-deployment \
  --region "${AWS_REGION}" \
  --output text --query "service.serviceName"

echo ""
echo "==> Deployment initiated. Monitor with:"
echo "    aws ecs describe-services --cluster ${ECS_CLUSTER} --services ${ECS_SERVICE} --region ${AWS_REGION}"
