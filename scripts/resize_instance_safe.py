import boto3
import json
import sys

def check_instance_type_supported(region, instance_type, architecture):
    ec2 = boto3.client('ec2', region_name=region)
    paginator = ec2.get_paginator('describe_instance_types')
    for page in paginator.paginate():
        for itype in page['InstanceTypes']:
            if itype['InstanceType'] == instance_type:
                arch_supported = architecture in itype.get('ProcessorInfo', {}).get('SupportedArchitectures', [])
                return arch_supported
    return False

def resize_instance(instance_id, region, new_type):
    ec2 = boto3.client('ec2', region_name=region)

    instance_info = ec2.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances'][0]
    current_type = instance_info['InstanceType']
    architecture = instance_info['Architecture']

    print(f"Current Type: {current_type} | Target Type: {new_type} | Architecture: {architecture}")

    if not check_instance_type_supported(region, new_type, architecture):
        print(f"ERROR: Instance type {new_type} is not compatible with architecture {architecture}.")
        sys.exit(1)

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
    with open('input.json') as f:
        inputs = json.load(f)

    instance_id = inputs['instance_id']
    region = inputs['region']
    desired_type = inputs['desired_instance_type']

    resize_instance(instance_id, region, desired_type)
