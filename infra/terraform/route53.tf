# Route 53

# Hosted zone for your domain
# This is created by Terraform and manages all DNS records for the custom domain
resource "aws_route53_zone" "main" {
  count   = var.enable_custom_domain ? 1 : 0
  name    = var.domain_name
  comment = "Hosted zone for ${local.project_name} ${var.environment}"

  tags = {
    Name        = "${local.project_name}-hosted-zone"
    Environment = var.environment
  }
}

# SSL/TLS Certificate for CloudFront / Frontend
resource "aws_acm_certificate" "cloudfront" {
  count             = var.enable_custom_domain ? 1 : 0
  provider          = aws.us_east_1
  domain_name       = var.domain_name
  validation_method = "DNS"

  subject_alternative_names = [
    "www.${var.domain_name}",
    "*.${var.domain_name}"
  ]

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name        = "${local.project_name}-cloudfront-certificate"
    Environment = var.environment
  }
}

# DNS validation records for ACM certificate
resource "aws_route53_record" "cert_validation" {
  for_each = var.enable_custom_domain ? {
    for dvo in aws_acm_certificate.cloudfront[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = aws_route53_zone.main[0].zone_id
}

# Wait for certificate validation to complete
resource "aws_acm_certificate_validation" "cloudfront" {
  count                   = var.enable_custom_domain ? 1 : 0
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.cloudfront[0].arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]

  timeouts {
    create = "10m"
  }
}

# NOTE: Backend ACM Certificate and validation are defined in app.tf
# - aws_acm_certificate.backend (for api.${domain_name})
# - aws_acm_certificate_validation.backend
# - aws_route53_record.backend_cert_validation

# DNS Records for CloudFront (Frontend)

# A record for root domain (artguard.com) → CloudFront
resource "aws_route53_record" "frontend_root" {
  count   = var.enable_custom_domain ? 1 : 0
  zone_id = aws_route53_zone.main[0].zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }

  depends_on = [aws_cloudfront_distribution.frontend]
}

# A record for www subdomain (www.artguard.com) → CloudFront
resource "aws_route53_record" "frontend_www" {
  count   = var.enable_custom_domain ? 1 : 0
  zone_id = aws_route53_zone.main[0].zone_id
  name    = "www.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = aws_cloudfront_distribution.frontend.hosted_zone_id
    evaluate_target_health = false
  }

  depends_on = [aws_cloudfront_distribution.frontend]
}

# DNS Records for ALB (Backend API)

# A record for API subdomain (api.artguard.com) → ALB
resource "aws_route53_record" "backend_api" {
  count   = var.enable_custom_domain ? 1 : 0
  zone_id = aws_route53_zone.main[0].zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.backend.dns_name
    zone_id                = aws_lb.backend.zone_id
    evaluate_target_health = true
  }

  depends_on = [
    aws_lb.backend,
    aws_acm_certificate_validation.backend
  ]
}
