import boto3
import json
import sys

def rollback_instance(instance_id, region):
    ec2 = boto3.client('ec2', region_name=region)

    with open('rollback.json') as f:
        rollback_data = json.load(f)

    previous_type = rollback_data.get('previous_instance_type')
    if not previous_type:
        print("ERROR: Rollback data invalid.")
        sys.exit(1)

    print(f"Rolling back instance {instance_id} to {previous_type}...")

    instance_info = ec2.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances'][0]

    if instance_info['State']['Name'] != 'stopped':
        ec2.stop_instances(InstanceIds=[instance_id])
        ec2.get_waiter('instance_stopped').wait(InstanceIds=[instance_id])

    ec2.modify_instance_attribute(
        InstanceId=instance_id,
        InstanceType={'Value': previous_type}
    )

    ec2.start_instances(InstanceIds=[instance_id])
    print("Rollback complete.")

if __name__ == "__main__":
    with open('input.json') as f:
        inputs = json.load(f)

    rollback_instance(inputs['instance_id'], inputs['region'])
