import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('pdm_telemetry')

THRESHOLD = 0.15

def lambda_handler(event, context):
    item = json.loads(json.dumps(event), parse_float=Decimal)
    item['anomaly'] = item['std'] > Decimal(str(THRESHOLD))

    mean = float(item['mean'])
    std = float(item['std'])
    rms = float(item['rms'])
    peak = float(item['peak'])
    mean_s = (mean - 0.015529833283607358) / 0.005369874584641386
    std_s = (std - 0.24307023168939534) / 0.22371267545584972
    rms_s = (rms - 0.24381568937982837) / 0.22350485359441521
    peak_s = (peak - 1.192221429780015) / 1.2038397293375984

    score_Ball = 2.377388491884463 + 0.08315396305983508 * mean_s + 0.2835927013986288 * std_s + 0.2609976188530672 * rms_s + -1.0991755622760253 * peak_s
    score_InnerRace = 2.732015711322899 + -0.9497917146808769 * mean_s + 1.4534037580525614 * std_s + 1.4470314456027165 * rms_s + 2.4125504092698282 * peak_s
    score_Normal = -4.585562406324706 + -0.9832534138456416 * mean_s + -4.105923911726443 * std_s + -4.079055137071332 * rms_s + -3.536123791298782 * peak_s
    score_OuterRace = -0.5238417968825967 + 1.8498911654666874 * mean_s + 2.368927452275261 * std_s + 2.37102607261556 * rms_s + 2.2227489443049757 * peak_s
    best_score = max(score_Ball, score_InnerRace, score_Normal, score_OuterRace)

    if best_score == score_Ball:
        predicted_fault = 'Ball'

    elif best_score == score_InnerRace:
        predicted_fault = 'InnerRace'

    elif best_score == score_Normal:
        predicted_fault = 'Normal'

    else:
        predicted_fault = 'OuterRace'
    item['predicted_fault'] = predicted_fault
    table.put_item(Item=item)
    return {'statusCode': 200}
    

