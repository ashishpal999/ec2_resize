import boto3
import json
import sys

def resize_instance(instance_id, region, new_type):
    ec2 = boto3.client('ec2', region_name=region)

    instance_info = ec2.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances'][0]
    current_type = instance_info['InstanceType']
    architecture = instance_info['Architecture']

    print(f"Current Type: {current_type} | Target Type: {new_type} | Architecture: {architecture}")

    try:
        ec2.modify_instance_attribute(
            InstanceId=instance_id,
            InstanceType={'Value': new_type},
            DryRun=True
        )
        print("Dry-run passed. Proceeding...")
    except ec2.exceptions.ClientError as e:
        if 'DryRunOperation' not in str(e):
            print(f"Dry-run failed: {e}")
            sys.exit(1)

    if instance_info['State']['Name'] != 'stopped':
        ec2.stop_instances(InstanceIds=[instance_id])
        ec2.get_waiter('instance_stopped').wait(InstanceIds=[instance_id])

    with open('rollback.json', 'w') as f:
        json.dump({'previous_instance_type': current_type}, f)

    ec2.modify_instance_attribute(
        InstanceId=instance_id,
        InstanceType={'Value': new_type}
    )
    print(f"Instance type changed from {current_type} to {new_type}.")

    ec2.start_instances(InstanceIds=[instance_id])
    print("Instance started successfully.")

if __name__ == "__main__":
    with open('resize_recommendation.json') as f:  # Reading from resize_recommendation.json
        outputs = json.load(f)

    instance_id = outputs['instance_id']
    region = outputs['region']
    desired_type = outputs['ai_suggested_instance_type']  # Using the AI suggested instance type

    resize_instance(instance_id, region, desired_type)