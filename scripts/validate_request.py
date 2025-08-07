import boto3
import os
import json
import sys
from datetime import datetime, timedelta
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ---------- AWS Metrics & Instance Info ----------

def fetch_instance_details(instance_id, region):
    """Fetches the current instance type and architecture."""
    client = boto3.client('ec2', region_name=region)
    try:
        reservations = client.describe_instances(InstanceIds=[instance_id])['Reservations']
        if not reservations:
            raise ValueError(f"Instance ID {instance_id} not found.")
        instance = reservations[0]['Instances'][0]
        # Boto3 does not have a direct attribute for OS, so we'll infer based on AMI or other data.
        # This is a placeholder; a more robust solution would involve checking the AMI name.
        os_info = instance.get('PlatformDetails', 'Linux/UNIX')
        return instance['InstanceType'], instance['Architecture'], os_info
    except Exception as e:
        print(f"Error fetching instance details: {e}")
        sys.exit(1)

# ---------- Instance Types Cache ----------

def fetch_available_instance_types(region, architecture, cache_file='instance_types_cache.json'):
    """Fetches and caches all valid instance types for a given architecture and region."""
    now = datetime.utcnow()
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache = json.load(f)
            key = f"{region}_{architecture}"
            if key in cache:
                last_updated_str = cache[key].get('last_updated')
                if last_updated_str:
                    last_updated = datetime.strptime(last_updated_str, "%Y-%m-%dT%H:%M:%SZ")
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

def _get_size_rank(instance_type):
    """Internal helper to get a numerical rank for instance size."""
    sizes = ['nano', 'micro', 'small', 'medium', 'large', 'xlarge', '2xlarge', '4xlarge', '8xlarge', '16xlarge', '32xlarge', '48xlarge']
    try:
        size = instance_type.split('.')[1]
        return sizes.index(size)
    except (IndexError, ValueError):
        return -1 # Return -1 for unknown sizes

# ---------- Groq AI for Compatibility Analysis ----------

def ai_analyze_compatibility(current_type, desired_type, architecture, os_info, valid_types):
    """Uses Groq AI to analyze if the desired instance type is a compatible upgrade."""
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    # Pre-computation based on original script's logic
    is_requested_type_valid_for_arch = desired_type in valid_types
    is_a_size_increase = _get_size_rank(desired_type) > _get_size_rank(current_type)
    is_same_family = current_type.split('.')[0] == desired_type.split('.')[0]
    is_downgrade = _get_size_rank(desired_type) < _get_size_rank(current_type) and is_same_family

    prompt = f"""You are an expert AWS solutions architect.
Your task is to analyze an EC2 instance resize request.
Current instance type: {current_type}
Desired instance type: {desired_type}
Operating System: {os_info}
Architecture: {architecture}

# --- Factual Analysis from our Script ---
1. The requested instance type is {'' if is_requested_type_valid_for_arch else 'NOT '}available for this architecture.
2. The requested change is a {'' if is_a_size_increase else 'downgrade or side-grade'} in size.
3. The current and desired instance types {'are in the same family' if is_same_family else 'are in DIFFERENT families'}.
# --------------------------------------------------

Based on the provided facts and your knowledge of AWS best practices, determine if the desired instance type is a valid and logical upgrade.
A change is considered valid if it meets these criteria:
* **Architecture Compatibility**: The architecture of the requested instance must be the same.
* **Logical Progression**: The change should be a logical upgrade within the same or a compatible family (e.g., T3 to T4g).
* **True Upgrade**: The change must not be a downgrade.

Respond with 'VALID' if the request is logical and compatible, or 'NOT_VALID' if it is not. Provide a detailed, one-sentence reason for the decision.

Example 1:
Current type: t2.micro
Desired type: t2.medium
Response: VALID. The t2.medium offers more resources within the same instance family.

Example 2:
Current type: t2.micro
Desired type: c5.large
Response: NOT_VALID. This is a change from a general-purpose to a compute-optimized family, which may be illogical without more context.

Example 3:
Current type: t2.micro
Desired type: t3.micro
Response: VALID. T3 instances are the next generation of general-purpose instances, making this a logical upgrade.

Example 4:
Current type: t3.small
Desired type: m5.large
Response: NOT_VALID. This is a jump from a burstable general-purpose instance to a fixed-performance one, which may not be a logical upgrade.

Example 5:
Current type: t2.large
Desired type: t2.medium
Response: NOT_VALID. This is a downgrade in size within the same instance family.

Your response should follow the format 'VALID/NOT_VALID. [Reason].'
"""

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3-70b-8192"
    )

    response = chat_completion.choices[0].message.content.strip()
    return response

# ---------- Main Execution ----------

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze_resize_request.py <path_to_input.json>")
        sys.exit(1)

    input_file_path = sys.argv[1]
    
    # Load input data
    try:
        with open(input_file_path) as f:
            input_data = json.load(f)
        
        instance_id = input_data['instance_id']
        region = input_data['region']
        desired_instance_type = input_data['desired_instance_type']
    except (FileNotFoundError, KeyError) as e:
        print(f"Error loading input file: {e}")
        sys.exit(1)

    # Fetch existing instance stats (without CPU)
    current_instance_type, architecture, os_info = fetch_instance_details(instance_id, region)
    
    # Create list of available compatible instance types
    valid_instance_types = fetch_available_instance_types(region, architecture)

    print("\n--- EC2 Instance Analysis ---")
    print(f"Current Instance Type: {current_instance_type}")
    print(f"Architecture: {architecture}")
    print(f"Operating System: {os_info}")
    print(f"Requested Instance Type: {desired_instance_type}")
    
    # Authenticate and use AI
    print("\n--- AI Compatibility Check ---")
    ai_response = ai_analyze_compatibility(current_instance_type, desired_instance_type, architecture, os_info, valid_instance_types)
    
    decision, *reason_parts = ai_response.split('.', 1)
    reason = reason_parts[0].strip() if reason_parts else "No reason provided."

    is_valid = decision.strip().upper() == 'VALID'
    
    print(f"Decision: {decision.strip().upper()}")
    print(f"Reason: {reason}")
    
    # Prepare and save results
    result = {
        "instance_id": instance_id,
        "region": region,
        "current_instance_type": current_instance_type,
        "requested_instance_type": desired_instance_type,
        "architecture": architecture,
        "operating_system": os_info,
        "compatibility_decision": decision.strip().upper(),
        "reason": reason,
        "is_valid_upgrade": is_valid
    }

    with open("resize_validation.json", "w") as f:
        json.dump(result, f, indent=2)

    print("\n✅ Output saved to resize_validation.json")
