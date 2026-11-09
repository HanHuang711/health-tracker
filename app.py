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
        # 🎨 顏色與圖示設定區
        # -------------------------------------------------------------
        CHEMO_COLOR = "#c8c8c8"  # 化療垂直虛線顏色

        # 各類別對應的顏色與圖示形狀 (circle=圓點, diamond=菱形, square=方塊)
        category_styles = {
            "看診": {"color": "#1F77B4", "symbol": "circle", "label": "🔵 看診紀錄"},
            "用藥": {"color": "#2CA02C", "symbol": "square", "label": "🟢 用藥紀錄"},
            "其他": {"color": "#FF7F0E", "symbol": "diamond", "label": "🟠 特殊事件"}
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

        # 3. 🟣 化療事件與其他事件處理
        if not event_df.empty:
          chemo_df = event_df[event_df["類別"] == "化療"]
          other_events_df = event_df[event_df["類別"] != "化療"]

          # 畫出化療垂直虛線（支援滑鼠懸停）
          y_min = item_df["數值"].min()
          y_max = item_df["數值"].max()
          y_mid = (y_min + y_max) / 2 if len(item_df) > 0 else 0

          first_chemo = True
          for _, chemo in chemo_df.iterrows():
            c_date = chemo["日期"]
            fig.add_trace(
                go.Scatter(
                    x=[c_date, c_date],
                    y=[y_min * 0.8, y_max * 1.2],
                    mode="lines",
                    name="🟣 化療紀錄" if first_chemo else "",
                    showlegend=first_chemo,
                    line=dict(color=CHEMO_COLOR, width=2.5, dash="dash"),
                    hovertemplate=(
                        "<b>【化療紀錄】</b><br>"
                        "<b>日期</b>: %{x|%Y-%m-%d}<br>"
                        f"<b>項目</b>: {chemo['項目']}<br>"
                        f"<b>醫院/診所</b>: {chemo['醫院診所']}<br>"
                        f"<b>備註</b>: {chemo['備註']}<extra></extra>"
                    ),
                )
            )
            first_chemo = False

          # 4. 其他事件（看診/用藥/其他）：排除「入院」與「出院」，其餘正常顯示互動圖示
          for cat, group in other_events_df.groupby("類別"):
            # 濾掉項目中包含「入院」或「出院」的紀錄，不顯示互動標示
            filtered_group = group[
                ~group["項目"].str.contains("入院|出院", na=False)
            ]

            if filtered_group.empty:
              continue

            style = category_styles.get(
                cat, {"color": "gray", "symbol": "diamond", "label": f"📌 {cat}"}
            )

            fig.add_trace(
                go.Scatter(
                    x=filtered_group["日期"],
                    y=[y_mid] * len(filtered_group),
                    mode="markers",
                    name=style["label"],
                    marker=dict(
                        size=13, symbol=style["symbol"], color=style["color"]
                    ),
                    hovertemplate=(
                        "<b>【%{customdata[0]}】</b><br>"
                        "<b>日期</b>: %{x}<br>"
                        "<b>項目</b>: %{customdata[1]}<br>"
                        "<b>醫院/診所</b>: %{customdata[2]}<br>"
                        "<b>備註</b>: %{customdata[3]}<extra></extra>"
                    ),
                    customdata=filtered_group[
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
      else:
        st.info("該項目尚無數值紀錄。")
    else:
      st.info("尚無類別為『驗血』的數據。")
  else:
    st.warning("目前試算表中沒有資料。")

# Tab 2: 完整歷史清單
with tab2:
  st.header("就醫與檢驗完整歷程")
  if not df.empty:
    category_filter = st.multiselect(
        "篩選類別", options=df["類別"].unique(), default=df["類別"].unique()
    )
    filtered_df = df[df["類別"].isin(category_filter)]
    st.dataframe(filtered_df, use_container_width=True)
  else:
    st.info("目前試算表中沒有資料。")

# Tab 3: 新增筆記 / 紀錄
with tab3:
  st.header("新增筆記 / 紀錄")
  with st.form("add_data_form", clear_on_submit=True):
    date_val = st.date_input("日期")
    cat_val = st.selectbox("類別", ["驗血", "看診", "用藥", "化療", "其他"])
    item_val = st.text_input("項目 (如: 入院, 出院, 第1次化療, 門診追蹤)")
    val_val = st.text_input("數值 (驗血才需填寫，無則留空)")
    unit_val = st.text_input("單位 (如: mg/dL)")
    ref_val = st.text_input("參考範圍 (如: 70-99)")
    hosp_val = st.text_input("醫院 / 診所", value="林口長庚")
    note_val = st.text_area("醫師囑咐 / 備註")

    submitted = st.form_submit_button("寫入 Google 試算表")

    if submitted:
      if sheet is not None:
        new_row = [
            str(date_val),
            cat_val,
            item_val,
            val_val,
            unit_val,
            ref_val,
            hosp_val,
            note_val,
        ]
        sheet.append_row(new_row)
        st.success("成功新增資料！請刷新頁面查看最新互動圖表。")
      else:
        st.error("連線至 Google 試算表失敗，無法寫入。")