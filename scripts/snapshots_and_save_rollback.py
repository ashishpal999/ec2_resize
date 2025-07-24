import boto3
import json
import sys
import time

def create_snapshots_and_prepare_rollback(instance_id, region):
    ec2 = boto3.client('ec2', region_name=region)

    # Get instance details
    reservations = ec2.describe_instances(InstanceIds=[instance_id])['Reservations']
    instance = reservations[0]['Instances'][0]
    original_instance_type = instance['InstanceType']

    # Get attached EBS volumes
    volumes = [dev['Ebs']['VolumeId'] for dev in instance['BlockDeviceMappings'] if 'Ebs' in dev]

    snapshot_ids = []
    print(f"Creating snapshots of attached volumes for instance {instance_id}...")

    for vol_id in volumes:
        print(f"Creating snapshot for volume {vol_id}...")
        snapshot = ec2.create_snapshot(VolumeId=vol_id, Description=f"Rollback snapshot for {instance_id}")
        snapshot_id = snapshot['SnapshotId']
        snapshot_ids.append(snapshot_id)

    # Wait for snapshots to complete (optional, can wait or skip)
    print("Waiting for snapshots to complete...")
    waiter = ec2.get_waiter('snapshot_completed')
    for snap_id in snapshot_ids:
        waiter.wait(SnapshotIds=[snap_id])
        print(f"Snapshot {snap_id} completed.")

    rollback_data = {
        "instance_id": instance_id,
        "region": region,
        "original_instance_type": original_instance_type,
        "snapshot_ids": snapshot_ids
    }

    with open('rollback.json', 'w') as f:
        json.dump(rollback_data, f, indent=2)

    print("Rollback data saved to rollback.json")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python create_snapshots_and_prepare_rollback.py <instance_id> <region>")
        sys.exit(1)

    instance_id = sys.argv[1]
    region = sys.argv[2]

    create_snapshots_and_prepare_rollback(instance_id, region)
