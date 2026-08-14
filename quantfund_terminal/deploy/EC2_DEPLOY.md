# Deploy to EC2 (single box, docker-compose)

Get QuantFund Research Terminal live on one EC2 instance in ~20–30 minutes. This
runs frontend + backend + Postgres + Redis as containers on the instance. Good
for an investor demo; scale to ECS/Fargate later (see `docs/11_DEPLOYMENT_AWS.md`).

## 0. Instance requirements

- **Type:** `t3.medium` (2 vCPU / 4 GB) recommended. `t3.small` (2 GB) works only
  if you add swap (the frontend/pyarrow builds are memory-hungry) — see Troubleshooting.
- **OS:** Amazon Linux 2023 or Ubuntu 22.04+.
- **Disk:** ≥ 20 GB.
- **Region:** ap-south-1 (Mumbai).

## 1. Security group (open the demo ports)

Add inbound rules on the instance's security group:

| Type | Port | Source | Why |
|---|---|---|---|
| Custom TCP | 3000 | your IP (or 0.0.0.0/0 for open demo) | frontend UI |
| Custom TCP | 8000 | your IP (or 0.0.0.0/0 for open demo) | backend API (browser calls it directly) |
| SSH | 22 | your IP | admin |

> Both 3000 and 8000 must be reachable from your **browser** — the UI calls the
> API directly from the client. Prefer restricting Source to your IP.

## 2. Install Docker + compose plugin (on the EC2)

Amazon Linux 2023:
```bash
sudo dnf update -y
sudo dnf install -y docker git
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"      # then log out/in (or: newgrp docker)
# compose plugin:
sudo dnf install -y docker-compose-plugin || {
  mkdir -p ~/.docker/cli-plugins
  curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
    -o ~/.docker/cli-plugins/docker-compose && chmod +x ~/.docker/cli-plugins/docker-compose; }
docker compose version
```
Ubuntu:
```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo systemctl enable --now docker && sudo usermod -aG docker "$USER"   # re-login
```

## 3. Get the code onto the instance

**Option A — rsync from your Mac** (no GitHub needed). Run this on your Mac; it
skips heavy dirs so the transfer is small:
```bash
rsync -avz --progress \
  --exclude '.git' --exclude '.venv' --exclude 'data' --exclude 'datasets' \
  --exclude 'runs' --exclude 'experiments' --exclude 'node_modules' \
  --exclude '.next' --exclude '*.db' --exclude '*.csv' --exclude '*.parquet' \
  -e "ssh -i /path/to/key.pem" \
  "/Users/sakshambansal/Desktop/Desktop 21-07-2026/Quant-fund/" \
  ec2-user@<EC2_PUBLIC_IP>:~/Quant-fund/
```
(Use `ubuntu@` instead of `ec2-user@` on Ubuntu.)

**Option B — git** (if you push the repo to GitHub):
```bash
ssh -i key.pem ec2-user@<EC2_PUBLIC_IP>
git clone <your-repo-url> ~/Quant-fund
```

> The backend image needs `pyproject.toml`, `src/`, `quantfund_terminal/`, and
> `reports/`. The rsync excludes above keep all of those.

## 4. Deploy (on the EC2)

```bash
cd ~/Quant-fund/quantfund_terminal
./deploy/ec2_deploy.sh
```
The script auto-detects the instance public IP (IMDSv2), builds the frontend with
`NEXT_PUBLIC_API_BASE=http://<ip>:8000`, opens CORS to `http://<ip>:3000`, seeds
the demo data, and starts everything detached.

If auto-detection fails (or you use an Elastic IP / domain):
```bash
PUBLIC_IP=<your.ec2.ip> ./deploy/ec2_deploy.sh
```

First build takes a few minutes (installs pandas/numpy/pyarrow + builds Next).

## 5. Open it

```
http://<EC2_PUBLIC_IP>:3000      # terminal UI
http://<EC2_PUBLIC_IP>:8000/docs # API docs
http://<EC2_PUBLIC_IP>:8000/health
```

## Operate

```bash
cd ~/Quant-fund/quantfund_terminal
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose down                 # stop
./deploy/ec2_deploy.sh              # redeploy after code changes (rsync again first)
docker compose exec backend python quantfund_terminal/backend/seed.py --reset  # reset demo data
```

## Troubleshooting

- **UI loads but panels say "Gateway offline":** port 8000 not open in the SG, or
  the browser can't reach `http://<ip>:8000`. Confirm the SG rule and that
  `API_BASE` used the public IP (re-run with `PUBLIC_IP=...`).
- **CORS error in browser console:** the frontend origin isn't in `QFT_CORS_ORIGINS`.
  The deploy script sets it to `http://<ip>:3000`; if you use a domain, set
  `CORS_ORIGINS=https://your.domain` before running, or `CORS_ORIGINS='*'` for an open demo.
- **Build killed / OOM on t3.small:** add swap, then redeploy:
  ```bash
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile \
    && sudo mkswap /swapfile && sudo swapon /swapfile
  ```
- **`permission denied` talking to Docker:** you didn't re-login after `usermod -aG docker`.
  Run `newgrp docker` or reconnect.

## Hardening (optional, before showing investors on a public URL)

- Put an Nginx/Caddy reverse proxy + TLS (Let's Encrypt) in front; serve UI on 443
  and proxy `/api` to 8000 so you don't expose raw ports.
- Restrict SG sources to your IP / VPN.
- The stack has **no broker credentials** and is read-only w.r.t. trading by design.
