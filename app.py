import gspread
import pandas as pd
import plotly.express as px
import streamlit as st
from google.oauth2.service_account import Credentials

# 頁面基本設定（適合手機瀏覽）
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
    # 支援本地 json 或 Streamlit Cloud Secrets
    if "gcp_service_account" in st.secrets:
      creds = Credentials.from_service_account_info(
          st.secrets["gcp_service_account"], scopes=SCOPES
      )
    else:
      creds = Credentials.from_service_account_file(
          "credentials.json", scopes=SCOPES
      )

    client = gspread.authorize(creds)
    # 替換成你的 Google 試算表名稱
    sheet = client.open("我的健康與就醫紀錄").sheet1
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    if not df.empty and "日期" in df.columns:
      df["日期"] = pd.to_datetime(df["日期"])
      df = df.sort_values("日期", ascending=False)
    return sheet, df
  except Exception as e:
    st.error(f"讀取資料失敗：{e}")
    return None, pd.DataFrame()


sheet, df = load_data()

st.title("🩺 健康與就醫歷程")

# 分頁籤設計：方便手機上滑動切換功能
tab1, tab2, tab3 = st.tabs(["📊 數據趨勢", "📋 完整歷程", "➕ 新增紀錄"])

# Tab 1: 驗血數據趨勢圖
with tab1:
  st.header("驗血數據趨勢")
  if not df.empty:
    blood_df = df[df["類別"] == "驗血"].copy()
    if not blood_df.empty:
      blood_df["數值"] = pd.to_numeric(blood_df["數值"], errors="coerce")
      items = blood_df["項目"].dropna().unique()

      selected_item = st.selectbox("選擇要檢視的血液指標", items)

      item_df = blood_df[blood_df["項目"] == selected_item].sort_values(
          "日期"
      )

      if not item_df.empty:
        # 使用 Plotly 繪製互動式趨勢圖
        fig = px.line(
            item_df,
            x="日期",
            y="數值",
            markers=True,
            title=f"{selected_item} 歷史變化曲線",
            text="數值",
            hover_data=["單位", "參考範圍", "醫院診所", "備註"],
        )
        fig.update_traces(textposition="top center")
        fig.update_layout(xaxis_title="日期", yaxis_title="數值")
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

# Tab 3: 直接在手機網頁上記錄新數據
with tab3:
  st.header("新增筆記 / 紀錄")
  with st.form("add_data_form", clear_on_submit=True):
    date_val = st.date_input("日期")
    cat_val = st.selectbox("類別", ["驗血", "看診", "用藥", "其他"])
    item_val = st.text_input("項目 (如: 飯前血糖, 心臟科門診)")
    val_val = st.text_input("數值 (驗血才需填寫，無則留空)")
    unit_val = st.text_input("單位 (如: mg/dL)")
    ref_val = st.text_input("參考範圍 (如: 70-99)")
    hosp_val = st.text_input("醫院 / 診所")
    note_val = st.text_area("醫師囑咐 / 備註")

    submitted = st.form_submit_submitted = st.form_submit_button("寫入 Google 試算表")

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
        st.success("成功新增資料！請刷新頁面查看最新數據。")
      else:
        st.error("連線至 Google 試算表失敗，無法寫入。")