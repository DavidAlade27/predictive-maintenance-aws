import boto3
import json
from decimal import Decimal

bedrock = boto3.client("bedrock-runtime", region_name="eu-north-1")
dynamodb = boto3.resource("dynamodb", region_name="eu-north-1")
table = dynamodb.Table("pdm_knowledge_base")

with open("knowledge_base.md", "r") as f:
    content = f.read()

sections = content.split("## ")
entries = [s.strip() for s in sections if s.strip()]

for entry in entries:
    lines = entry.split("\n", 1)
    fault_type = lines[0].strip()
    text = lines[1].strip() if len(lines) > 1 else ""

    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": text})
    )
    result = json.loads(response["body"].read())
    embedding = result["embedding"]

    table.put_item(
        Item={
            "fault_type": fault_type,
            "text": text,
            "embedding": [Decimal(str(x)) for x in embedding]
        }
    )
    print(f"Stored embedding for: {fault_type}")

print("Done.")
