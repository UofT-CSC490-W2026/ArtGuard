# CloudFront Function for Directory Index Rewriting (SPA routing)
resource "aws_cloudfront_function" "dir_index_rewrite" {
  name    = "${local.project_name}-dir-index-rewrite"
  runtime = "cloudfront-js-1.0"
  comment = "Rewrite directory requests to index.html for React SPA"
  publish = true
  code    = <<EOF
function handler(event) {
    var request = event.request;
    var uri = request.uri;

    // Case 1: URI ends with / (e.g., /dashboard/) -> append index.html
    if (uri.endsWith('/')) {
        request.uri += 'index.html';
    }
    // Case 2: URI is missing extension (e.g., /dashboard) -> append /index.html
    else if (!uri.includes('.')) {
        request.uri += '/index.html';
    }

    return request;
}
EOF
}

# Origin Access Control for S3
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${local.project_name}-frontend-oac"
  description                       = "Origin Access Control for S3 Frontend"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# CloudFront Distribution - Serves Frontend from S3 and API from App Runner
resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "CloudFront distribution for ${local.project_name}"
  default_root_object = "index.html"
  price_class         = "PriceClass_100" # North America and Europe only (cheaper)

  # S3 bucket for React frontend static files
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "S3-Frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # ALB for FastAPI backend
  origin {
    domain_name = aws_lb.backend.dns_name
    origin_id   = "ALB-Backend"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only" # ALB terminates HTTPS
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Default behavior: Serve React app from S3
  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-Frontend"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0 # Set to 0 for development, increase for production
    max_ttl                = 0
    compress               = true

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.dir_index_rewrite.arn
    }
  }

  # Cache behavior for API requests - route to ALB
  ordered_cache_behavior {
    path_pattern     = "/api/*"
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "ALB-Backend"

    forwarded_values {
      query_string = true
      headers      = ["Authorization", "Accept", "Content-Type", "Origin"]
      cookies {
        forward = "all"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
    compress               = true
  }

  # Cache behavior for static assets 
  # Adjust path patterns based on your build output
  ordered_cache_behavior {
    path_pattern     = "/static/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-Frontend"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 31536000 # 1 year
    default_ttl            = 31536000
    max_ttl                = 31536000
    compress               = true
  }

  # Cache behavior for assets (images, fonts, etc.)
  ordered_cache_behavior {
    path_pattern     = "/assets/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-Frontend"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 31536000 # 1 year
    default_ttl            = 31536000
    max_ttl                = 31536000
    compress               = true
  }

  # Custom error responses for SPA routing
  # When CloudFront gets 404 from S3, serve index.html for client-side routing
  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  # Geographic restrictions
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # SSL/TLS Certificate
  viewer_certificate {
    # Use custom domain certificate if enabled, otherwise use CloudFront default
    cloudfront_default_certificate = var.enable_custom_domain ? false : true
    acm_certificate_arn            = var.enable_custom_domain ? aws_acm_certificate.cloudfront[0].arn : null
    ssl_support_method             = var.enable_custom_domain ? "sni-only" : null
    minimum_protocol_version       = var.enable_custom_domain ? "TLSv1.2_2021" : "TLSv1"
  }

  # Custom domain aliases
  aliases = var.enable_custom_domain ? [
    var.domain_name,
    "www.${var.domain_name}"
  ] : []

  tags = {
    Name    = "${local.project_name}-frontend-cdn"
    Purpose = "Frontend CDN and API Gateway"
  }
}
