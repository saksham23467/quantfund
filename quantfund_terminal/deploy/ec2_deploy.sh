#!/usr/bin/env bash
# One-command deploy of QuantFund Research Terminal onto a single EC2 host via
# docker-compose. Run this FROM the EC2 instance, inside the quantfund_terminal/
# directory of the transferred repo.
#
#   cd ~/Quant-fund/quantfund_terminal && ./deploy/ec2_deploy.sh
#
# It auto-detects the instance public IP (IMDSv2) so the frontend is built with
# the correct API base and CORS is opened to that origin. Override by exporting
# PUBLIC_IP=1.2.3.4 before running (e.g. when using an Elastic IP or domain).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # quantfund_terminal/
cd "$HERE"

# --- Resolve public IP ------------------------------------------------------
if [[ -z "${PUBLIC_IP:-}" ]]; then
  echo "Detecting EC2 public IP via instance metadata (IMDSv2)..."
  TOKEN="$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 300" || true)"
  if [[ -n "$TOKEN" ]]; then
    PUBLIC_IP="$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
      http://169.254.169.254/latest/meta-data/public-ipv4 || true)"
  fi
fi
if [[ -z "${PUBLIC_IP:-}" ]]; then
  echo "!! Could not auto-detect a public IP."
  echo "   Re-run as:  PUBLIC_IP=<your.ec2.public.ip> ./deploy/ec2_deploy.sh"
  exit 1
fi

export API_BASE="http://${PUBLIC_IP}:8000"
export CORS_ORIGINS="http://${PUBLIC_IP}:3000"
echo "Public IP     : ${PUBLIC_IP}"
echo "Frontend      : http://${PUBLIC_IP}:3000"
echo "Backend API   : ${API_BASE}   (docs at ${API_BASE}/docs)"
echo "CORS origin   : ${CORS_ORIGINS}"

# --- docker compose plugin vs legacy binary --------------------------------
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "!! docker compose not found. Install Docker + the compose plugin first"
  echo "   (see deploy/EC2_DEPLOY.md)."
  exit 1
fi

echo "Building + starting containers (detached)..."
$DC up --build -d

echo
echo "Deployed. Containers:"
$DC ps
echo
echo "Open:  http://${PUBLIC_IP}:3000"
echo "Make sure the instance security group allows inbound TCP 3000 and 8000."
