import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials

# 頁面基本設定
st.set_page_config(
    page_title="個人健康與就醫歷程", page_icon="🩺", layout="centered"
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# 載入雲端試算表資料
def load_data():
  try:
    if "gcp_service_account" in st.secrets:
      creds = Credentials.from_service_account_info(
          st.secrets["gcp_service_account"], scopes=SCOPES
      )
    else:
      creds = Credentials.from_service_account_file(
          "credentials.json", scopes=SCOPES
      )

    client = gspread.authorize(creds)
    sheet = client.open("我的健康與就醫紀錄").worksheet("驗血數據")
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    if not df.empty and "日期" in df.columns:
      df["日期"] = pd.to_datetime(df["日期"], format="mixed", errors="coerce")
      df = df.sort_values("日期", ascending=False)
    return sheet, df
  except Exception as e:
    st.error(f"讀取資料失敗：{e}")
    return None, pd.DataFrame()


sheet, df = load_data()

st.title("🩺 健康與就醫歷程")

tab1, tab2, tab3 = st.tabs(["📊 數據趨勢", "📋 完整歷程", "➕ 新增紀錄"])

# Tab 1: 驗血數據趨勢圖
with tab1:
  st.header("驗血數據趨勢")
  if not df.empty:
    blood_df = df[df["類別"] == "驗血"].copy()
    event_df = df[df["類別"] != "驗血"].sort_values("日期").copy()

    if not blood_df.empty:
      blood_df["數值"] = pd.to_numeric(blood_df["數值"], errors="coerce")
      items = blood_df["項目"].dropna().unique()

      selected_item = st.selectbox("選擇要檢視的血液指標", items)

      item_df = blood_df[blood_df["項目"] == selected_item].sort_values(
          "日期"
      )

      if not item_df.empty:
        fig = go.Figure()

        # -------------------------------------------------------------
        # 🎨 顏色設定區：在這裡自由替換你想要的顏色！
        # -------------------------------------------------------------
        CHEMO_COLOR = "#8A2BE2"  # 化療垂直虛線顏色 (例如紫羅蘭色 #8A2BE2)

        category_colors = {
            "看診": "#1F77B4",  # 藍色
            "用藥": "#2CA02C",  # 綠色
            "其他": "#FF7F0E",  # 橘色
        }

        # 1. 繪製驗血數據折線
        fig.add_trace(
            go.Scatter(
                x=item_df["日期"],
                y=item_df["數值"],
                mode="lines+markers+text",
                name=selected_item,
                text=item_df["數值"],
                textposition="top center",
                hovertemplate=(
                    "<b>日期</b>: %{x}<br>"
                    "<b>數值</b>: %{y}<br>"
                    "<b>單位</b>: %{customdata[0]}<br>"
                    "<b>參考範圍</b>: %{customdata[1]}<br>"
                    "<b>醫院診所</b>: %{customdata[2]}<br>"
                    "<b>備註</b>: %{customdata[3]}<extra></extra>"
                ),
                customdata=item_df[
                    ["單位", "參考範圍", "醫院診所", "備註"]
                ].values,
            )
        )

        # 2. 🏥 入院到出院背景淡色區塊
        if not event_df.empty:
          admit_records = event_df[
              event_df["項目"].str.contains("入院", na=False)
          ]
          discharge_records = event_df[
              event_df["項目"].str.contains("出院", na=False)
          ]

          for _, admit in admit_records.iterrows():
            admit_date = admit["日期"]
            matching_discharge = discharge_records[
                discharge_records["日期"] >= admit_date
            ]
            discharge_date = (
                matching_discharge.iloc[0]["日期"]
                if not matching_discharge.empty
                else admit_date + pd.Timedelta(days=5)
            )

            fig.add_vrect(
                x0=admit_date,
                x1=discharge_date,
                fillcolor="lightcoral",
                opacity=0.15,
                layer="below",
                line_width=0,
            )

        # 3. 🟣 化療事件：使用 add_vline 畫出穩定可靠的垂直虛線
        if not event_df.empty:
          chemo_df = event_df[event_df["類別"] == "化療"]
          other_events_df = event_df[event_df["類別"] != "化療"]

          # 畫出化療垂直虛線
          for _, chemo in chemo_df.iterrows():
            c_date = chemo["日期"]
            fig.add_vline(
                x=c_date, line_width=2, line_dash="dash", line_color=CHEMO_COLOR
            )

          # 為了讓圖例 (Legend) 出現化療選項，我們加一個隱藏或圖例專用的點
          if not chemo_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=[chemo_df.iloc[0]["日期"]],
                    y=[item_df["數值"].iloc[0]],
                    mode="markers",
                    name="🟣 化療紀錄",
                    marker=dict(size=0, color=CHEMO_COLOR),  # 點設為透明
                    hoverinfo="skip",
                )
            )

          # 4. 其他事件（看診/用藥/其他）：互動圖示呈現
          category_icons = {
              "看診": "🔵 看診紀錄",
              "用藥": "🟢 用藥紀錄",
              "其他": "🚩 特殊事件",
          }

          y_mid = (
              item_df["數值"].min() + item_df["數值"].max()
          ) / 2 if len(item_df) > 0 else 0

          for cat, group in other_events_df.groupby("類別"):
            name_label = category_icons.get(cat, f"📌 {cat}")
            color = category_colors.get(cat, "gray")

            fig.add_trace(
                go.Scatter(
                    x=group["日期"],
                    y=[y_mid] * len(group),
                    mode="markers",
                    name=name_label,
                    marker=dict(size=12, symbol="diamond", color=color),
                    hovertemplate=(
                        "<b>【%{customdata[0]}】</b><br>"
                        "<b>日期</b>: %{x}<br>"
                        "<b>項目</b>: %{customdata[1]}<br>"
                        "<b>醫院/診所</b>: %{customdata[2]}<br>"
                        "<b>備註</b>: %{customdata[3]}<extra></extra>"
                    ),
                    customdata=group[
                        ["類別", "項目", "醫院診所", "備註"]
                    ].values,
                )
            )

        fig.update_layout(
            title=f"{selected_item} 歷史變化與事件對照圖",
            xaxis_title="日期",
            yaxis_title="數值",
            hovermode="closest",
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("歷史明細")
        st.dataframe(
            item_df[
                ["日期", "數值", "單位", "參考範圍", "醫院診所", "備註"]
            ],
            use_container_width=True,
        )