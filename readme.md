# AWS Lambda Log Analyser

A comprehensive Streamlit dashboard for analyzing AWS Lambda logs, detecting errors, and monitoring performance metrics with detailed visualizations and exports.

---

## Features

### 📈 Overview Tab
- **Executive Summary** - Key metrics at a glance (total events, errors, cold starts, avg duration)
- **Health Score** - Overall Lambda function health indicator (0-100%)
- **Event Distribution** - Pie chart showing breakdown of event types
- **Quick Stats** - Duration stats, memory stats, invocation stats, log group breakdown

### ⏱️ Performance Tab
- **Duration Distribution** - Interactive histogram of invocation durations
- **Memory Usage Distribution** - Interactive histogram of memory usage
- **Invocation Timeline** - Time-series chart showing duration over time with cold start markers
- **Billed Duration Analysis** - Total and average billed duration
- **Timeout Risk Analysis** - Shows invocations at risk of timing out
- **Cold Start Impact** - Compare cold start vs warm invocation durations
- **Cost Estimation** - Estimated AWS Lambda costs based on billed duration and memory

### 🚨 Errors Tab
- **Error Summary** - Total errors, error rate, unique error types
- **Error Timeline** - Scatter plot showing when errors occurred
- **Error Details** - Full error messages with expandable details
- **Error Pattern Analysis** - Bar chart of error types distribution

### 📋 Raw Data Tab
- **Complete Invocation Data** - Full table of all Lambda invocations
- **All Events** - START, END, ERROR, and other events
- **CSV Export** - Download invocation data as CSV

### 📥 Export Tab
- **PDF Report** - Comprehensive analysis report
- **JSON Export** - Full analysis data in JSON format
- **Analysis Metadata** - Quick view of analysis configuration

---

## Architecture

```
Browser (Streamlit Dashboard)
        │
        ▼
   Run Analysis Button
        │
        ├──► CloudWatch Logs  (fetch recent log events via boto3)
        │
        ├──► Log Parser       (detect errors, extract duration/memory/cold starts)
        │
        └──► Dashboard        (visualize results, export reports)
```

---

## Project Structure

```
lambda-analyser/
├── src/
│   ├── config.py             # Environment variable config
│   ├── log_fetcher.py        # CloudWatch Logs fetching (paginated)
│   └── log_parser.py         # Log parsing: errors, REPORT metrics, cold starts
├── test/
│   ├── test_log_parser.py
│   └── test_dynamodb_writer.py
├── app.py                    # Streamlit dashboard application
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## Quick Start

### 1. Setup

```bash
git clone <your-repo-url>
cd lambda-analyser
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Run the Dashboard

```bash
streamlit run app.py
```

The dashboard will open in your browser at `http://localhost:8501`.

### 3. Configure and Analyze

1. Enter your AWS credentials in the sidebar
2. Select your AWS region (e.g., `ap-south-1` for Mumbai)
3. Add CloudWatch log group names (one per line)
4. Set the lookback period in minutes
5. Configure Lambda memory size and timeout for accurate cost estimation
6. Click "Run Analysis"

---

## Metrics Analyzed

### Performance Metrics
- Invocation duration (ms) - Min, Max, Avg, P95, P99
- Billed duration (ms) - Total and average
- Memory configured vs used (MB)
- Memory efficiency percentage
- Estimated cost ($)

### Operational Metrics
- Cold start detection and count
- Cold start rate percentage
- Cold start impact (slowdown vs warm invocations)
- Timeout risk analysis

### Error Metrics
- Total errors and error rate
- Unique error types
- Error timeline
- Error message details
- Error pattern analysis

### Health Score
- Composite score (0-100%) based on:
  - Error rate (50% weight)
  - Cold start rate (10% weight)
  - P95 duration threshold (20% weight)
  - Memory efficiency (20% weight)

---

## AWS Permissions Required

The AWS credentials you provide need permissions to:
- `logs:FilterLogEvents` - Read CloudWatch logs
- `logs:DescribeLogStreams` - List log streams
- `logs:DescribeLogGroups` - List log groups (optional)

Example IAM policy:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:FilterLogEvents",
                "logs:DescribeLogStreams",
                "logs:DescribeLogGroups"
            ],
            "Resource": "*"
        }
    ]
}
```

---

## Cost Estimation

The dashboard estimates Lambda costs based on:
- **Compute charges**: $0.0000166667 per GB-second
- **Request charges**: $0.20 per 1 million requests

Formula: `cost = (total_billed_seconds × memory_gb × 0.0000166667) + (invocations × 0.0000002)`

---

## Run Tests

```bash
source .venv/bin/activate
PYTHONPATH=src pytest tests/ -v
```
