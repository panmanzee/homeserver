variable "use_localstack" {
  description = "point the provider at LocalStack instead of real AWS"
  type        = bool
  default     = false
}

variable "localstack_endpoint" {
  type    = string
  default = "http://localhost:4566"
}

variable "region" {
  type    = string
  default = "ap-southeast-1"
}

variable "bucket_name" {
  description = "must be globally unique on real AWS"
  type        = string
  default     = "pan-homelab-restic-backup"
}

variable "noncurrent_expire_days" {
  type    = number
  default = 60
}
