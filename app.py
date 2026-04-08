import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(
    page_title="数据分析工具",
    page_icon="📊",
    layout="wide",
)

st.title("📊 数据获取与分析工具")
st.markdown("本工具从公开数据源获取数据并进行可视化分析。")

# ─────────────────────────────────────────────
# Sidebar – data source & parameters
# ─────────────────────────────────────────────
st.sidebar.header("⚙️ 参数设置")

data_source = st.sidebar.selectbox(
    "选择数据来源",
    ["天气数据（Open-Meteo）", "COVID-19 全球数据", "上传 CSV 文件"],
)

# ─────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def fetch_weather(lat: float, lon: float, days: int) -> pd.DataFrame:
    """Fetch hourly temperature data from the Open-Meteo API (no API key required)."""
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days - 1)
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=temperature_2m,precipitation,windspeed_10m"
        f"&start_date={start_date}&end_date={end_date}"
        "&timezone=auto"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()["hourly"]
    df = pd.DataFrame(data)
    df["time"] = pd.to_datetime(df["time"])
    df.rename(
        columns={
            "temperature_2m": "温度 (°C)",
            "precipitation": "降水量 (mm)",
            "windspeed_10m": "风速 (km/h)",
        },
        inplace=True,
    )
    return df


@st.cache_data(ttl=3600)
def fetch_covid() -> pd.DataFrame:
    """Fetch latest COVID-19 summary data from disease.sh."""
    url = "https://disease.sh/v3/covid-19/countries?sort=cases"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    records = resp.json()
    rows = [
        {
            "国家": r["country"],
            "确诊总数": r["cases"],
            "死亡总数": r["deaths"],
            "康复总数": r["recovered"],
            "活跃病例": r["active"],
            "每百万确诊": r["casesPerOneMillion"],
            "每百万死亡": r["deathsPerOneMillion"],
            "人口": r["population"],
        }
        for r in records
        if r.get("population", 0) > 0
    ]
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
# Weather data section
# ─────────────────────────────────────────────
if data_source == "天气数据（Open-Meteo）":
    st.header("🌤️ 天气数据分析")

    lat = st.sidebar.number_input("纬度", value=39.9042, min_value=-90.0, max_value=90.0, format="%.4f")
    lon = st.sidebar.number_input("经度", value=116.4074, min_value=-180.0, max_value=180.0, format="%.4f")
    days = st.sidebar.slider("历史天数", min_value=1, max_value=7, value=3)

    with st.spinner("正在获取天气数据…"):
        try:
            df = fetch_weather(lat, lon, days)
        except Exception as e:
            st.error(f"数据获取失败：{e}")
            st.stop()

    st.success(f"成功获取 {len(df)} 条记录")

    # ── Summary statistics ──
    st.subheader("📋 统计摘要")
    stats_cols = ["温度 (°C)", "降水量 (mm)", "风速 (km/h)"]
    st.dataframe(df[stats_cols].describe().round(2), use_container_width=True)

    # ── Temperature trend ──
    st.subheader("🌡️ 温度变化趋势")
    fig_temp = px.line(
        df,
        x="time",
        y="温度 (°C)",
        title="逐小时温度",
        labels={"time": "时间"},
        template="plotly_white",
    )
    st.plotly_chart(fig_temp, use_container_width=True)

    # ── Precipitation bar ──
    st.subheader("🌧️ 降水量")
    daily = df.copy()
    daily["日期"] = daily["time"].dt.date
    daily_precip = daily.groupby("日期")["降水量 (mm)"].sum().reset_index()
    fig_precip = px.bar(
        daily_precip,
        x="日期",
        y="降水量 (mm)",
        title="每日总降水量",
        template="plotly_white",
    )
    st.plotly_chart(fig_precip, use_container_width=True)

    # ── Wind speed distribution ──
    st.subheader("💨 风速分布")
    fig_wind = px.histogram(
        df,
        x="风速 (km/h)",
        nbins=30,
        title="风速频率分布",
        template="plotly_white",
    )
    st.plotly_chart(fig_wind, use_container_width=True)

    # ── Raw data ──
    with st.expander("查看原始数据"):
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 下载 CSV", csv, "weather_data.csv", "text/csv")

# ─────────────────────────────────────────────
# COVID-19 section
# ─────────────────────────────────────────────
elif data_source == "COVID-19 全球数据":
    st.header("🦠 COVID-19 全球数据分析")

    top_n = st.sidebar.slider("显示国家数量（按确诊降序）", 10, 50, 20)

    with st.spinner("正在获取 COVID-19 数据…"):
        try:
            df = fetch_covid()
        except Exception as e:
            st.error(f"数据获取失败：{e}")
            st.stop()

    st.success(f"共获取 {len(df)} 个国家/地区的数据")

    df_top = df.head(top_n)

    # ── Bar: total cases ──
    st.subheader(f"📊 确诊总数 Top {top_n}")
    fig_bar = px.bar(
        df_top,
        x="确诊总数",
        y="国家",
        orientation="h",
        title=f"确诊总数 Top {top_n} 国家",
        template="plotly_white",
        color="确诊总数",
        color_continuous_scale="Reds",
    )
    fig_bar.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig_bar, use_container_width=True)

    # ── Scatter: cases vs deaths ──
    st.subheader("🔍 确诊 vs 死亡（每百万人口）")
    fig_scatter = px.scatter(
        df,
        x="每百万确诊",
        y="每百万死亡",
        hover_name="国家",
        size="人口",
        size_max=50,
        log_x=True,
        log_y=True,
        title="确诊率 vs 死亡率（对数坐标）",
        template="plotly_white",
        color="每百万死亡",
        color_continuous_scale="Oranges",
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    # ── Pie: active / recovered / deaths ──
    st.subheader("🥧 全球病例状态分布（Top 国家之和）")
    totals = df_top[["活跃病例", "康复总数", "死亡总数"]].sum()
    fig_pie = go.Figure(
        go.Pie(
            labels=totals.index.tolist(),
            values=totals.values.tolist(),
            hole=0.4,
        )
    )
    fig_pie.update_layout(title_text=f"Top {top_n} 国家病例状态分布")
    st.plotly_chart(fig_pie, use_container_width=True)

    # ── Raw data ──
    with st.expander("查看原始数据"):
        st.dataframe(df, use_container_width=True)
        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 下载 CSV", csv, "covid_data.csv", "text/csv")

# ─────────────────────────────────────────────
# Upload CSV section
# ─────────────────────────────────────────────
else:
    st.header("📂 上传 CSV 文件进行分析")

    uploaded = st.file_uploader("选择 CSV 文件", type=["csv"])
    if uploaded is None:
        st.info("请上传一个 CSV 文件以开始分析。")
        st.stop()

    try:
        df = pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"文件读取失败：{e}")
        st.stop()

    st.success(f"文件加载成功：{df.shape[0]} 行 × {df.shape[1]} 列")

    # ── Data preview ──
    st.subheader("🔍 数据预览")
    st.dataframe(df.head(20), use_container_width=True)

    # ── Statistics ──
    st.subheader("📋 统计摘要")
    numeric_df = df.select_dtypes(include="number")
    if numeric_df.empty:
        st.warning("未检测到数值列，无法生成统计摘要。")
    else:
        st.dataframe(numeric_df.describe().round(4), use_container_width=True)

        # ── Correlation heatmap ──
        if len(numeric_df.columns) >= 2:
            st.subheader("🔗 相关性热力图")
            corr = numeric_df.corr()
            fig_heat = px.imshow(
                corr,
                text_auto=True,
                color_continuous_scale="RdBu_r",
                title="数值列相关性矩阵",
                template="plotly_white",
            )
            st.plotly_chart(fig_heat, use_container_width=True)

        # ── Column chart ──
        st.subheader("📈 数值列可视化")
        col_x = st.selectbox("X 轴", options=df.columns.tolist(), index=0)
        col_y = st.selectbox(
            "Y 轴",
            options=numeric_df.columns.tolist(),
            index=0 if len(numeric_df.columns) == 1 else 1,
        )
        chart_type = st.radio("图表类型", ["折线图", "柱状图", "散点图"], horizontal=True)

        if chart_type == "折线图":
            fig = px.line(df, x=col_x, y=col_y, template="plotly_white")
        elif chart_type == "柱状图":
            fig = px.bar(df, x=col_x, y=col_y, template="plotly_white")
        else:
            fig = px.scatter(df, x=col_x, y=col_y, template="plotly_white")

        st.plotly_chart(fig, use_container_width=True)

    # ── Download cleaned data ──
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("⬇️ 下载 CSV", csv, "analyzed_data.csv", "text/csv")
