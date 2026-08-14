output "datasets_bucket" {
  value       = aws_s3_bucket.datasets.bucket
  description = "S3 bucket for immutable certified data packages"
}

output "postgres_endpoint" {
  value       = aws_db_instance.postgres.address
  description = "RDS Postgres endpoint (inject into QFT_DATABASE_URL)"
}

output "redis_endpoint" {
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
  description = "ElastiCache Redis primary endpoint (inject into QFT_REDIS_URL)"
}

output "ecs_cluster" {
  value = aws_ecs_cluster.main.name
}
