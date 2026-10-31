"""LogPulse – Streamlit Analytics Dashboard."""

import os
from pathlib import Path
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st

from src.analytics.metrics import AnalyticsEngine
from src.loader.db_loader import DBLoader
from src.pipeline.orchestrator import PipelineOrchestrator
from src.utils.db_utils import get_connection, get_db_path

st.set_page_config(
    page_title="LogPulse – Log Analytics Pipeline",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom header styling
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0px;
    }
    .sub-title {
        color: #6B7280;
        font-size: 1.05rem;
        margin-bottom: 25px;
    }
    .metric-card {
        background-color: #F8FAFC;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #E2E8F0;
    }
    /* Hide Streamlit default Deploy button and menu */
    .stAppDeployButton, [data-testid="stAppDeployButton"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_engine():
    db_path = get_db_path()
    return AnalyticsEngine(db_path)


def bootstrap_database(db_path: str = None) -> bool:
    """Ensure database schema exists and automatically seed sample data if empty.

    Safe for public cloud deployments (e.g. Streamlit Cloud) where db/logpulse.db
    is excluded from Git. Preserves existing non-empty database records.

    Returns:
        True if sample data was newly ingested, False otherwise.
    """
    if db_path is None:
        db_path = get_db_path()

    try:
        loader = DBLoader(db_path)
        loader.init_db()

        with get_connection(db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM log_events").fetchone()
            count = row[0] if row else 0

        # Only bootstrap if log_events has zero records
        if count == 0:
            sample_dir = PROJECT_ROOT / "data" / "sample"
            if sample_dir.exists():
                orchestrator = PipelineOrchestrator(db_path=db_path)
                sample_files = orchestrator.discover_files(raw_dir=str(sample_dir))
                if sample_files:
                    orchestrator.run(raw_dir=str(sample_dir))
                    return True
        return False
    except Exception as e:
        st.warning(f"Database bootstrap warning: {e}")
        return False


def main():
    st.markdown('<div class="main-title">⚡ LogPulse</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-title">Application Log Analytics & Pipeline Performance Monitoring</div>',
        unsafe_allow_html=True,
    )

    engine = load_engine()
    bootstrapped = bootstrap_database(engine.db_path)

    # Sidebar
    st.sidebar.title("Pipeline Controls")
    st.sidebar.info(f"📁 Database: `{os.path.basename(engine.db_path)}`")
    if bootstrapped:
        st.sidebar.success("⚡ Demo sample data automatically initialized!")
    if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
        st.rerun()

    # Retrieve overall metrics
    try:
        summary = engine.get_overall_summary()
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        st.info("Have you run the pipeline yet? Use `python -m src.pipeline.orchestrator` to ingest logs.")
        return

    # Top KPI Metrics Row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Logs Loaded", f"{summary['total_logs']:,}")
    with col2:
        st.metric("Total Errors", f"{summary['error_count']:,}")
    with col3:
        st.metric("Error Rate", f"{summary['error_rate_pct']}%")
    with col4:
        st.metric("Avg Latency", f"{summary['avg_latency_ms']} ms")
    with col5:
        st.metric("Quarantined", f"{summary['quarantined_count']:,}")

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Volume & Trends",
        "🛠️ Service Analytics",
        "⏱️ Latency Profiling",
        "🛡️ Quarantine Inspector",
        "🚀 Pipeline Execution Runs",
    ])

    # TAB 1: Trends
    with tab1:
        st.subheader("Log Volume & Error Trends Over Time")
        freq = st.selectbox("Aggregation Interval", ["1h", "30min", "15min"], index=0)
        df_vol = engine.get_volume_timeline(freq=freq)
        if not df_vol.empty and len(df_vol) > 0:
            df_chart = df_vol.copy()
            df_chart["dt"] = pd.to_datetime(df_chart["dt"])
            df_chart = df_chart.set_index("dt")

            st.line_chart(df_chart[["total", "errors"]])
            st.caption("Total Ingested Log Events vs. Error/Critical Events")
        else:
            st.info("No timeline data available.")

        st.subheader("Severity Distribution")
        df_sev = engine.get_severity_distribution()
        if not df_sev.empty:
            c1, c2 = st.columns([1, 1])
            with c1:
                st.dataframe(df_sev, use_container_width=True, hide_index=True)
            with c2:
                st.bar_chart(df_sev.set_index("severity")["count"])

    # TAB 2: Services
    with tab2:
        st.subheader("Error Rates by Service")
        df_service = engine.get_error_rates_by_service()
        if not df_service.empty:
            c1, c2 = st.columns([1, 1])
            with c1:
                st.dataframe(df_service, use_container_width=True, hide_index=True)
            with c2:
                st.bar_chart(df_service.set_index("service")["error_rate_pct"])

            st.subheader("Top Error Messages")
            df_top_errors = engine.get_top_error_messages(limit=10)
            st.dataframe(df_top_errors, use_container_width=True, hide_index=True)
        else:
            st.info("No service analytics data available.")

    # TAB 3: Latency
    with tab3:
        st.subheader("Service Latency Distribution (ms)")
        df_lat = engine.get_latency_by_service()
        if not df_lat.empty:
            st.dataframe(df_lat, use_container_width=True, hide_index=True)
            st.caption("P50, P95, and P99 latency percentiles calculated per service.")
            st.bar_chart(df_lat.set_index("service")[["p50_ms", "p95_ms", "p99_ms"]])
        else:
            st.info("No latency metrics recorded.")

    # TAB 4: Quarantine
    with tab4:
        st.subheader("Invalid Record Quarantine Summary")
        df_quar = engine.get_quarantine_reasons()
        if not df_quar.empty:
            c1, c2 = st.columns([1, 1])
            with c1:
                st.dataframe(df_quar, use_container_width=True, hide_index=True)
            with c2:
                st.bar_chart(df_quar.set_index("rejection_reason")["count"])

            st.subheader("Recent Quarantined Records")
            from src.utils.db_utils import get_connection
            with get_connection(engine.db_path) as conn:
                sample_quar = pd.read_sql_query(
                    "SELECT id, raw_line, rejection_reason, source_file, created_at FROM quarantine ORDER BY id DESC LIMIT 50",
                    conn,
                )
            st.dataframe(sample_quar, use_container_width=True, hide_index=True)
        else:
            st.success("🎉 No records currently in quarantine!")

    # TAB 5: Pipeline Runs
    with tab5:
        st.subheader("Pipeline Execution Runs History")
        df_runs = engine.get_pipeline_runs_history()
        if not df_runs.empty:
            st.dataframe(df_runs, use_container_width=True, hide_index=True)
        else:
            st.info("No pipeline runs recorded yet.")


if __name__ == "__main__":
    main()
