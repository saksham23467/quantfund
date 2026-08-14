variable "project" {
  type    = string
  default = "quantfund-terminal"
}

variable "env" {
  type        = string
  description = "Environment name (dev|staging|prod)"
  default     = "dev"
}

variable "region" {
  type    = string
  default = "ap-south-1" # Mumbai — India data residency
}

variable "vpc_id" {
  type        = string
  description = "Existing VPC id to deploy into"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "db_username" {
  type    = string
  default = "quantfund"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_security_group_id" {
  type = string
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "redis_security_group_id" {
  type = string
}
