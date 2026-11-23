output "bucket" {
  value = aws_s3_bucket.backup.id
}

output "restic_repository" {
  value = "s3:${var.use_localstack ? var.localstack_endpoint : "s3.${var.region}.amazonaws.com"}/${aws_s3_bucket.backup.id}"
}

output "access_key_id" {
  value = aws_iam_access_key.restic.id
}

output "secret_access_key" {
  value     = aws_iam_access_key.restic.secret
  sensitive = true
}
