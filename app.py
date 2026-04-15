"""
app.py
Streamlit Dashboard for Lambda Log Analyser

Run: streamlit run app.py
"""

import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

sys.path.insert(0, str(Path(__file__).parent / "src"))

from log_fetcher import LogFetcher
from log_parser import LogParser, ParsedEvent, AnalysisSummary

st.set_page_config(
    page_title="Lambda Log Analyser",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

AWS_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "eu-west-1", "eu-west-2", "eu-central-1",
    "ap-south-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1",
]


def init_session_state():
    defaults = {
        "analysis_complete": False,
        "summary": None,
        "parsed_events": [],
        "raw_events": [],
        "log_groups": [],
        "lookback_minutes": 60,
        "timestamp": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def run_analysis(
    log_groups: List[str],
    lookback_minutes: int,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    aws_region: str,
) -> tuple:
    os.environ["AWS_ACCESS_KEY_ID"] = aws_access_key_id
    os.environ["AWS_SECRET_ACCESS_KEY"] = aws_secret_access_key

    fetcher = LogFetcher(region=aws_region)
    parser = LogParser()

    raw_events = list(fetcher.fetch_all_groups(log_groups, lookback_minutes))
    parsed_events = [parser.parse_event(raw) for raw in raw_events]
    summary = parser.build_summary(parsed_events, log_groups)

    return raw_events, parsed_events, summary


def generate_pdf(
    summary: AnalysisSummary,
    parsed_events: List[ParsedEvent],
    log_groups: List[str],
    lookback_minutes: int,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=20,
        spaceAfter=20,
        textColor=colors.HexColor("#1a1a2e"),
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=15,
        spaceAfter=10,
        textColor=colors.HexColor("#16213e"),
    )
    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=6,
    )

    elements = []
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    elements.append(Paragraph("Lambda Log Analysis Report", title_style))
    elements.append(Paragraph(f"<b>Generated:</b> {run_time}", body_style))
    elements.append(Paragraph(f"<b>Log Groups:</b> {', '.join(log_groups)}", body_style))
    elements.append(Paragraph(f"<b>Lookback Period:</b> {lookback_minutes} minutes", body_style))
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("Executive Summary", heading_style))
    summary_data = [
        ["Metric", "Value"],
        ["Total Events Processed", str(summary.total_events_processed)],
        ["Lambda Invocations", str(summary.total_invocations)],
        ["Errors Detected", str(summary.total_errors)],
        ["Error Rate", f"{(summary.total_errors / summary.total_invocations * 100):.2f}%" if summary.total_invocations else "N/A"],
        ["Cold Starts", str(summary.cold_starts)],
        ["Cold Start Rate", f"{(summary.cold_starts / summary.total_invocations * 100):.2f}%" if summary.total_invocations else "N/A"],
        ["Avg Duration (ms)", f"{summary.avg_duration_ms:.2f}" if summary.avg_duration_ms else "N/A"],
        ["Max Duration (ms)", f"{summary.max_duration_ms:.2f}" if summary.max_duration_ms else "N/A"],
        ["P95 Duration (ms)", f"{summary.p95_duration_ms:.2f}" if summary.p95_duration_ms else "N/A"],
        ["P99 Duration (ms)", f"{summary.p99_duration_ms:.2f}" if summary.p99_duration_ms else "N/A"],
        ["Avg Memory Used (MB)", f"{summary.avg_memory_mb:.2f}" if summary.avg_memory_mb else "N/A"],
        ["Max Memory Used (MB)", f"{summary.max_memory_mb:.2f}" if summary.max_memory_mb else "N/A"],
        ["Estimated Cost ($)", f"{summary.estimated_cost:.6f}" if hasattr(summary, 'estimated_cost') and summary.estimated_cost else "N/A"],
    ]

    table = Table(summary_data, colWidths=[3 * inch, 2.5 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


def create_duration_chart(durations: List[float]) -> go.Figure:
    fig = px.histogram(
        x=durations,
        nbins=30,
        title="Invocation Duration Distribution",
        labels={"x": "Duration (ms)", "y": "Count"},
        color_discrete_sequence=["#4ECDC4"],
    )
    fig.update_layout(
        height=400,
        showlegend=False,
        bargap=0.1,
        template="plotly_white",
    )
    fig.add_vline(x=sum(durations)/len(durations), line_dash="dash", line_color="red", annotation_text="Avg")
    return fig


def create_memory_chart(memory: List[float]) -> go.Figure:
    fig = px.histogram(
        x=memory,
        nbins=30,
        title="Memory Usage Distribution",
        labels={"x": "Memory Used (MB)", "y": "Count"},
        color_discrete_sequence=["#FF6B6B"],
    )
    fig.update_layout(
        height=400,
        showlegend=False,
        bargap=0.1,
        template="plotly_white",
    )
    return fig


def create_timeline_chart(parsed_events: List[ParsedEvent]) -> go.Figure:
    df = pd.DataFrame([
        {
            "timestamp": ev.iso_timestamp,
            "duration_ms": ev.duration_ms,
            "memory_mb": ev.max_memory_used_mb,
            "is_cold_start": ev.is_cold_start,
            "event_type": ev.event_type,
        }
        for ev in parsed_events if ev.event_type == "report"
    ])

    if df.empty:
        return None

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["duration_ms"],
        mode="lines+markers",
        name="Duration (ms)",
        line=dict(color="#4ECDC4"),
        marker=dict(size=8, symbol="circle"),
    ))

    cold_starts = df[df["is_cold_start"]]
    if not cold_starts.empty:
        fig.add_trace(go.Scatter(
            x=cold_starts["timestamp"],
            y=cold_starts["duration_ms"],
            mode="markers",
            name="Cold Start",
            marker=dict(size=15, color="#FF6B6B", symbol="star"),
        ))

    fig.update_layout(
        title="Invocation Timeline",
        xaxis_title="Time",
        yaxis_title="Duration (ms)",
        height=400,
        template="plotly_white",
        hovermode="x unified",
    )
    return fig


def create_error_timeline(errors: List[ParsedEvent]) -> go.Figure:
    if not errors:
        return None

    df = pd.DataFrame([
        {
            "timestamp": ev.iso_timestamp,
            "error_type": ev.error_type or "Unknown",
            "log_group": ev.log_group.split("/")[-1],
        }
        for ev in errors
    ])

    df["timestamp"] = pd.to_datetime(df["timestamp"])

    fig = px.scatter(
        df,
        x="timestamp",
        y="error_type",
        color="log_group",
        size=[10] * len(df),
        title="Error Timeline",
        labels={"timestamp": "Time", "error_type": "Error Type", "log_group": "Function"},
    )
    fig.update_layout(height=300, template="plotly_white")
    return fig


def create_cost_gauge(estimated_cost: float, max_cost: float = 0.01) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=estimated_cost,
        number={"prefix": "$", "suffix": "", "valueformat": ".6f"},
        gauge={
            "axis": {"range": [0, max_cost]},
            "bar": {"color": "#4ECDC4"},
            "steps": [
                {"range": [0, max_cost * 0.5], "color": "#90EE90"},
                {"range": [max_cost * 0.5, max_cost * 0.8], "color": "#FFD700"},
                {"range": [max_cost * 0.8, max_cost], "color": "#FF6B6B"},
            ],
        },
        title={"text": "Estimated Cost ($)"},
    ))
    fig.update_layout(height=250)
    return fig


def main():
    init_session_state()

    with st.sidebar:
        st.header("⚙️ Configuration")
        st.divider()

        aws_access_key_id = st.text_input(
            "AWS Access Key ID",
            type="password",
            help="Your AWS access key for programmatic access",
        )
        aws_secret_access_key = st.text_input(
            "AWS Secret Access Key",
            type="password",
            help="Your AWS secret access key",
        )
        aws_region = st.selectbox("AWS Region", AWS_REGIONS, index=7)

        st.divider()
        st.subheader("📋 Analysis Settings")

        log_groups_input = st.text_area(
            "Log Group Names",
            placeholder="/aws/lambda/my-function\n/aws/lambda/another-function",
            help="Enter one log group per line",
            height=100,
        )
        log_groups = [g.strip() for g in log_groups_input.split("\n") if g.strip()]

        lookback_minutes = st.slider(
            "Lookback Period (minutes)",
            min_value=5,
            max_value=1440,
            value=60,
            step=5,
            help="How far back to fetch logs",
        )

        memory_size = st.number_input(
            "Lambda Memory Size (MB)",
            min_value=128,
            max_value=10240,
            value=128,
            step=128,
            help="Set your Lambda function memory size for accurate cost estimation",
        )

        duration_timeout = st.number_input(
            "Lambda Timeout (seconds)",
            min_value=1,
            max_value=900,
            value=30,
            step=1,
            help="Set your Lambda function timeout",
        )

        st.divider()

        can_run = bool(aws_access_key_id and aws_secret_access_key and log_groups)

        st.button(
            "🚀 Run Analysis",
            type="primary",
            use_container_width=True,
            disabled=not can_run,
            on_click=lambda: st.session_state.update({
                "log_groups": log_groups,
                "lookback_minutes": lookback_minutes,
            }) if can_run else None,
        )

    st.title("📊 Lambda Log Analyser Dashboard")
    st.markdown("Comprehensive analysis of AWS Lambda logs with performance metrics, cost estimation, and error tracking.")

    if not (aws_access_key_id and aws_secret_access_key and log_groups):
        st.info("👈 Please configure AWS credentials and log groups in the sidebar to begin analysis.")
        return

    if can_run:
        with st.spinner("Fetching and analyzing logs..."):
            try:
                raw_events, parsed_events, summary = run_analysis(
                    log_groups,
                    lookback_minutes,
                    aws_access_key_id,
                    aws_secret_access_key,
                    aws_region,
                )

                if parsed_events:
                    summary.estimated_cost = calculate_cost(
                        summary.total_invocations,
                        summary.billed_durations_ms,
                        memory_size,
                    )

                st.session_state.update({
                    "analysis_complete": True,
                    "summary": summary,
                    "parsed_events": parsed_events,
                    "raw_events": raw_events,
                    "log_groups": log_groups,
                    "lookback_minutes": lookback_minutes,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                st.success("✅ Analysis complete!")
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                return

    if st.session_state.analysis_complete:
        summary = st.session_state.summary
        parsed_events = st.session_state.parsed_events

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📈 Overview",
            "⏱️ Performance",
            "🚨 Errors",
            "📋 Raw Data",
            "📥 Export"
        ])

        with tab1:
            st.subheader("🎯 Executive Summary")

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric(
                    "Total Events",
                    summary.total_events_processed,
                    delta=f"{summary.total_invocations} invocations",
                )
            with col2:
                st.metric(
                    "Errors",
                    summary.total_errors,
                    delta=f"{(summary.total_errors / summary.total_invocations * 100):.1f}% rate" if summary.total_invocations else "0%",
                    delta_color="inverse" if summary.total_errors > 0 else "off",
                )
            with col3:
                st.metric(
                    "Cold Starts",
                    summary.cold_starts,
                    delta=f"{(summary.cold_starts / summary.total_invocations * 100):.1f}% rate" if summary.total_invocations else "0%",
                )
            with col4:
                st.metric(
                    "Avg Duration",
                    f"{summary.avg_duration_ms:.1f} ms" if summary.avg_duration_ms else "N/A",
                )
            with col5:
                if hasattr(summary, 'estimated_cost'):
                    st.metric(
                        "Est. Cost",
                        f"${summary.estimated_cost:.6f}",
                    )
                else:
                    st.metric(
                        "Avg Memory",
                        f"{summary.avg_memory_mb:.0f} MB" if summary.avg_memory_mb else "N/A",
                    )

            st.divider()

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 📊 Event Distribution")
                event_counts = {}
                for ev in parsed_events:
                    event_counts[ev.event_type] = event_counts.get(ev.event_type, 0) + 1

                fig = px.pie(
                    names=list(event_counts.keys()),
                    values=list(event_counts.values()),
                    hole=0.4,
                    color=list(event_counts.keys()),
                    color_discrete_map={
                        "report": "#4ECDC4",
                        "error": "#FF6B6B",
                        "start": "#95E1D3",
                        "end": "#F38181",
                        "other": "#FCE38A",
                    },
                )
                fig.update_layout(height=350, template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("#### 🌡️ Health Score")
                health_score = calculate_health_score(summary)
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=health_score,
                    number={"suffix": "%"},
                    gauge={
                        "axis": {"range": [0, 100]},
                        "bar": {"color": get_health_color(health_score)},
                        "steps": [
                            {"range": [0, 50], "color": "#FF6B6B"},
                            {"range": [50, 75], "color": "#FFD700"},
                            {"range": [75, 100], "color": "#4ECDC4"},
                        ],
                    },
                ))
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

            st.divider()
            st.markdown("#### 📋 Quick Stats")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.markdown("**Duration Stats**")
                st.write(f"- Min: {min(summary.durations_ms):.2f} ms" if summary.durations_ms else "- No data")
                st.write(f"- Avg: {summary.avg_duration_ms:.2f} ms" if summary.avg_duration_ms else "")
                st.write(f"- Max: {max(summary.durations_ms):.2f} ms" if summary.durations_ms else "")
                st.write(f"- P95: {summary.p95_duration_ms:.2f} ms" if summary.p95_duration_ms else "")
                st.write(f"- P99: {summary.p99_duration_ms:.2f} ms" if hasattr(summary, 'p99_duration_ms') and summary.p99_duration_ms else "- P99: N/A")

            with col2:
                st.markdown("**Memory Stats**")
                st.write(f"- Min: {min(summary.memory_used_mb):.0f} MB" if summary.memory_used_mb else "- No data")
                st.write(f"- Avg: {summary.avg_memory_mb:.0f} MB" if summary.avg_memory_mb else "")
                st.write(f"- Max: {max(summary.memory_used_mb):.0f} MB" if summary.memory_used_mb else "")
                efficiency = summary.memory_efficiency_pct if hasattr(summary, 'memory_efficiency_pct') and summary.memory_efficiency_pct else None
                st.write(f"- Memory Efficiency: {efficiency:.1f}%" if efficiency else "- Efficiency: N/A")

            with col3:
                st.markdown("**Invocation Stats**")
                st.write(f"- Total: {summary.total_invocations}")
                st.write(f"- Cold: {summary.cold_starts}")
                st.write(f"- Warm: {summary.total_invocations - summary.cold_starts}")
                st.write(f"- Timeout Risk: {'⚠️ Yes' if summary.max_duration_ms and summary.max_duration_ms > duration_timeout * 1000 else '✅ No'}")

            with col4:
                st.markdown("**Log Group Breakdown**")
                group_stats = get_group_stats(parsed_events)
                for group, count in sorted(group_stats.items(), key=lambda x: -x[1])[:5]:
                    st.write(f"- {group}: {count}")

        with tab2:
            st.subheader("⏱️ Performance Analysis")

            col1, col2 = st.columns(2)
            with col1:
                if summary.durations_ms:
                    st.plotly_chart(create_duration_chart(summary.durations_ms), use_container_width=True)
                else:
                    st.info("No duration data available")

            with col2:
                if summary.memory_used_mb:
                    st.plotly_chart(create_memory_chart(summary.memory_used_mb), use_container_width=True)
                else:
                    st.info("No memory data available")

            st.divider()

            timeline = create_timeline_chart(parsed_events)
            if timeline:
                st.plotly_chart(timeline, use_container_width=True)
            else:
                st.info("No timeline data available")

            st.divider()
            st.subheader("📊 Advanced Metrics")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.markdown("**Billed Duration**")
                if summary.billed_durations_ms:
                    total_billed = sum(summary.billed_durations_ms)
                    st.write(f"Total: {total_billed:.0f} ms")
                    st.write(f"Avg: {total_billed / len(summary.billed_durations_ms):.2f} ms")
                else:
                    st.write("No billed duration data")

            with col2:
                st.markdown("**Timeout Analysis**")
                if summary.durations_ms and duration_timeout:
                    risky = [d for d in summary.durations_ms if d > duration_timeout * 1000 * 0.8]
                    st.write(f"High Risk (>80%): {len(risky)}")
                    st.write(f"Safe (<80%): {len(summary.durations_ms) - len(risky)}")

            with col3:
                st.markdown("**Cold Start Impact**")
                if summary.cold_starts > 0 and summary.durations_ms:
                    cold_durations = [ev.duration_ms for ev in parsed_events if ev.is_cold_start and ev.duration_ms]
                    warm_durations = [ev.duration_ms for ev in parsed_events if not ev.is_cold_start and ev.duration_ms]
                    if cold_durations and warm_durations:
                        avg_cold = sum(cold_durations) / len(cold_durations)
                        avg_warm = sum(warm_durations) / len(warm_durations)
                        st.write(f"Avg Cold: {avg_cold:.2f} ms")
                        st.write(f"Avg Warm: {avg_warm:.2f} ms")
                        st.write(f"Slowdown: +{avg_cold - avg_warm:.2f} ms")

            with col4:
                st.markdown("**Cost Estimation**")
                if hasattr(summary, 'estimated_cost') and summary.estimated_cost:
                    st.write(f"Per Invocation: ${summary.estimated_cost / max(summary.total_invocations, 1):.6f}")
                    st.write(f"Total: ${summary.estimated_cost:.6f}")

        with tab3:
            st.subheader("🚨 Error Analysis")

            if summary.error_events:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Errors", summary.total_errors)
                with col2:
                    st.metric("Error Rate", f"{(summary.total_errors / summary.total_events_processed * 100):.1f}%")
                with col3:
                    unique_types = len(set(ev.error_type for ev in summary.error_events if ev.error_type))
                    st.metric("Unique Error Types", unique_types)

                st.divider()

                error_timeline = create_error_timeline(summary.error_events)
                if error_timeline:
                    st.plotly_chart(error_timeline, use_container_width=True)

                st.divider()
                st.subheader("📋 Error Details")

                error_df = pd.DataFrame([
                    {
                        "Timestamp": ev.iso_timestamp,
                        "Function": ev.log_group.split("/")[-1],
                        "Error Type": ev.error_type or "Unknown",
                        "Error Message": (ev.error_message or ev.message)[:150] + "..." if len(ev.error_message or ev.message) > 150 else (ev.error_message or ev.message),
                        "Full Message": ev.message,
                    }
                    for ev in summary.error_events
                ])

                st.dataframe(
                    error_df[["Timestamp", "Function", "Error Type", "Error Message"]],
                    use_container_width=True,
                    hide_index=True,
                )

                with st.expander("🔍 View Full Error Messages"):
                    for i, ev in enumerate(summary.error_events, 1):
                        st.markdown(f"**Error {i}** - {ev.iso_timestamp}")
                        st.code(ev.message[:1000] if len(ev.message) > 1000 else ev.message, language=None)
                        st.divider()

            else:
                st.success("✅ No errors detected in the analyzed logs!")
                st.balloons()

            st.divider()
            st.subheader("🔍 Error Pattern Analysis")

            if summary.error_events:
                error_types = {}
                for ev in summary.error_events:
                    etype = ev.error_type or "Unknown"
                    error_types[etype] = error_types.get(etype, 0) + 1

                fig = px.bar(
                    x=list(error_types.keys()),
                    y=list(error_types.values()),
                    color=list(error_types.keys()),
                    title="Error Types Distribution",
                    labels={"x": "Error Type", "y": "Count"},
                )
                fig.update_layout(height=300, showlegend=False, template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)

        with tab4:
            st.subheader("📋 Raw Invocation Data")

            report_events = [ev for ev in parsed_events if ev.event_type == "report"]

            if report_events:
                inv_df = pd.DataFrame([
                    {
                        "Timestamp": ev.iso_timestamp,
                        "Function": ev.log_group.split("/")[-1],
                        "Request ID": ev.request_id or "N/A",
                        "Duration (ms)": round(ev.duration_ms, 2) if ev.duration_ms else 0,
                        "Billed (ms)": round(ev.billed_duration_ms, 2) if ev.billed_duration_ms else 0,
                        "Memory Used (MB)": round(ev.max_memory_used_mb, 2) if ev.max_memory_used_mb else 0,
                        "Init Duration (ms)": round(ev.init_duration_ms, 2) if ev.init_duration_ms else 0,
                        "Cold Start": "❄️ Yes" if ev.is_cold_start else "✅ No",
                    }
                    for ev in report_events
                ])

                st.dataframe(inv_df, use_container_width=True, hide_index=True)

                st.divider()
                st.subheader("📥 Download Data")

                csv = inv_df.to_csv(index=False)
                st.download_button(
                    "📊 Download as CSV",
                    csv,
                    file_name=f"lambda_invocation_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                )

            all_events = [ev for ev in parsed_events if ev.event_type != "report"]
            if all_events:
                st.divider()
                st.subheader("📋 Other Events")

                other_df = pd.DataFrame([
                    {
                        "Timestamp": ev.iso_timestamp,
                        "Function": ev.log_group.split("/")[-1],
                        "Type": ev.event_type.upper(),
                        "Message": ev.message[:100] + "..." if len(ev.message) > 100 else ev.message,
                    }
                    for ev in all_events[:100]
                ])

                st.dataframe(other_df, use_container_width=True, hide_index=True)

        with tab5:
            st.subheader("📥 Export Reports")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### 📄 PDF Report")
                pdf_bytes = generate_pdf(
                    summary,
                    parsed_events,
                    st.session_state.log_groups,
                    st.session_state.lookback_minutes,
                )
                st.download_button(
                    "📥 Download PDF Report",
                    pdf_bytes,
                    file_name=f"lambda_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

            with col2:
                st.markdown("#### 📊 JSON Export")
                import json
                export_data = {
                    "generated_at": st.session_state.timestamp,
                    "log_groups": st.session_state.log_groups,
                    "lookback_minutes": st.session_state.lookback_minutes,
                    "summary": summary.to_dict(),
                    "total_events": len(parsed_events),
                    "parsed_events": [
                        {
                            "timestamp": ev.iso_timestamp,
                            "log_group": ev.log_group,
                            "event_type": ev.event_type,
                            "duration_ms": ev.duration_ms,
                            "is_cold_start": ev.is_cold_start,
                            "error_type": ev.error_type,
                        }
                        for ev in parsed_events
                    ],
                }
                json_str = json.dumps(export_data, indent=2)
                st.download_button(
                    "📥 Download JSON",
                    json_str,
                    file_name=f"lambda_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    use_container_width=True,
                )

            st.divider()
            st.markdown("#### 📝 Analysis Metadata")
            st.json({
                "Analysis Time": st.session_state.timestamp,
                "Log Groups": st.session_state.log_groups,
                "Lookback Period": f"{st.session_state.lookback_minutes} minutes",
                "Region": aws_region,
                "Total Raw Events": len(st.session_state.raw_events),
                "Total Parsed Events": len(parsed_events),
            })


def calculate_cost(invocations: int, billed_durations_ms: List[float], memory_mb: int) -> float:
    if not billed_durations_ms:
        return 0.0

    total_billed_seconds = sum(billed_durations_ms) / 1000.0
    memory_gb = memory_mb / 1024.0

    compute_seconds = total_billed_seconds
    compute_charge = compute_seconds * memory_gb * 0.0000166667
    request_charge = invocations * 0.0000002

    return compute_charge + request_charge


def calculate_health_score(summary: AnalysisSummary) -> float:
    score = 100.0

    if summary.total_invocations > 0:
        error_rate = summary.total_errors / summary.total_events_processed
        score -= error_rate * 50

        cold_start_rate = summary.cold_starts / summary.total_invocations
        score -= cold_start_rate * 10

    if summary.durations_ms:
        p95_threshold = 3000
        if summary.p95_duration_ms and summary.p95_duration_ms > p95_threshold:
            score -= min(20, (summary.p95_duration_ms - p95_threshold) / 100)

    if summary.memory_used_mb and summary.avg_memory_mb:
        efficiency = summary.avg_memory_mb / 1024 * 100
        if efficiency < 50:
            score -= (50 - efficiency) * 0.2

    return max(0, min(100, score))


def get_health_color(score: float) -> str:
    if score >= 75:
        return "#4ECDC4"
    elif score >= 50:
        return "#FFD700"
    else:
        return "#FF6B6B"


def get_group_stats(parsed_events: List[ParsedEvent]) -> dict:
    stats = {}
    for ev in parsed_events:
        group = ev.log_group.split("/")[-1]
        stats[group] = stats.get(group, 0) + 1
    return stats


if __name__ == "__main__":
    main()
