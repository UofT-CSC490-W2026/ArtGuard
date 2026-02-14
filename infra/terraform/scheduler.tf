# EventBridge Scheduler - Auto Scale ECS Service
# Saves costs by scaling ECS service to 0 tasks during off-hours
# NOTE: Only enabled for dev environment. Production runs 24/7.

# EventBridge Rule: Scale ECS to 0 at 10:00 PM (22:00) EST
resource "aws_cloudwatch_event_rule" "pause_ecs" {
  count = var.environment == "dev" ? 1 : 0

  name                = "${local.project_name}-pause-ecs"
  description         = "Scale ECS service to 0 to save costs"
  schedule_expression = var.scheduler_pause_cron

  tags = {
    Name        = "${local.project_name}-pause-ecs-rule"
    Environment = var.environment
  }
}

# EventBridge Rule: Resume ECS at 8:00 AM EST
resource "aws_cloudwatch_event_rule" "resume_ecs" {
  count = var.environment == "dev" ? 1 : 0

  name                = "${local.project_name}-resume-ecs"
  description         = "Resume ECS service"
  schedule_expression = var.scheduler_resume_cron

  tags = {
    Name        = "${local.project_name}-resume-ecs-rule"
    Environment = var.environment
  }
}

# EventBridge Target: Trigger Lambda to pause (scale to 0)
resource "aws_cloudwatch_event_target" "pause_ecs" {
  count = var.environment == "dev" ? 1 : 0

  rule      = aws_cloudwatch_event_rule.pause_ecs[0].name
  target_id = "PauseECS"
  arn       = aws_lambda_function.ecs_scheduler.arn

  input = jsonencode({
    action = "pause"
  })
}

# EventBridge Target: Trigger Lambda to resume
resource "aws_cloudwatch_event_target" "resume_ecs" {
  count = var.environment == "dev" ? 1 : 0

  rule      = aws_cloudwatch_event_rule.resume_ecs[0].name
  target_id = "ResumeECS"
  arn       = aws_lambda_function.ecs_scheduler.arn

  input = jsonencode({
    action = "resume"
  })
}
