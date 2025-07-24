import boto3
import datetime
import json

def fetch_metrics(instance_id, region):
    client = boto3.client('cloudwatch', region_name=region)
    response = client.get_metric_statistics(
        Namespace='AWS/EC2',
        MetricName='CPUUtilization',
        Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
        StartTime=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=7),
        EndTime=datetime.datetime.now(datetime.UTC),
        Period=3600,
        Statistics=['Average']
    )
    datapoints = [dp['Average'] for dp in response['Datapoints']]
    return sum(datapoints) / len(datapoints) if datapoints else 0

def recommend_action(cpu):
    if cpu < 30:
        return "downgrade"
    elif cpu > 70:
        return "upgrade"
    else:
        return "no_change"

if __name__ == "__main__":
    with open('../input.json') as f:
        inputs = json.load(f)

    instance_id = inputs['instance_id']
    region = inputs['region']

    avg_cpu = fetch_metrics(instance_id, region)
    action = recommend_action(avg_cpu)

    result = {
        "average_cpu": avg_cpu,
        "action": action
    }

    with open('recommendation.json', 'w') as f:
        json.dump(result, f)

    print(f"Average CPU Usage: {avg_cpu}% — Recommended Action: {action}")
