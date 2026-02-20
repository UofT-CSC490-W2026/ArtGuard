# S3 Bucket for Frontend Static Files (React/Next.js)
# Stores the compiled frontend application served via CloudFront
resource "aws_s3_bucket" "frontend" {
  bucket        = "${local.project_name}-frontend-${var.environment}"
  force_destroy = false

  tags = {
    Name    = "${local.project_name}-frontend"
    Purpose = "Frontend Static Website Hosting"
  }
}

# Block all public access to frontend bucket (CloudFront will access via OAC)
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable versioning for frontend bucket for rollbacks
resource "aws_s3_bucket_versioning" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption for frontend bucket
resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# S3 Bucket Policy for Frontend - Allow CloudFront OAC access
resource "aws_s3_bucket_policy" "frontend_cloudfront" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
          }
        }
      }
    ]
  })
}


# S3 Bucket for Raw/Uploaded Images
resource "aws_s3_bucket" "images_raw" {
  bucket        = "${local.project_name}-images-raw-${var.environment}"
  force_destroy = false

  tags = {
    Name    = "${local.project_name}-images-raw"
    Purpose = "Raw Image Storage - User Uploads"
  }
}

# Block public access to raw images
resource "aws_s3_bucket_public_access_block" "images_raw" {
  bucket = aws_s3_bucket.images_raw.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable versioning for raw images
resource "aws_s3_bucket_versioning" "images_raw" {
  bucket = aws_s3_bucket.images_raw.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption for raw images
resource "aws_s3_bucket_server_side_encryption_configuration" "images_raw" {
  bucket = aws_s3_bucket.images_raw.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Lifecycle policy for raw images (when to move to cheaper storage)
resource "aws_s3_bucket_lifecycle_configuration" "images_raw" {
  bucket = aws_s3_bucket.images_raw.id

  # Training data lifecycle
  rule {
    id     = "archive-training-images"
    status = "Enabled"

    filter {
      prefix = "training/"
    }

    transition {
      days          = var.s3_training_ia_transition_days
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = var.s3_lifecycle_glacier_days
      storage_class = "GLACIER_IR"
    }

    expiration {
      days = var.s3_lifecycle_expiration_days
    }
  }

  # Real-time inference images: Auto-delete (GDPR/privacy compliance)
  rule {
    id     = "delete-inference-images"
    status = "Enabled"

    filter {
      prefix = "inference/"
    }

    expiration {
      days = var.s3_inference_expiration_days
    }
  }
}

# Resource-Based Policy for Raw Images Bucket
resource "aws_s3_bucket_policy" "images_raw" {
  bucket = aws_s3_bucket.images_raw.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowECSTaskAccess"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.ecs_task.arn
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.images_raw.arn}/*"
      },
      {
        Sid    = "AllowECSTaskListBucket"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.ecs_task.arn
        }
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.images_raw.arn
      },
      {
        Sid       = "DenyUnencryptedObjectUploads"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.images_raw.arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption" = "AES256"
          }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.images_raw.arn,
          "${aws_s3_bucket.images_raw.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })

  depends_on = [
    aws_s3_bucket_public_access_block.images_raw
  ]
}


# S3 Bucket for Processed Images

resource "aws_s3_bucket" "images_processed" {
  bucket        = "${local.project_name}-images-processed-${var.environment}"
  force_destroy = true

  tags = {
    Name    = "${local.project_name}-images-processed"
    Purpose = "Processed Image Storage"
  }
}

# Block public access to processed images
resource "aws_s3_bucket_public_access_block" "images_processed" {
  bucket = aws_s3_bucket.images_processed.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Enable versioning for processed images
resource "aws_s3_bucket_versioning" "images_processed" {
  bucket = aws_s3_bucket.images_processed.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Server-side encryption for processed images
resource "aws_s3_bucket_server_side_encryption_configuration" "images_processed" {
  bucket = aws_s3_bucket.images_processed.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# CORS configuration for images (if frontend needs direct access)
resource "aws_s3_bucket_cors_configuration" "images_processed" {
  bucket = aws_s3_bucket.images_processed.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = concat(
      [
        "https://${aws_cloudfront_distribution.frontend.domain_name}",
        "http://localhost:3000"
      ],
      var.enable_custom_domain ? [
        "https://${var.domain_name}",
        "https://www.${var.domain_name}"
      ] : []
    )
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

# Lifecycle policy for processed images
resource "aws_s3_bucket_lifecycle_configuration" "images_processed" {
  bucket = aws_s3_bucket.images_processed.id

  rule {
    id     = "archive-old-processed-images"
    status = "Enabled"

    filter {}

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = var.s3_lifecycle_glacier_days
      storage_class = "GLACIER_IR"
    }
  }
}

# Resource-Based Policy for Processed Images Bucket
# Restricts access to ECS tasks only
resource "aws_s3_bucket_policy" "images_processed" {
  bucket = aws_s3_bucket.images_processed.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowECSTaskAccess"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.ecs_task.arn
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "${aws_s3_bucket.images_processed.arn}/*"
      },
      {
        Sid    = "AllowECSTaskListBucket"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.ecs_task.arn
        }
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.images_processed.arn
      },
      {
        Sid       = "DenyUnencryptedObjectUploads"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.images_processed.arn}/*"
        Condition = {
          StringNotEquals = {
            "s3:x-amz-server-side-encryption" = "AES256"
          }
        }
      },
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.images_processed.arn,
          "${aws_s3_bucket.images_processed.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })

  depends_on = [
    aws_s3_bucket_public_access_block.images_processed
  ]
}


# S3 Bucket for Knowledge Base Documents for RAG
resource "aws_s3_bucket" "knowledge_base" {
  bucket        = "${local.project_name}-knowledge-base-${var.environment}"
  force_destroy = false

  tags = {
    Name    = "${local.project_name}-knowledge-base"
    Purpose = "Bedrock Knowledge Base Documents - RAG"
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "knowledge_base" {
  bucket = aws_s3_bucket.knowledge_base.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning for documents
resource "aws_s3_bucket_versioning" "knowledge_base" {
  bucket = aws_s3_bucket.knowledge_base.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "knowledge_base" {
  bucket = aws_s3_bucket.knowledge_base.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}


# S3 CloudWatch Metrics Configuration

# Frontend bucket metrics
resource "aws_s3_bucket_metric" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  name   = "EntireBucket"
}

# Images raw bucket metrics
resource "aws_s3_bucket_metric" "images_raw" {
  bucket = aws_s3_bucket.images_raw.id
  name   = "EntireBucket"
}

# Images processed bucket metrics
resource "aws_s3_bucket_metric" "images_processed" {
  bucket = aws_s3_bucket.images_processed.id
  name   = "EntireBucket"
}

# Knowledge Base bucket metrics
resource "aws_s3_bucket_metric" "knowledge_base" {
  bucket = aws_s3_bucket.knowledge_base.id
  name   = "EntireBucket"
}
