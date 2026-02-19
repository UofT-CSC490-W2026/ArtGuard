# AppAutoScaling Scheduled Actions - Auto Pause/Resume ECS Service
# Saves costs by scaling ECS service to 0 tasks during off-hours
# NOTE: Only enabled for dev environment. Production runs 24/7.

# Pause ECS at 10:00 PM EST (03:00 UTC) - Scale to 0
resource "aws_appautoscaling_scheduled_action" "pause_ecs" {
  count = var.environment == "dev" ? 1 : 0

  name               = "${local.project_name}-pause-ecs"
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  schedule           = var.scheduler_pause_cron

  scalable_target_action {
    min_capacity = 0
    max_capacity = 0
  }
}

# Resume ECS at 8:00 AM EST (13:00 UTC) - Restore capacity
resource "aws_appautoscaling_scheduled_action" "resume_ecs" {
  count = var.environment == "dev" ? 1 : 0

  name               = "${local.project_name}-resume-ecs"
  service_namespace  = aws_appautoscaling_target.ecs.service_namespace
  resource_id        = aws_appautoscaling_target.ecs.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs.scalable_dimension
  schedule           = var.scheduler_resume_cron

  scalable_target_action {
    min_capacity = var.ecs_min_capacity
    max_capacity = var.ecs_max_capacity
  }
}
