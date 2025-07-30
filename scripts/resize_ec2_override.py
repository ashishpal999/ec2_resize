import boto3
import json
import sys

def resize_instance(instance_id, region, new_type, requester, approver):
    ec2 = boto3.client('ec2', region_name=region)

    instance_info = ec2.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances'][0]
    current_type = instance_info['InstanceType']
    architecture = instance_info['Architecture']
    state = instance_info['State']['Name']

    print(f"Requester: {requester} | Approver: {approver}")
    print(f"Current Type: {current_type} | Target Type: {new_type} | Architecture: {architecture}")

    # ✅ Skip if already desired type
    if current_type == new_type:
        print(f"⚠️ No action needed: Instance is already of type '{current_type}'.")
        sys.exit(0)

    # ✅ Dry-run permission check
    try:
        ec2.modify_instance_attribute(
            InstanceId=instance_id,
            InstanceType={'Value': new_type},
            DryRun=True
        )
        print("✅ Dry-run passed. Proceeding with override resize...")
    except ec2.exceptions.ClientError as e:
        if 'DryRunOperation' not in str(e):
            print(f"❌ Dry-run failed: {e}")
            sys.exit(1)

    if state != 'stopped':
        print("🔻 Stopping instance...")
        ec2.stop_instances(InstanceIds=[instance_id])
        ec2.get_waiter('instance_stopped').wait(InstanceIds=[instance_id])
        print("✅ Instance stopped.")

    # Save rollback info
    with open('rollback.json', 'w') as f:
        json.dump({'previous_instance_type': current_type}, f)

    # Modify instance type
    print(f"🔧 Changing instance type to {new_type} (override requested)...")
    ec2.modify_instance_attribute(
        InstanceId=instance_id,
        InstanceType={'Value': new_type}
    )
    print(f"✅ Instance type changed from {current_type} to {new_type}.")

    # Start instance
    ec2.start_instances(InstanceIds=[instance_id])
    print("🚀 Instance started successfully.")

if __name__ == "__main__":
    with open('../input.json') as f:
        data = json.load(f)

    instance_id = data['instance_id']
    region = data['region']
    desired_type = data['desired_instance_type']
    requester = data.get('requester_email', 'unknown')
    approver = data.get('approver_email', 'unknown')

    resize_instance(instance_id, region, desired_type, requester, approver)
