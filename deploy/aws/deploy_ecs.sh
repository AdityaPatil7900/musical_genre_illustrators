#!/usr/bin/env bash
# Case Study 4 -- deploy the API-based product to AWS ECS (Fargate) behind
# an Application Load Balancer, which is what gives us a stable external
# URL (ECS tasks alone don't have one).
#
# This is the most manual of the three clouds -- the rubric gives no
# official one-command path for ECS the way it does for Cloud Run /
# Container Apps, so this script does the full chain: ECR push, Secrets
# Manager, execution role, task definition, cluster, ALB + target group +
# listener, security groups, and the service itself. It uses your
# account's DEFAULT VPC and its default subnets, which is what a fresh
# AWS Educate account has -- if you've deleted your default VPC this needs
# adjusting.
#
# Run from a shell where `aws` is configured (`aws configure`) against
# your AWS Educate-linked account. HF_TOKEN is read only from your local
# environment -- never committed, never pasted into chat.
#
# Required environment variables:
#   HF_TOKEN   - your Hugging Face token
# Optional:
#   AWS_REGION - defaults to us-east-1
set -euo pipefail

: "${HF_TOKEN:?Set HF_TOKEN in your local shell before running this script}"
AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="${AWS_REGION}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REPO_NAME="genre-api"
CLUSTER_NAME="genre-cs4-cluster"
SERVICE_NAME="genre-api-svc"
TASK_FAMILY="genre-api"
EXEC_ROLE_NAME="genreCS4EcsExecutionRole"

echo "== Account: ${ACCOUNT_ID}, region: ${AWS_REGION} =="

echo "== Ensuring ECR repo exists =="
aws ecr describe-repositories --repository-names "${REPO_NAME}" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name "${REPO_NAME}" >/dev/null

IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}:latest"

echo "== Logging in to ECR and pushing image =="
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
docker build -f Dockerfile.cloud -t "${REPO_NAME}:latest" .
docker tag "${REPO_NAME}:latest" "${IMAGE_URI}"
docker push "${IMAGE_URI}"

echo "== Storing HF_TOKEN in Secrets Manager =="
if aws secretsmanager describe-secret --secret-id genre/hf-token >/dev/null 2>&1; then
  aws secretsmanager put-secret-value --secret-id genre/hf-token --secret-string "${HF_TOKEN}" >/dev/null
else
  aws secretsmanager create-secret --name genre/hf-token --secret-string "${HF_TOKEN}" >/dev/null
fi
HF_SECRET_ARN=$(aws secretsmanager describe-secret --secret-id genre/hf-token --query ARN --output text)

echo "== Ensuring ECS task execution role exists =="
if ! aws iam get-role --role-name "${EXEC_ROLE_NAME}" >/dev/null 2>&1; then
  aws iam create-role --role-name "${EXEC_ROLE_NAME}" \
    --assume-role-policy-document '{
      "Version":"2012-10-17",
      "Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]
    }' >/dev/null
  aws iam attach-role-policy --role-name "${EXEC_ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
  aws iam put-role-policy --role-name "${EXEC_ROLE_NAME}" --policy-name ReadHfTokenSecret \
    --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"secretsmanager:GetSecretValue\",\"Resource\":\"${HF_SECRET_ARN}\"}]}"
  echo "   (waiting ~10s for IAM role propagation)"
  sleep 10
fi
EXEC_ROLE_ARN=$(aws iam get-role --role-name "${EXEC_ROLE_NAME}" --query Role.Arn --output text)

echo "== Registering task definition =="
sed -e "s|__EXECUTION_ROLE_ARN__|${EXEC_ROLE_ARN}|" \
    -e "s|__IMAGE_URI__|${IMAGE_URI}|" \
    -e "s|__HF_TOKEN_SECRET_ARN__|${HF_SECRET_ARN}|" \
    -e "s|__AWS_REGION__|${AWS_REGION}|" \
    deploy/aws/task-def.template.json > /tmp/genre-api-task-def.json
aws ecs register-task-definition --cli-input-json file:///tmp/genre-api-task-def.json >/dev/null

echo "== Ensuring cluster exists =="
aws ecs describe-clusters --clusters "${CLUSTER_NAME}" --query 'clusters[0].status' --output text 2>/dev/null | grep -q ACTIVE || \
  aws ecs create-cluster --cluster-name "${CLUSTER_NAME}" >/dev/null

echo "== Looking up default VPC/subnets =="
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SUBNET_IDS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values="${VPC_ID}" --query 'Subnets[].SubnetId' --output text | tr '\t' ',')
SUBNET_1=$(echo "${SUBNET_IDS}" | cut -d, -f1)
SUBNET_2=$(echo "${SUBNET_IDS}" | cut -d, -f2)

echo "== Creating security groups (ALB: public 80 in; task: 8080 from ALB only) =="
ALB_SG_ID=$(aws ec2 create-security-group --group-name genre-cs4-alb-sg \
  --description "ALB SG for genre-api CS4" --vpc-id "${VPC_ID}" --query GroupId --output text 2>/dev/null || \
  aws ec2 describe-security-groups --filters Name=group-name,Values=genre-cs4-alb-sg Name=vpc-id,Values="${VPC_ID}" --query 'SecurityGroups[0].GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id "${ALB_SG_ID}" --protocol tcp --port 80 --cidr 0.0.0.0/0 >/dev/null 2>&1 || true

TASK_SG_ID=$(aws ec2 create-security-group --group-name genre-cs4-task-sg \
  --description "Task SG for genre-api CS4" --vpc-id "${VPC_ID}" --query GroupId --output text 2>/dev/null || \
  aws ec2 describe-security-groups --filters Name=group-name,Values=genre-cs4-task-sg Name=vpc-id,Values="${VPC_ID}" --query 'SecurityGroups[0].GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id "${TASK_SG_ID}" --protocol tcp --port 8080 --source-group "${ALB_SG_ID}" >/dev/null 2>&1 || true

echo "== Creating ALB + target group + listener =="
ALB_ARN=$(aws elbv2 describe-load-balancers --names genre-cs4-alb --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || true)
if [ -z "${ALB_ARN}" ] || [ "${ALB_ARN}" = "None" ]; then
  ALB_ARN=$(aws elbv2 create-load-balancer --name genre-cs4-alb --subnets "${SUBNET_1}" "${SUBNET_2}" \
    --security-groups "${ALB_SG_ID}" --scheme internet-facing --type application \
    --query 'LoadBalancers[0].LoadBalancerArn' --output text)
fi

TG_ARN=$(aws elbv2 describe-target-groups --names genre-cs4-tg --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || true)
if [ -z "${TG_ARN}" ] || [ "${TG_ARN}" = "None" ]; then
  TG_ARN=$(aws elbv2 create-target-group --name genre-cs4-tg --protocol HTTP --port 8080 \
    --vpc-id "${VPC_ID}" --target-type ip --health-check-path / \
    --query 'TargetGroups[0].TargetGroupArn' --output text)
fi

aws elbv2 describe-listeners --load-balancer-arn "${ALB_ARN}" --query 'Listeners[0].ListenerArn' --output text 2>/dev/null | grep -q arn || \
  aws elbv2 create-listener --load-balancer-arn "${ALB_ARN}" --protocol HTTP --port 80 \
    --default-actions Type=forward,TargetGroupArn="${TG_ARN}" >/dev/null

echo "== Creating/updating ECS service =="
if aws ecs describe-services --cluster "${CLUSTER_NAME}" --services "${SERVICE_NAME}" --query 'services[0].status' --output text 2>/dev/null | grep -q ACTIVE; then
  aws ecs update-service --cluster "${CLUSTER_NAME}" --service "${SERVICE_NAME}" \
    --task-definition "${TASK_FAMILY}" --force-new-deployment >/dev/null
else
  aws ecs create-service --cluster "${CLUSTER_NAME}" --service-name "${SERVICE_NAME}" \
    --task-definition "${TASK_FAMILY}" --desired-count 1 --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_1},${SUBNET_2}],securityGroups=[${TASK_SG_ID}],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=${TG_ARN},containerName=genre-api,containerPort=8080" >/dev/null
fi

echo "== Done. External URL (wait ~1-2 min for the task to pass health checks): =="
ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns "${ALB_ARN}" --query 'LoadBalancers[0].DNSName' --output text)
echo "http://${ALB_DNS}"
