#!/bin/bash
# invoke_lambda.sh - Script to invoke Lambda function multiple times for testing

FUNCTION_NAME=${1:-test-lambda}
REGION=${2:-ap-south-1}
COUNT=${3:-20}
DELAY=${4:-1}

echo "🚀 Invoking Lambda function '$FUNCTION_NAME' in $REGION"
echo "📊 Will invoke $COUNT times with $DELAY second delay between each"
echo ""

for i in $(seq 1 $COUNT); do
    echo -n "[$i/$COUNT] Invoking... "
    RESULT=$(aws lambda invoke \
        --function-name "$FUNCTION_NAME" \
        --payload '{"test": '$i', "timestamp": "'$(date -Iseconds)'"}' \
        --region "$REGION" \
        /tmp/lambda_resp.json 2>&1)
    
    if echo "$RESULT" | grep -q "StatusCode.*200"; then
        echo "✅ OK"
    else
        echo "❌ FAILED"
        echo "   Error: $RESULT"
    fi
    
    sleep "$DELAY"
done

echo ""
echo "✅ Done! Invoked $COUNT times."
echo "📋 Check your CloudWatch logs at: /aws/lambda/$FUNCTION_NAME"
