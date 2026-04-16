#!/usr/bin/env python3
"""
invoke_lambda.py - Script to invoke Lambda function multiple times for testing

Usage:
    python invoke_lambda.py [function_name] [region] [count] [delay]

Examples:
    python invoke_lambda.py                                    # Default: 20 invocations
    python invoke_lambda.py my-function us-east-1 50 0.5     # 50 invocations, 0.5s delay
    python invoke_lambda.py test-lambda ap-south-1 30 2       # 30 invocations, 2s delay
"""

import argparse
import time
import json
import sys
import boto3
from datetime import datetime


def invoke_lambda(function_name: str, region: str, payload: dict = None) -> dict:
    """Invoke a Lambda function and return the response."""
    client = boto3.client('lambda', region_name=region)
    
    if payload is None:
        payload = {}
    
    response = client.invoke(
        FunctionName=function_name,
        Payload=json.dumps(payload),
        InvocationType='RequestResponse'
    )
    
    return {
        'status_code': response['StatusCode'],
        'response': json.loads(response['Payload'].read().decode('utf-8'))
    }


def main():
    parser = argparse.ArgumentParser(
        description='Invoke AWS Lambda function multiple times for testing'
    )
    parser.add_argument(
        '-f', '--function',
        default='test-lambda',
        help='Lambda function name (default: test-lambda)'
    )
    parser.add_argument(
        '-r', '--region',
        default='ap-south-1',
        help='AWS region (default: ap-south-1)'
    )
    parser.add_argument(
        '-c', '--count',
        type=int,
        default=20,
        help='Number of invocations (default: 20)'
    )
    parser.add_argument(
        '-d', '--delay',
        type=float,
        default=1.0,
        help='Delay between invocations in seconds (default: 1.0)'
    )
    
    args = parser.parse_args()
    
    print(f"🚀 Invoking Lambda function '{args.function}' in {args.region}")
    print(f"📊 Will invoke {args.count} times with {args.delay}s delay between each\n")
    
    success = 0
    failed = 0
    
    for i in range(1, args.count + 1):
        payload = {
            'invocation': i,
            'timestamp': datetime.now().isoformat(),
            'test': True
        }
        
        try:
            result = invoke_lambda(args.function, args.region, payload)
            
            if result['status_code'] == 200:
                print(f"[{i:2d}/{args.count}] ✅ OK - {result['response']}")
                success += 1
            else:
                print(f"[{i:2d}/{args.count}] ❌ FAILED - Status: {result['status_code']}")
                failed += 1
                
        except Exception as e:
            print(f"[{i:2d}/{args.count}] ❌ ERROR - {str(e)}")
            failed += 1
        
        if i < args.count:
            time.sleep(args.delay)
    
    print(f"\n{'='*50}")
    print(f"✅ Completed!")
    print(f"   Successful: {success}")
    print(f"   Failed: {failed}")
    print(f"   Total: {args.count}")
    print(f"{'='*50}")
    print(f"\n📋 Check CloudWatch logs at: /aws/lambda/{args.function}")


if __name__ == '__main__':
    main()
