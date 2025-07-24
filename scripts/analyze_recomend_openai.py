import boto3
import os
import json
from datetime import datetime, timedelta, timezone
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------- AWS Metrics & Instance Info ----------
#Fetches average hourly CPU utilization for the past 7 days from CloudWatch for a specific EC2 instance
def fetch_metrics(instance_id, region):
    client = boto3.client('cloudwatch', region_name=region)
    resp = client.get_metric_statistics(
        Namespace='AWS/EC2',
        MetricName='CPUUtilization',
        Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
        StartTime=datetime.now(timezone.utc) - timedelta(days=7),
        EndTime=datetime.now(timezone.utc),
        Period=3600,
        Statistics=['Average']
    )
    datapoints = [d['Average'] for d in resp['Datapoints']]
    return sum(datapoints) / len(datapoints) if datapoints else 0

def fetch_instance_details(instance_id, region):
    client = boto3.client('ec2', region_name=region)
    reservations = client.describe_instances(InstanceIds=[instance_id])['Reservations']
    instance = reservations[0]['Instances'][0]
    return instance['InstanceType'], instance['Architecture']

# ---------- Instance Types Cache ----------

def fetch_available_instance_types(region, architecture, cache_file='instance_types_cache.json'):
    now = datetime.now(timezone.utc) 

    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache = json.load(f)
            key = f"{region}_{architecture}"

            if key in cache:
                last_updated_str = cache[key].get('last_updated')
                if last_updated_str:
                    last_updated = datetime.strptime(last_updated_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    if now - last_updated < timedelta(hours=23):
                        return cache[key]['instance_types']

    ec2 = boto3.client('ec2', region_name=region)
    paginator = ec2.get_paginator('describe_instance_types')
    valid_types = []

    for page in paginator.paginate():
        for itype in page['InstanceTypes']:
            if architecture in itype['ProcessorInfo']['SupportedArchitectures']:
                valid_types.append(itype['InstanceType'])

    key = f"{region}_{architecture}"
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache = json.load(f)
    else:
        cache = {}

    cache[key] = {
        'last_updated': now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        'instance_types': valid_types
    }

    with open(cache_file, 'w') as f:
        json.dump(cache, f, indent=2)

    return valid_types

# ---------- Logical Shortlist Builder ----------

def build_instance_shortlist(current_instance_type, valid_types):
    family = current_instance_type.split('.')[0]
    sizes = ['nano', 'micro', 'small', 'medium', 'large', 'xlarge', '2xlarge', '4xlarge', '8xlarge', '16xlarge', '32xlarge', '48xlarge']

    # Detect current size
    current_size = current_instance_type.split('.')[1]

    # Build shortlist: same family + compatible families
    compatible_families = [family]
    if family.startswith('t3'):
        compatible_families += ['t4g', 't3a']
    if family.startswith('m6'):
        compatible_families += ['m5', 'm6i', 'm7i']

    # Shortlist: only same/compatible families
    shortlist = [t for t in valid_types if any(t.startswith(fam) for fam in compatible_families)]

    # Sort shortlist logically (family-wise + size-wise)
    def size_rank(t):
        size = t.split('.')[1]
        return sizes.index(size) if size in sizes else 999

    shortlist = sorted(shortlist, key=lambda t: (compatible_families.index(t.split('.')[0]) if t.split('.')[0] in compatible_families else 99, size_rank(t)))

    return shortlist

# ---------- CPU Threshold Logic ----------

def threshold_decision(cpu):
    if cpu < 30:
        return "downgrade"
    elif cpu > 50:
        return "upgrade"
    else:
        return "retain"

# ---------- OpenAI Suggestion ----------

def ai_suggest_instance_type(current_instance_type, architecture, decision, shortlist):
    api_key = os.getenv('API_KEY')
    api_url = os.getenv('API_URL')
    api_ver = os.getenv('API_VER')
    api_model = os.getenv('API_MODEL')
    app_id = os.getenv('APP_ID')

    # Define the URL for the chat completion endpoint
    url = f"{api_url}/v1/{app_id}/openai/deployments/{api_model}/chat/completions?api_version={api_ver}"

    shortlist_trimmed = ', '.join(shortlist[:20])
    current_family = current_instance_type.split('.')[0]

    prompt = f"""You are optimizing AWS EC2 instance sizing.

Current instance type: {current_instance_type}
Architecture: {architecture}
Action recommended: {decision.upper()} (based on CPU usage analysis).
Instance family: {current_family}

Available options for {architecture} in this region (choose strictly from this list):
{shortlist_trimmed}

Recommend a new instance type that represents a logical {decision} (next size up/down). Avoid unnecessary large jumps.

Respond with only the instance type name."""

    payload = json.dumps({
        "messages": [
            {"role": "system", "content": "You are a helpful assistant within the Spark Assist platform."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "n": 1,
        "stream": False,
        "presence_penalty": 0,
        "frequency_penalty": 0,
        "top_p": 1
    })

    headers = {
        'api-key': api_key,
        'Content-Type': 'application/json'
    }

    response = requests.post(url, headers=headers, data=payload)
    response_data = response.json()

    if 'choices' in response_data and len(response_data['choices']) > 0:
        return response_data['choices'][0]['message']['content'].strip()
    else:
        return None

def validate_instance_type(suggested_type, valid_types):
    return suggested_type in valid_types

# ---------- Main Execution ----------

if __name__ == "__main__":
    instance_id = input("Enter EC2 Instance ID: ")
    region = input("Enter AWS Region (e.g. us-east-1): ")

    instance_type, architecture = fetch_instance_details(instance_id, region)
    valid_instance_types = fetch_available_instance_types(region, architecture)
    cpu = fetch_metrics(instance_id, region)

    print(f"\nCurrent Instance Type: {instance_type}")
    print(f"Architecture: {architecture}")
    print(f"Average CPU Usage: {cpu:.2f}%")

    decision = threshold_decision(cpu)
    print(f"\nThreshold-based Decision: {decision.upper()}")

    suggested_type = None
    validated = False

    if decision in ["upgrade", "downgrade"]:
        shortlist = build_instance_shortlist(instance_type, valid_instance_types)
        print(f"\nFiltered Instance Shortlist ({len(shortlist)}): {shortlist[:10]}...")

        suggested_type = ai_suggest_instance_type(instance_type, architecture, decision, shortlist)
        print(f"\nAI Suggested Instance Type: {suggested_type}")

        validated = validate_instance_type(suggested_type, valid_instance_types)
        if validated:
            print(f"\n✅ Recommendation Validated: Proceed to {decision} to {suggested_type}")
        else:
            print(f"\n❌ WARNING: AI suggested invalid instance type ({suggested_type}). Action aborted.")
    else:
        print("\nNo resizing required based on thresholds.")

    result = {
        "instance_id": instance_id,
        "region": region,
        "current_instance_type": instance_type,
        "architecture": architecture,
        "average_cpu_usage_percent": round(cpu, 2),
        "decision": decision,
        "ai_suggested_instance_type": suggested_type if suggested_type else None,
        "validated": validated,
        "action_required": validated
    }

    with open("resize_recommendation.json", "w") as f:
        json.dump(result, f, indent=2)

    print("\n✅ Output saved to resize_recommendation.json")