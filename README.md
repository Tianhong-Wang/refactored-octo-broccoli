# 📊 数据获取与分析工具

一个基于 **Streamlit** 的 Python 数据分析 Web 应用，可在浏览器中直接使用，无需任何编程基础。

## ✨ 功能

| 数据来源 | 说明 |
|---|---|
| 🌤️ 天气数据（Open-Meteo） | 输入经纬度，获取最近 1-7 天逐小时温度、降水量、风速并可视化 |
| 🦠 COVID-19 全球数据 | 实时获取全球各国确诊/死亡/康复数据，生成排行榜与散点图 |
| 📂 上传 CSV 文件 | 上传本地 CSV，自动生成统计摘要、相关性热力图与自定义图表 |

## 🚀 本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/Tianhong-Wang/refactored-octo-broccoli.git
cd refactored-octo-broccoli

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动应用
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。

## ☁️ 线上部署（Streamlit Community Cloud）

1. 前往 [share.streamlit.io](https://share.streamlit.io) 并使用 GitHub 账号登录。
2. 点击 **"New app"**，选择本仓库（`Tianhong-Wang/refactored-octo-broccoli`）。
3. 主文件填写 `app.py`，点击 **Deploy**。
4. 几分钟后即可获得公开可访问的 URL，分享给任何人使用。

## 🛠️ 依赖

- [Streamlit](https://streamlit.io/) — Web 框架
- [Pandas](https://pandas.pydata.org/) — 数据处理
- [Plotly](https://plotly.com/python/) — 交互式图表
- [Requests](https://requests.readthedocs.io/) — HTTP 数据获取