import json
import boto3
import time

bedrock = boto3.client('bedrock-runtime')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('pdm_telemetry')
kb_table = dynamodb.Table('pdm_knowledge_base')
parts_table = dynamodb.Table('pdm_spare_parts')
machine_config_table = dynamodb.Table('pdm_machine_config')

def get_downtime_savings(device_id):
    cfg = machine_config_table.get_item(Key={'device_id': device_id}).get('Item')
    if not cfg:
        return None
    hours_saved = cfg['unplanned_downtime_hours'] - cfg['planned_downtime_hours']
    return {'hours_saved': hours_saved,
            'savings': cfg['downtime_cost_per_hour'] * hours_saved}

sns = boto3.client('sns')
ALERT_TOPIC_ARN = 'arn:aws:sns:eu-north-1:YOUR_ACCOUNT_ID:pdm_fault_alerts'
ALERT_COOLDOWN_SECONDS = 300

def send_fault_alert(device_id, predicted_fault, savings_info, parts_summary, explanation):
    now = int(time.time())
    try:
        machine_config_table.update_item(
            Key={'device_id': device_id},
            UpdateExpression='SET last_alert_at = :now',
            ConditionExpression='attribute_not_exists(last_alert_at) OR last_alert_at < :cutoff',
            ExpressionAttributeValues={':now': now, ':cutoff': now - ALERT_COOLDOWN_SECONDS}
        )
    except machine_config_table.meta.client.exceptions.ConditionalCheckFailedException:
        return
    try:
        message = (
            f"Fault detected on {device_id}\n\n"
            f"Predicted fault: {predicted_fault}\n"
            f"Estimated savings if acted on now: ${savings_info['savings']:,.0f} "
            f"({savings_info['hours_saved']} hours of downtime avoided)\n"
            f"Spare parts: {parts_summary}\n\n"
            f"AI recommendation:\n{explanation}"
        )
        sns.publish(
            TopicArn=ALERT_TOPIC_ARN,
            Subject=f"Fault alert: {predicted_fault} on {device_id}",
            Message=message
        )
    except Exception as e:
        print(f"ALERT FAILED: {e}")

MODEL_ID = 'eu.anthropic.claude-haiku-4-5-20251001-v1:0'


def retrieve_context(fault_type):
    try:
        response = kb_table.get_item(Key={'fault_type': fault_type})
        return response.get('Item', {}).get('text', '')
    except Exception as e:
        print(f"DEBUG - lookup failed for {fault_type}: {e}")
        return ''


def check_spare_parts(fault_type):
    try:
        response = parts_table.get_item(Key={'fault_type': fault_type})
        item = response.get('Item', {})
        return {
            'part_name': item.get('part_name', 'Unknown'),
            'stock_count': int(item.get('stock_count', 0))
        }
    except Exception as e:
        print(f"DEBUG - parts lookup failed for {fault_type}: {e}")
        return {'part_name': 'Unknown', 'stock_count': 0}


TOOLS = [
    {
        "name": "check_spare_parts",
        "description": "Check current spare parts inventory for a given bearing fault type before recommending a replacement.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fault_type": {
                    "type": "string",
                    "description": "The fault type to check inventory for, e.g. InnerRace, OuterRace, Ball, Normal"
                }
            },
            "required": ["fault_type"]
        }
    }
]


def lambda_handler(event, context):
    for record in event['Records']:
        if record['eventName'] != 'INSERT':
            continue

        new_image = record['dynamodb']['NewImage']
        anomaly = new_image.get('anomaly', {}).get('BOOL', False)
        if not anomaly:
            continue

        device_id = new_image['device_id']['S']
        timestamp = new_image['timestamp']['S']
        mean = new_image['mean']['N']
        std = new_image['std']['N']
        rms = new_image['rms']['N']
        peak = new_image['peak']['N']
        predicted_fault = new_image.get('predicted_fault', {}).get('S', 'Unknown')

        reference_text = retrieve_context(predicted_fault)

        savings_info = get_downtime_savings(device_id) or {'savings': 0, 'hours_saved': 0}
        prompt = (
            f"A vibration sensor on device {device_id} recorded these stats "
            f"at {timestamp}: mean={mean}, std={std}, rms={rms}, peak={peak}. "
            f"This has been flagged as a possible fault, and a machine learning "
            f"model has classified it as: {predicted_fault}. "
            f"Here is reference guidance for this fault type: {reference_text} "
            f"Before making your final recommendation, check spare parts inventory "
            f"for this fault type using the check_spare_parts tool. "
            f"Then, in 2-3 sentences, explain what this specific fault type likely "
            f"indicates and recommend a next step for a maintenance engineer, "
            f"factoring in whether a replacement part is currently in stock."
            f" Also state that acting now avoids about ${savings_info['savings']:,.0f} of unplanned downtime ({savings_info['hours_saved']} hours)."
        )

        messages = [{"role": "user", "content": prompt}]

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 400,
            "tools": TOOLS,
            "messages": messages
        })

        response = bedrock.invoke_model(modelId=MODEL_ID, body=body)
        response_body = json.loads(response['body'].read())

        if response_body.get('stop_reason') == 'tool_use':
            messages.append({"role": "assistant", "content": response_body['content']})

            for block in response_body['content']:
                if block.get('type') == 'tool_use' and block['name'] == 'check_spare_parts':
                    tool_input = block['input']
                    tool_result = check_spare_parts(tool_input['fault_type'])

                    messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": block['id'],
                                "content": json.dumps(tool_result)
                            }
                        ]
                    })

            follow_up_body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 300,
                "tools": TOOLS,
                "messages": messages
            })
            response = bedrock.invoke_model(modelId=MODEL_ID, body=follow_up_body)
            response_body = json.loads(response['body'].read())

        explanation = ""
        for block in response_body.get('content', []):
            if block.get('type') == 'text':
               explanation = block['text']
               break

        parts_info = tool_result if 'tool_result' in dir() else None
        parts_summary = (
           f"{parts_info['part_name']}: {parts_info['stock_count']} in stock"
           if parts_info else "Not checked"
        )

        table.update_item(
            Key={'device_id': device_id, 'timestamp': timestamp},
            UpdateExpression='SET explanation = :e, kb_reference = :k, parts_checked = :p, estimated_savings = :s, downtime_hours_avoided = :h',
            ExpressionAttributeValues={
               ':e': explanation,
               ':k': reference_text,
               ':p': parts_summary,
               ':s': savings_info['savings'],
               ':h': savings_info['hours_saved']
            }
        )
        send_fault_alert(device_id, predicted_fault, savings_info, parts_summary, explanation)

    return {'statusCode': 200}