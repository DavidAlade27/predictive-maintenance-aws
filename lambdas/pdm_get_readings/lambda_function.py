import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('pdm_telemetry')

def decimal_to_number(obj):
    if isinstance(obj, list):
        return [decimal_to_number(v) for v in obj]
    if isinstance(obj, dict):
        return {k: decimal_to_number(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return float(obj)
    return obj

def lambda_handler(event, context):
    response = table.query(
        KeyConditionExpression='device_id = :d',
        ExpressionAttributeValues={':d': 'pdm_sensor_device'},
        ScanIndexForward=False,
        Limit=50
    )
    items = decimal_to_number(response['Items'])

    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json'
        },
    'body': json.dumps(items)
    }
        