"""
Lambda function to pause/resume ECS Fargate service for cost savings.

This function scales the ECS service to 0 tasks (pause) during off-hours
and restores it to the minimum capacity (resume) during business hours.
"""

import os
import boto3
import json
from datetime import datetime

# Initialize AWS clients
ecs_client = boto3.client('ecs')
autoscaling_client = boto3.client('application-autoscaling')

# Environment variables
CLUSTER_NAME = os.environ['CLUSTER_NAME']
SERVICE_NAME = os.environ['SERVICE_NAME']
MIN_CAPACITY = int(os.environ['MIN_CAPACITY'])
MAX_CAPACITY = int(os.environ['MAX_CAPACITY'])
PROJECT_NAME = os.environ['PROJECT_NAME']
ENVIRONMENT = os.environ['ENVIRONMENT']


def handler(event, context):
    """
    Main Lambda handler function.

    Args:
        event: Event data from EventBridge with 'action' field ('pause' or 'resume')
        context: Lambda context object

    Returns:
        dict: Response with status code and message
    """
    print(f"Event received: {json.dumps(event)}")

    action = event.get('action', 'unknown')
    timestamp = datetime.utcnow().isoformat()

    print(f"Action: {action}")
    print(f"Cluster: {CLUSTER_NAME}")
    print(f"Service: {SERVICE_NAME}")
    print(f"Min Capacity: {MIN_CAPACITY}")

    try:
        if action == 'pause':
            result = pause_ecs_service()
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'ECS service paused successfully',
                    'action': 'pause',
                    'desired_count': 0,
                    'timestamp': timestamp,
                    **result
                })
            }

        elif action == 'resume':
            result = resume_ecs_service()
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'ECS service resumed successfully',
                    'action': 'resume',
                    'desired_count': MIN_CAPACITY,
                    'timestamp': timestamp,
                    **result
                })
            }

        else:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': f'Invalid action: {action}. Must be "pause" or "resume".',
                    'timestamp': timestamp
                })
            }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'action': action,
                'timestamp': timestamp
            })
        }


def pause_ecs_service():
    """
    Scale ECS service to 0 tasks to save costs.

    Returns:
        dict: Result details
    """
    print(f"Pausing ECS service: {SERVICE_NAME}")

    # Update ECS service desired count to 0
    response = ecs_client.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        desiredCount=0
    )

    service_arn = response['service']['serviceArn']
    current_desired = response['service']['desiredCount']
    current_running = response['service']['runningCount']

    print(f"Service updated:")
    print(f"  ARN: {service_arn}")
    print(f"  Desired count: {current_desired}")
    print(f"  Running count: {current_running}")

    # Deregister scalable target to prevent auto-scaling
    try:
        resource_id = f"service/{CLUSTER_NAME}/{SERVICE_NAME}"
        autoscaling_client.deregister_scalable_target(
            ServiceNamespace='ecs',
            ResourceId=resource_id,
            ScalableDimension='ecs:service:DesiredCount'
        )
        print(f"Deregistered scalable target: {resource_id}")
        autoscaling_deregistered = True
    except autoscaling_client.exceptions.ObjectNotFoundException:
        print("Scalable target not found (already deregistered or never registered)")
        autoscaling_deregistered = False

    return {
        'service_arn': service_arn,
        'previous_desired_count': current_desired,
        'current_running_count': current_running,
        'autoscaling_deregistered': autoscaling_deregistered
    }


def resume_ecs_service():
    """
    Restore ECS service to minimum capacity.

    Returns:
        dict: Result details
    """
    print(f"Resuming ECS service: {SERVICE_NAME}")

    # Update ECS service desired count to MIN_CAPACITY
    response = ecs_client.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        desiredCount=MIN_CAPACITY
    )

    service_arn = response['service']['serviceArn']
    current_desired = response['service']['desiredCount']
    current_running = response['service']['runningCount']

    print(f"Service updated:")
    print(f"  ARN: {service_arn}")
    print(f"  Desired count: {current_desired}")
    print(f"  Running count: {current_running}")

    # Re-register scalable target for auto-scaling
    try:
        resource_id = f"service/{CLUSTER_NAME}/{SERVICE_NAME}"
        autoscaling_client.register_scalable_target(
            ServiceNamespace='ecs',
            ResourceId=resource_id,
            ScalableDimension='ecs:service:DesiredCount',
            MinCapacity=MIN_CAPACITY,
            MaxCapacity=MAX_CAPACITY
        )
        print(f"Registered scalable target: {resource_id}")
        autoscaling_registered = True
    except Exception as e:
        print(f"Warning: Could not register scalable target: {str(e)}")
        autoscaling_registered = False

    return {
        'service_arn': service_arn,
        'desired_count': current_desired,
        'current_running_count': current_running,
        'autoscaling_registered': autoscaling_registered
    }
