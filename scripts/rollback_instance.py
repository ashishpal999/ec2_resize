import boto3
import json
import time

def rollback_instance():
    with open('rollback.json') as f:
        data = json.load(f)

    instance_id = data['instance_id']
    region = data['region']
    original_instance_type = data['original_instance_type']

    ec2 = boto3.client('ec2', region_name=region)

    print(f"Stopping instance {instance_id}...")
    ec2.stop_instances(InstanceIds=[instance_id])

    # Wait for instance to stop
    waiter = ec2.get_waiter('instance_stopped')
    waiter.wait(InstanceIds=[instance_id])
    print("Instance stopped.")

    # Change instance type
    print(f"Modifying instance {instance_id} to type {original_instance_type}...")
    ec2.modify_instance_attribute(InstanceId=instance_id, Attribute='instanceType', Value=original_instance_type)
    print("Instance type changed.")

    # Start instance again
    print(f"Starting instance {instance_id}...")
    ec2.start_instances(InstanceIds=[instance_id])

    # Wait for instance to be running
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])
    print("Instance started. Rollback complete.")

if __name__ == "__main__":
    rollback_instance()
