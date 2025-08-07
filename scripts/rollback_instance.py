import boto3
import json
import time
import sys

def get_root_volume_id(ec2_client, instance_id):
    """
    Finds the root volume ID and device name for the given instance.
    """
    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        
        for mapping in instance['BlockDeviceMappings']:
            if mapping['DeviceName'] == instance['RootDeviceName']:
                return mapping['Ebs']['VolumeId'], mapping['DeviceName']
    except Exception as e:
        print(f"Error finding root volume for instance {instance_id}: {e}")
        return None, None
    return None, None

def rollback_instance_with_snapshot():
    """
    Performs a snapshot-based rollback of an EC2 instance, including instance type change and cleanup.
    """
    try:
        with open('rollback.json') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading rollback.json file: {e}")
        sys.exit(1)

    instance_id = data.get('instance_id')
    region = data.get('region')
    original_instance_type = data.get('original_instance_type')
    snapshot_ids = data.get('snapshot_ids')

    if not all([instance_id, region, original_instance_type, snapshot_ids]):
        print("Required data (instance_id, region, original_instance_type, snapshot_ids) not found in rollback.json")
        sys.exit(1)

    ec2 = boto3.client('ec2', region_name=region)

    # 1. Stop the instance
    print(f"Stopping instance {instance_id}...")
    ec2.stop_instances(InstanceIds=[instance_id])
    waiter = ec2.get_waiter('instance_stopped')
    waiter.wait(InstanceIds=[instance_id])
    print("Instance stopped.")

    # 2. Get old volume details and create new volume
    print("Getting root volume details...")
    old_volume_id, device_name = get_root_volume_id(ec2, instance_id)
    if not old_volume_id:
        print("Could not find the root volume ID. Aborting rollback.")
        sys.exit(1)

    print(f"Creating a new volume from snapshot {snapshot_ids[0]}...")
    try:
        new_volume = ec2.create_volume(
            SnapshotId=snapshot_ids[0],
            AvailabilityZone=ec2.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances'][0]['Placement']['AvailabilityZone']
        )
        new_volume_id = new_volume['VolumeId']
        print(f"New volume {new_volume_id} created.")
    except Exception as e:
        print(f"Error creating new volume from snapshot: {e}")
        sys.exit(1)

    # Wait for the new volume to be available
    waiter = ec2.get_waiter('volume_available')
    waiter.wait(VolumeIds=[new_volume_id])

    # 3. Detach the old volume
    print(f"Detaching old volume {old_volume_id}...")
    ec2.detach_volume(VolumeId=old_volume_id, InstanceId=instance_id, Device=device_name)
    waiter = ec2.get_waiter('volume_available')
    waiter.wait(VolumeIds=[old_volume_id])
    print("Old volume detached.")

    # 4. Attach the new volume
    print(f"Attaching new volume {new_volume_id}...")
    ec2.attach_volume(VolumeId=new_volume_id, InstanceId=instance_id, Device=device_name)
    waiter = ec2.get_waiter('volume_in_use')
    waiter.wait(VolumeIds=[new_volume_id])
    print("New volume attached.")

    # 5. Modify instance type
    print(f"Modifying instance {instance_id} to type {original_instance_type}...")
    ec2.modify_instance_attribute(InstanceId=instance_id, Attribute='instanceType', Value=original_instance_type)
    print("Instance type changed.")

    # 6. Start the instance again
    print(f"Starting instance {instance_id}...")
    ec2.start_instances(InstanceIds=[instance_id])
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])
    print("Instance started. Rollback complete.")

    # 7. Cleanup (NEW STEP)
    print("\n--- Starting Cleanup ---")
    
    # Delete the old volume
    try:
        ec2.delete_volume(VolumeId=old_volume_id)
        print(f"✅ Old volume {old_volume_id} deleted successfully.")
    except Exception as e:
        print(f"❌ Error deleting old volume {old_volume_id}: {e}")

    # Delete the snapshot used for rollback
    try:
        ec2.delete_snapshot(SnapshotId=snapshot_ids[0])
        print(f"✅ Snapshot {snapshot_ids[0]} deleted successfully.")
    except Exception as e:
        print(f"❌ Error deleting snapshot {snapshot_ids[0]}: {e}")

if __name__ == "__main__":
    rollback_instance_with_snapshot()
