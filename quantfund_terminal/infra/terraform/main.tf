##############################################################################
# QuantFund Research Terminal — AWS infrastructure (SKELETON / starting point)
#
# This is an opinionated scaffold, not a turnkey apply. It provisions the core
# managed services: ECS/Fargate (backend + frontend), RDS Postgres, ElastiCache
# Redis, S3 (immutable certified data packages), and CloudFront (frontend CDN).
# Fill in networking (VPC/subnets/SGs), IAM, ACM certs, and secrets before use.
##############################################################################

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  # backend "s3" { ... }  # configure remote state per environment
}

provider "aws" {
  region = var.region
}

# --- Networking (reference an existing VPC or create one) -------------------
data "aws_vpc" "main" {
  id = var.vpc_id
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }
  tags = { Tier = "private" }
}

# --- S3: immutable certified data packages ----------------------------------
resource "aws_s3_bucket" "datasets" {
  bucket = "${var.project}-datasets-${var.env}"
}

resource "aws_s3_bucket_versioning" "datasets" {
  bucket = aws_s3_bucket.datasets.id
  versioning_configuration { status = "Enabled" }  # content-addressed + versioned
}

resource "aws_s3_bucket_public_access_block" "datasets" {
  bucket                  = aws_s3_bucket.datasets.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Object Lock (WORM) enforces immutability of certified packages.
# NOTE: object lock must be enabled at bucket creation in production.

# --- RDS Postgres (research metadata / results / audit) ----------------------
resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-${var.env}"
  subnet_ids = data.aws_subnets.private.ids
}

resource "aws_db_instance" "postgres" {
  identifier              = "${var.project}-${var.env}"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = var.db_instance_class
  allocated_storage       = 50
  storage_encrypted       = true
  db_name                 = "quantfund"
  username                = var.db_username
  password                = var.db_password          # use Secrets Manager in prod
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [var.db_security_group_id]
  backup_retention_period = 7
  multi_az                = var.env == "prod"
  skip_final_snapshot     = var.env != "prod"
  deletion_protection     = var.env == "prod"
}

# --- ElastiCache Redis (cache / queue / rate-limit) --------------------------
resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project}-${var.env}"
  subnet_ids = data.aws_subnets.private.ids
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.project}-${var.env}"
  description                = "QuantFund Terminal cache/queue"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.redis_node_type
  num_cache_clusters         = var.env == "prod" ? 2 : 1
  automatic_failover_enabled = var.env == "prod"
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [var.redis_security_group_id]
}

# --- ECS / Fargate cluster ---------------------------------------------------
resource "aws_ecs_cluster" "main" {
  name = "${var.project}-${var.env}"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# Task/service definitions for `backend` and `frontend` live in ecs.tf (scaffold
# below). They pull images from ECR, inject QFT_DATABASE_URL / QFT_REDIS_URL from
# Secrets Manager, and sit behind an ALB. See docs/11_DEPLOYMENT_AWS.md.

# --- CloudFront (frontend CDN) ----------------------------------------------
# resource "aws_cloudfront_distribution" "frontend" { ... origin = ALB/S3 ... }
