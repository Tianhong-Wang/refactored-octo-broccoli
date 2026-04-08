import os
import sys

# ================= 0. 强效解决 Windows 编码问题 =================
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
# 注：已移除写死的 VPN 代理设置，以保证代码在不同电脑上的可移植性。
# 运行前请确保电脑已开启全局/系统代理。

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import requests
from collections import Counter
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

API_BASE_URL = os.getenv("SJTU_API_BASE_URL", "https://models.sjtu.edu.cn/api/v1").strip()
API_KEY = os.getenv("SJTU_API_KEY", "").strip()

if not API_KEY:
    st.error("请先配置 SJTU_API_KEY")
    st.stop()

client = OpenAI(
    api_key=API_KEY,
    base_url=API_BASE_URL,
)

# ================= 2. 网页基础设置与状态管理 =================
st.set_page_config(page_title="DataBiz | 品牌营销商业化洞察", page_icon="📈", layout="wide")

if 'df' not in st.session_state:
    try:
        st.session_state.df = pd.read_excel("SocialBeta精准抓取数据.xlsx")
    except FileNotFoundError:
        st.session_state.df = pd.DataFrame()


# ================= 3. 核心功能：时间解析引擎 (NA版) =================
def parse_relative_time(time_str):
    now = datetime.now()
    if not time_str or time_str == "未知时间": return None
    try:
        if "分钟前" in time_str:
            mins = int(re.search(r'\d+', time_str).group())
            return (now - timedelta(minutes=mins)).date()
        elif "小时前" in time_str:
            hours = int(re.search(r'\d+', time_str).group())
            return (now - timedelta(hours=hours)).date()
        elif "天前" in time_str:
            days = int(re.search(r'\d+', time_str).group())
            return (now - timedelta(days=days)).date()
        elif "昨天" in time_str:
            return (now - timedelta(days=1)).date()
        elif "前天" in time_str:
            return (now - timedelta(days=2)).date()
        elif "-" in time_str:
            date_part = time_str.split()[0]
            parts = date_part.split('-')
            if len(parts) == 3:
                return datetime(int(parts[0]), int(parts[1]), int(parts[2])).date()
            elif len(parts) == 2:
                return datetime(now.year, int(parts[0]), int(parts[1])).date()
    except Exception:
        pass
    return None


# ================= 4. 核心功能：批量爬虫 (包含品牌类型与标签拆分) =================
def fetch_latest_events(pages=3):
    base_url = "https://socialbeta.com"
    headers = {"User-Agent": "Mozilla/5.0", "X-Requested-With": "XMLHttpRequest"}
    articles_data = []

    for page in range(1, pages + 1):
        url = "https://socialbeta.com/" if page == 1 else f"https://socialbeta.com/get/home?page={page}&date={int(time.time())}"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, "html.parser")
            article_boxes = soup.find_all('div', class_='con')
            if not article_boxes: break

            for box in article_boxes:
                brand_type_node = box.find('div', class_='brand')
                brand_type = brand_type_node.get_text(strip=True) if brand_type_node else "未分类"

                tit_tag = box.find('div', class_='tit')
                if not tit_tag or not tit_tag.find('a'): continue
                title = tit_tag.find('a').get_text(strip=True)
                link = urljoin(base_url, tit_tag.find('a').get('href'))

                meta_tag = box.find('div', class_='meta')
                summary = meta_tag.get_text(strip=True) if meta_tag else ""

                date_tag = box.find('div', class_='date')
                raw_time = date_tag.get_text(strip=True) if date_tag else ""
                parsed_date = parse_relative_time(raw_time)

                brand_list, tag_list = [], []
                tag_div = box.find('div', class_='tag')
                if tag_div:
                    for a in tag_div.find_all('a'):
                        href, text = a.get('href', ''), a.get_text(strip=True)
                        if '/brand/' in href:
                            brand_list.append(text)
                        else:
                            tag_list.append(text)

                articles_data.append({
                    "文章标题": title, "一句话简介": summary, "发布日期": parsed_date,
                    "品牌类型": brand_type,
                    "涉及品牌": "、".join(brand_list) if brand_list else "通用/未知",
                    "营销标签": "、".join(tag_list) if tag_list else "无",
                    "文章详情页链接": link
                })
        except Exception as e:
            st.error(f"抓取第 {page} 页失败: {e}")
            break
        time.sleep(1)

    df = pd.DataFrame(articles_data)
    if not df.empty:
        df = df.drop_duplicates(subset=['文章详情页链接'])
        df.to_excel("SocialBeta精准抓取数据.xlsx", index=False)
        st.session_state.df = df
    return len(df)


# ================= 5. 详情页抓取与 AI 报告 (定制化 Prompt) =================
@st.cache_data(show_spinner=False, ttl=3600)
def fetch_article_detail(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=8)
        res.encoding = "utf-8"
        soup = BeautifulSoup(res.text, "html.parser")
        content = "\n".join([p.get_text(strip=True) for p in soup.find_all('p')])
        content = re.sub(r"\s+", " ", content).strip()
        return content[:500]
    except Exception:
        return "详情抓取失败。"

def fetch_details_parallel(selected_df, max_workers=5):
    detail_map = {}
    total = len(selected_df)

    progress_bar = st.progress(0, text="🕸️ 正在抓取文章详情...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(fetch_article_detail, row['文章详情页链接']): idx
            for idx, row in selected_df.iterrows()
        }

        finished = 0
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                detail_map[idx] = future.result()
            except Exception:
                detail_map[idx] = "详情抓取失败。"

            finished += 1
            progress_bar.progress(finished / total, text=f"🕸️ 正在抓取文章详情... ({finished}/{total})")

    progress_bar.empty()
    return detail_map
@st.cache_data(show_spinner=False, ttl=24 * 3600)
def summarize_one_case_for_report(title, brand_type, summary, brands, tags, detail):
    """
    分层摘要：先把每篇文章压缩成高密度要点，减少最终汇总输入长度，从而显著加速模型推理（B阶段）。
    结果会按入参缓存，重复生成研报会更快。
    """
    sys_instruct = "你是资深商业数据分析师。请把营销案例压缩成高密度要点，避免空话套话。"
    prompt = f"""
请将下面案例压缩成结构化要点（中文），控制在 120-180 字：
- 具体营销动作/机制是什么（必须具体）
- 可能的目标人群/场景
- 可量化指标/数据机会（1-2条，尽量可落地）

案例信息：
标题：{title}
品牌类型：{brand_type}
简介：{summary}
品牌：{brands}
标签：{tags}
正文节选：{detail}
"""
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": sys_instruct},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()

def generate_ai_report(selected_df, use_layered_summary=True):
    # 并发抓取正文
    detail_map = fetch_details_parallel(selected_df, max_workers=min(12, max(4, len(selected_df))))

    my_bar = st.progress(0, text="🧠 正在整理分析材料...")
    total = len(selected_df)

    # 这里不再直接把长文本拼给最终汇总，而是先压缩成短摘要
    case_summaries = []

    for i, (idx, row) in enumerate(selected_df.iterrows()):
        my_bar.progress((i + 1) / total, text=f"🧠 正在整理分析材料... ({i+1}/{total})")

        detail = detail_map.get(idx, "详情抓取失败。")

        if use_layered_summary:
            summary_text = summarize_one_case_for_report(
                title=row.get("文章标题", ""),
                brand_type=row.get("品牌类型", ""),
                summary=row.get("一句话简介", ""),
                brands=row.get("涉及品牌", ""),
                tags=row.get("营销标签", ""),
                detail=detail,
            )
        else:
            # 保底：不用分层摘要就保持原信息块（会慢很多）
            summary_text = f"""标题：{row.get('文章标题','')}
品牌类型：{row.get('品牌类型','')}
简介：{row.get('一句话简介','')}
品牌：{row.get('涉及品牌','')}
标签：{row.get('营销标签','')}
正文节选：{detail}"""

        case_summaries.append(f"【案例{i+1}】\n{summary_text}\n---")

    my_bar.empty()

    combined_text = "\n".join(case_summaries)

    sys_instruct = """你是一位拥有10年经验的顶级商业数据分析师和 4A 广告公司策略总监。
你的任务是根据提供的【深度文章正文及数据】，敏锐嗅出背后的商业价值，产出能卖给客户的数据服务解决方案。
语言风格：极其专业、克制、直击痛点，多用行业黑话（如 ROI、LBS、AIGC、全渠道、人群画像等）。客观总结，不对AIGC等行业有特别偏好。
必须基于全部案例进行综合分析，不能只围绕单一案例展开。"""

    prompt = f"""
请仔细阅读以下多个【品牌营销深度详情】案例数据。
你必须基于全部案例进行综合分析，不能只围绕单一案例展开。
在“重点品牌案例与商业化机会分析”部分，请优先选择不同品牌、不同营销动作的案例，避免连续使用同一品牌或明显只参考第一条案例。

{combined_text}

请严格按照以下 Markdown 排版格式输出报告（不要多加废话，直接输出报告正文）：

### 1. 核心营销趋势洞察
综合全部案例，提炼出核心营销趋势，这也是我们数据服务需要重点布局的方向：
* **趋势一：[高度概括的趋势名称]** [深入分析该趋势]。**数据机会在于：[指出具体的数据挖掘或分析机会]**。
* **趋势二：[高度概括的趋势名称]** [深入分析该趋势]。**数据机会在于：[指出具体的数据挖掘或分析机会]**。
* **趋势X：[高度概括的趋势名称]** [深入分析该趋势]。**数据机会在于：[指出具体的数据挖掘或分析机会]**。

### 2. 重点品牌案例与商业化机会分析
(请从全部案例中挑选最具代表性的 3 个真实案例，优先选择不同品牌或不同营销动作，按以下格式输出)
#### [真实的品牌名] - [具体的营销动作]
* **事件亮点**：[一句话总结]
* **数据服务切入点**：
    * **[切入点1名称，如 LBS人群画像]**：[详细说明我们（QuestMobile）能为该品牌提供什么数据服务]
    * **[切入点2名称，如 跨媒介重定向]**：[详细说明]

### 3. 行业通用数据解决方案建议
基于近期的营销动态，建议我司（QuestMobile）产品和销售团队重点向快消、美妆、3C数码、汽车、家电等行业主推以下两套标准化的数据服务产品：

#### 解决方案一：【[高大上的系统/产品名称，如 AI与社媒互动效能评估系统]】
* **针对痛点**：[描述品牌目前面临的普遍痛点]
* **产品内容**：
    1.  **[核心功能1]**：[具体描述]
    2.  **[核心功能2]**：[具体描述]
    3.  **[核心功能3]**：[具体描述]
* **目标客户**：[根据数据内容，列举3-4个具体品牌]

#### 解决方案二：【[高大上的系统/产品名称，如 全域场景营销精准追踪包]】
* **针对痛点**：[描述品牌目前面临的普遍痛点]
* **产品内容**：
    1.  **[核心功能1]**：[具体描述]
    2.  **[核心功能2]**：[具体描述]
* **目标客户**：[根据数据内容，列举3-4个具体品牌]

补充要求：
1. 先综合所有案例再总结趋势，不要只复述第一条案例。
2. 输出的 3 个重点案例，尽量来自不同品牌。
3. 如果多个案例相似，优先选择信息差异更大的案例。
4. 不要把第一条案例当作全文主线。
"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": sys_instruct},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"生成失败：{e}"
# ================= 6. 搭建可视化看板功能 =================
def show_news_charts(df):
    news_df = df[df['品牌类型'] == '快讯']
    if news_df.empty:
        st.warning("⚡ 选中的文章中没有‘快讯’类型，无法生成图表。")
        return

    st.markdown("#### ⚡ 选中“快讯”类分析看板")

    all_brands = []
    for b in news_df['涉及品牌']:
        if pd.notna(b) and b != "通用/未知":
            all_brands.extend([x.strip() for x in str(b).split('、') if x.strip()])

    all_tags = []
    for t in news_df['营销标签']:
        if pd.notna(t) and t != "无":
            all_tags.extend([x.strip() for x in str(t).split('、') if x.strip()])

    brand_counts = Counter(all_brands).most_common(10)
    tag_counts = Counter(all_tags).most_common(10)

    # 再显式按次数降序，避免显示顺序不稳定
    b_df = pd.DataFrame(brand_counts, columns=['品牌', '次数']).sort_values(by='次数', ascending=False)
    t_df = pd.DataFrame(tag_counts, columns=['标签', '次数']).sort_values(by='次数', ascending=False)

    # 1. 自动输出“本周趋势一句话总结”
    trend_parts = []
    if not b_df.empty:
        trend_parts.append("品牌关注度最高的是 " + "、".join(b_df['品牌'].head(3).tolist()))
    if not t_df.empty:
        trend_parts.append("高频营销玩法是 " + "、".join(t_df['标签'].head(3).tolist()))

    if trend_parts:
        st.info("本周趋势一句话总结：" + "；".join(trend_parts) + "。")

    col1, col2 = st.columns(2)

    with col1:
        st.caption("品牌出现频率 (TOP 10，降序)")
        if not b_df.empty:
            st.bar_chart(b_df.set_index('品牌'))
            st.dataframe(b_df, hide_index=True, width="stretch")
        else:
            st.write("无品牌数据")

    with col2:
        st.caption("营销标签频率 (TOP 10，降序)")
        if not t_df.empty:
            st.bar_chart(t_df.set_index('标签'))
            st.dataframe(t_df, hide_index=True, width="stretch")
        else:
            st.write("无标签数据")


# ================= 7. 主界面 UI =================
st.title("📈 DataBiz | 品牌营销商业化洞察")

with st.sidebar:
    st.header("⚙️ 抓取配置")
    scrape_pages = st.number_input("批量抓取页数", min_value=1, value=3)
    if st.button("🔄 执行采集", type="primary", width="stretch"):
        fetch_latest_events(pages=scrape_pages)
        st.rerun()

    st.markdown("---")
    if not st.session_state.df.empty:
        valid_dates = pd.to_datetime(st.session_state.df['发布日期']).dropna().dt.date
        if not valid_dates.empty:
            date_range = st.date_input("分析日期筛选", value=(valid_dates.min(), valid_dates.max()))
        else:
            date_range = []
    else:
        date_range = []

if not st.session_state.df.empty:
    if len(date_range) == 2:
        start, end = date_range
        mask = (pd.to_datetime(st.session_state.df['发布日期']).dt.date >= start) & (
                    pd.to_datetime(st.session_state.df['发布日期']).dt.date <= end)
        filtered_df = st.session_state.df.loc[mask].copy()
    else:
        filtered_df = st.session_state.df.copy()

    col_left, col_right = st.columns([2.2, 1.8])

    with col_left:
        st.markdown(f"### 📋 1. 选择分析对象 (共 {len(filtered_df)} 条)")
        select_all = st.checkbox("☑️ 全选当前筛选文章", value=False)

        df_display = filtered_df[['文章标题', '发布日期', '品牌类型', '涉及品牌', '营销标签', '文章详情页链接']].copy()

        df_display.insert(0, '☑️ 选中', select_all)
        df_display['查看原文'] = df_display['文章详情页链接']

        df_display = df_display[['☑️ 选中', '文章标题', '发布日期', '品牌类型', '涉及品牌', '营销标签', '查看原文']]

        edited_df = st.data_editor(
            df_display,
            hide_index=True,
            width="stretch",
            height=450,
            column_config={
                "☑️ 选中": st.column_config.CheckboxColumn(required=True),
                "查看原文": st.column_config.LinkColumn(
                    "查看原文",
                    help="点击跳转到原文",
                    display_text="打开"
                ),
            },
            disabled=['文章标题', '发布日期', '品牌类型', '涉及品牌', '营销标签', '查看原文']
        )

        selected_df = filtered_df[edited_df['☑️ 选中']]

        if not selected_df.empty:
            st.markdown("---")
            show_news_charts(selected_df)

    with col_right:
         st.markdown("### 🧠 2. 商业洞察报告")
            
          max_cases = st.number_input("研报最多使用案例数（越大越慢）", min_value=3, max_value=50, value=20, step=1)
         use_layered_summary = st.checkbox("启用分层摘要（推荐：更快更稳）", value=True)
            
        if st.button("📄 生成洞察研报", width="stretch", type="primary"):
            if selected_df.empty:
                st.error("请先勾选文章！")
            else:
                selected_for_report = selected_df.head(int(max_cases))
                with st.spinner("AI 正在推演中..."):
                    report = generate_ai_report(selected_for_report, use_layered_summary=use_layered_summary)
                    st.markdown(report)
else:
    st.info("👈 请先在左侧采集数据。")
