import json
import tempfile
import google.genai as genai
import gspread
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.oauth2.service_account import Credentials


# 頁面基本設定
st.set_page_config(
    page_title="阿爸的人生劇本", page_icon="🩺", layout="centered"
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# 載入雲端試算表資料 (驗血與醫療歷程)
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


# 載入「看診問答」資料
def load_qa_data():
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
    try:
      qa_sheet = client.open("我的健康與就醫紀錄").worksheet("看診問答")
    except Exception:
      qa_sheet = client.open("我的健康與就醫紀錄").add_worksheet(
          title="看診問答", rows=100, cols=4
      )
      qa_sheet.update(
          [["預定看診日期", "想詢問的問題", "醫生回答與備註", "狀態"]]
      )

    qa_data = qa_sheet.get_all_records()
    qa_df = pd.DataFrame(qa_data)

    if not qa_df.empty and "預定看診日期" in qa_df.columns:
      qa_df["預定看診日期"] = pd.to_datetime(
          qa_df["預定看診日期"], format="mixed", errors="coerce"
      )
      qa_df = qa_df.sort_values("預定看診日期", ascending=True)
    return qa_sheet, qa_df
  except Exception as e:
    return None, pd.DataFrame()


# 🎙️ 使用新版 Google GenAI SDK 分析看診音檔摘要
def analyze_audio_consultation_gemini(audio_file_bytes, file_name):
  api_key = st.secrets.get("GEMINI_API_KEY", "")
  if not api_key:
    st.error("未設定 GEMINI_API_KEY，無法使用 Gemini 語音辨識功能。")
    return None, None

  try:
    with st.spinner(
        "🤖 Google Gemini (GenAI) 正在上傳並聆聽音檔、萃取看診重點中..."
    ):
      # 初始化新版 Client
      client = genai.Client(api_key=api_key)

      # 建立臨時檔案儲存上傳的音訊
      suffix = "." + file_name.split(".")[-1] if "." in file_name else ".mp3"
      with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(audio_file_bytes)
        tmp_path = tmp.name

      # 使用新版 Files API 上傳音檔
      audio_file = client.files.upload(file=tmp_path)

      prompt = """
            請仔細聆聽這段醫療看診時的對話錄音，並幫我分析並萃取重點，整理成嚴格的 JSON 格式（不要包含任何 markdown 程式碼標記如 ```json）：
            {
                "整體摘要": "這次看診的核心摘要與注意事項（一句話總結）",
                "問答清單": [
                    {
                        "問題": "病患或家屬詢問的問題（若對話中未明確提及，可根據情境整理）",
                        "醫生回答與備註": "醫師給出的指示、藥物調整或衛教交代"
                    }
                ]
            }
            """

      # 呼叫最新閃電模型 gemini-2.5-flash
      response = client.models.generate_content(
          model="gemini-3.8-flash", contents=[audio_file, prompt]
      )

      # 刪除雲端暫存檔案
      try:
        client.files.delete(name=audio_file.name)
      except:
        pass

      result_text = response.text.strip()
      if result_text.startswith("```"):
        result_text = (
            result_text.replace("```json", "").replace("```", "").strip()
        )

      parsed_json = json.loads(result_text)
      return parsed_json, "（已透過最新 Google GenAI SDK 語音分析完成）"
  except Exception as e:
    st.error(f"Gemini 語音分析失敗：{e}")
    return None, None


sheet, df = load_data()
qa_sheet, qa_df = load_qa_data()

st.title("🩺 身體的功課")

# 分頁籤設計
tab1, tab2, tab3, tab4 = st.tabs(
    ["📊 數據趨勢", "📋 在線編輯與歷程", "➕ 新增紀錄", "💬 看診問答"]
)

# Tab 1: 驗血數據趨勢圖
with tab1:
  st.header("驗血數據趨勢")
  if not df.empty:
    blood_df = df[df["類別"] == "驗血"].copy()
    event_df = df[df["類別"] != "驗血"].sort_values("日期").copy()

    if not blood_df.empty:
      blood_df["數值"] = pd.to_numeric(blood_df["數值"], errors="coerce")
      items = sorted(blood_df["項目"].dropna().unique().astype(str))

      selected_item = st.selectbox("選擇要檢視的血液指標", items)
      item_df = blood_df[blood_df["項目"] == selected_item].sort_values(
          "日期"
      )

      if not item_df.empty:
        fig = go.Figure()

        CHEMO_COLOR = "#c8c8c8"
        NORMAL_POINT_COLOR = "#64dcf0"
        ABNORMAL_POINT_COLOR = "#FF4B4B"

        category_styles = {
            "看診": {
                "color": "#64dcf0",
                "symbol": "circle",
                "name": "看診紀錄",
            },
            "用藥": {
                "color": "#2CA02C",
                "symbol": "square",
                "name": "用藥紀錄",
            },
            "其他": {
                "color": "#FF7F0E",
                "symbol": "diamond",
                "name": "特殊事件",
            },
        }

        if "數值異常" not in item_df.columns:
          item_df["數值異常"] = ""

        point_colors = []
        for _, row in item_df.iterrows():
          val_abnormal = row.get("數值異常", "")
          if pd.notna(val_abnormal) and str(val_abnormal).strip() != "":
            point_colors.append(ABNORMAL_POINT_COLOR)
          else:
            point_colors.append(NORMAL_POINT_COLOR)

        fig.add_trace(
            go.Scatter(
                x=item_df["日期"],
                y=item_df["數值"],
                mode="lines+markers+text",
                name=selected_item,
                text=item_df["數值"],
                textposition="top center",
                line=dict(color="#1F77B4", width=2),
                marker=dict(size=10, color=point_colors),
                hovertemplate=(
                    "<b>日期</b>: %{x|%Y-%m-%d}<br>"
                    "<b>數值</b>: %{y}<br>"
                    "<b>單位</b>: %{customdata[0]}<br>"
                    "<b>參考範圍</b>: %{customdata[1]}<br>"
                    "<b>異常狀態</b>: %{customdata[2]}<br>"
                    "<b>醫院診所</b>: %{customdata[3]}<br>"
                    "<b>備註</b>: %{customdata[4]}<extra></extra>"
                ),
                customdata=item_df[
                    ["單位", "參考範圍", "數值異常", "醫院診所", "備註"]
                ].values,
            )
        )

        if not event_df.empty:
          sorted_events = event_df.sort_values("日期")
          admit_records = sorted_events[
              sorted_events["項目"].str.contains("入院", na=False)
          ]
          discharge_records = sorted_events[
              sorted_events["項目"].str.contains("出院", na=False)
          ]

          for _, admit in admit_records.iterrows():
            admit_date = admit["日期"]
            matching_discharge = discharge_records[
                discharge_records["日期"] >= admit_date
            ]

            if not matching_discharge.empty:
              discharge_date = matching_discharge.iloc[0]["日期"]
              discharge_records = discharge_records[
                  discharge_records["日期"] != discharge_date
              ]
            else:
              discharge_date = admit_date + pd.Timedelta(days=5)

            fig.add_vrect(
                x0=admit_date,
                x1=discharge_date,
                fillcolor="lightcoral",
                opacity=0.15,
                layer="below",
                line_width=0,
            )

        if not event_df.empty:
          chemo_df = event_df[event_df["類別"] == "化療"]
          other_events_df = event_df[event_df["類別"] != "化療"]

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
                    name="化療紀錄",
                    showlegend=first_chemo,
                    line=dict(color=CHEMO_COLOR, width=2, dash="dash"),
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

          for cat, group in other_events_df.groupby("類別"):
            filtered_group = group[
                ~group["項目"].str.contains("入院|出院", na=False)
            ]
            if filtered_group.empty:
              continue

            aggregated_records = []
            for date_key, date_subgroup in filtered_group.groupby("日期"):
              items_list = []
              for _, r in date_subgroup.iterrows():
                item_text = f"{r['項目']}"
                if pd.notna(r["備註"]) and str(r["備註"]).strip():
                  item_text += f" ({r['備註']})"
                items_list.append(item_text)

              items_str = "<br>• ".join(items_list)
              hosp_str = date_subgroup.iloc[0]["醫院診所"]

              aggregated_records.append({
                  "日期": date_key,
                  "類別": cat,
                  "項目內容": items_str,
                  "醫院診所": hosp_str,
              })

            agg_df = pd.DataFrame(aggregated_records)
            style = category_styles.get(
                cat,
                {"color": "gray", "symbol": "diamond", "name": f"{cat}紀錄"},
            )

            fig.add_trace(
                go.Scatter(
                    x=agg_df["日期"],
                    y=[y_mid] * len(agg_df),
                    mode="markers",
                    name=style["name"],
                    marker=dict(
                        size=12, symbol=style["symbol"], color=style["color"]
                    ),
                    hovertemplate=(
                        "<b>【%{customdata[0]}】</b><br>"
                        "<b>日期</b>: %{x|%Y-%m-%d}<br>"
                        "<b>醫院/診所</b>: %{customdata[2]}<br>"
                        "<b>當日項目</b>:<br>• %{customdata[1]}<extra></extra>"
                    ),
                    customdata=agg_df[
                        ["類別", "項目內容", "醫院診所"]
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
                ["日期", "數值", "單位", "參考範圍", "數值異常", "醫院診所", "備註"]
            ],
            use_container_width=True,
        )
      else:
        st.info("該項目尚無數值紀錄。")
    else:
      st.info("尚無類別為『驗血』的數據。")
  else:
    st.warning("目前試算表中沒有資料。")

# Tab 2: 📱 在線雙擊編輯與完整歷程
with tab2:
  st.header("📋 線上數據編輯與總覽")
  st.caption(
      "💡 提示：你可以直接雙擊下方表格儲存格修改文字，編輯完後點擊最下方按鈕即可同步至"
      " Google 雲端！"
  )

  if not df.empty:
    edit_df = df.copy()
    if "日期" in edit_df.columns:
      edit_df["日期"] = edit_df["日期"].dt.strftime("%Y-%m-%d")

    edited_df = st.data_editor(
        edit_df,
        use_container_width=True,
        num_rows="dynamic",
        key="health_data_editor",
    )

    if st.button("💾 儲存所有修改至 Google 試算表", type="primary"):
      if sheet is not None:
        try:
          updated_data = edited_df.fillna("").astype(str).values.tolist()
          sheet.clear()
          header = list(edited_df.columns)
          sheet.update([header] + updated_data)
          st.success("✅ 修改成功！所有資料已更新至 Google 試算表。")
          st.rerun()
        except Exception as e:
          st.error(f"❌ 寫入雲端失敗：{e}")
      else:
        st.error("連線至 Google 試算表失敗，無法儲存。")
  else:
    st.info("目前試算表中沒有資料。")

# Tab 3: 新增紀錄
with tab3:
  st.header("➕ 新增健康與就醫紀錄")

  cat_val = st.selectbox("類別", ["驗血", "看診", "用藥", "化療", "其他"])

  existing_blood_items = []
  if not df.empty and "類別" in df.columns:
    b_df = df[df["類別"] == "驗血"]
    if not b_df.empty:
      existing_blood_items = sorted(b_df["項目"].dropna().unique().astype(str))

  with st.form("add_data_form", clear_on_submit=True):
    import datetime

    date_val = st.date_input("日期", value=datetime.date.today())

    if cat_val == "驗血" and existing_blood_items:
      item_val = st.selectbox("項目 (選擇驗血指標)", existing_blood_items)
    else:
      item_val = st.text_input(
          "項目 (如: 入院, 出院, 第1次化療, 門診追蹤, 直腸科)"
      )

    val_val = st.text_input("數值 (驗血才需填寫，無則留空)")
    unit_val = st.text_input("單位 (如: mg/dL)")
    ref_val = st.text_input("參考範圍 (如: 70-99)")
    abnormal_val = st.text_input("數值異常標記 (如: H 或 L，正常則留空)")
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
            abnormal_val,
        ]
        sheet.append_row(new_row)
        st.success("🎉 成功寫入 Google 試算表！請刷新頁面查看最新趨勢圖。")
        st.rerun()
      else:
        st.error("連線至 Google 試算表失敗，無法寫入。")

# Tab 4: 💬 看診問答專區（包含 Gemini 錄音檔 AI 摘要）
with tab4:
  st.header("💬 下次看診問題與醫生回答記錄")

  # 🎙️ 上傳看診錄音檔自動分析區塊 (Gemini 驅動)
  with st.expander("🎙️ 上傳看診錄音檔（Gemini AI 自動聆聽並萃取問答）", expanded=False):
    st.caption(
        "看完診後，可直接上傳手機錄音檔（支援 mp3, m4a, wav），Google Gemini"
        " 會自動幫忙分析並整理成問答清單！"
    )
    audio_file_uploaded = st.file_uploader(
        "選擇看診錄音檔", type=["mp3", "m4a", "wav", "ogg", "webm"]
    )

    if audio_file_uploaded is not None:
      st.audio(audio_file_uploaded)
      if st.button("🤖 開始用 Gemini 分析錄音檔"):
        parsed_result, raw_info = analyze_audio_consultation_gemini(
            audio_file_uploaded.getvalue(), audio_file_uploaded.name
        )
        if parsed_result:
          st.session_state["gemini_audio_qa"] = parsed_result
          st.session_state["gemini_raw_info"] = raw_info
          st.success("✅ Gemini 語音分析成功！請往下查看整理結果。")

    # 如果有分析結果，提供一鍵寫入選項
    if "gemini_audio_qa" in st.session_state:
      st.info(
          f"💡 **AI 整體摘要**：{st.session_state['gemini_audio_qa'].get('整體摘要', '')}"
      )
      st.write("👇 **萃取出的問答清單（點擊下方按鈕可批量寫入問題庫）**：")

      for i, qa_item in enumerate(
          st.session_state["gemini_audio_qa"].get("問答清單", [])
      ):
        st.text_input(
            f"Q{i+1}",
            value=qa_item.get("問題", ""),
            key=f"g_q_{i}",
            disabled=True,
        )
        st.text_input(
            f"A{i+1}",
            value=qa_item.get("醫生回答與備註", ""),
            key=f"g_a_{i}",
            disabled=True,
        )

      if st.button("📥 將上述 AI 整理的問答全部寫入 Google 試算表"):
        if qa_sheet is not None:
          try:
            import datetime

            today_str = str(datetime.date.today())
            rows_to_add = []
            for qa_item in st.session_state["gemini_audio_qa"].get(
                "問答清單", []
            ):
              rows_to_add.append([
                  today_str,
                  qa_item.get("問題", ""),
                  qa_item.get("醫生回答與備註", ""),
                  "已詢問",
              ])
            qa_sheet.append_rows(rows_to_add)
            st.success("🎉 成功將 Gemini 整理的問答寫入雲端！")
            del st.session_state["gemini_audio_qa"]  # 清除暫存
            st.rerun()
          except Exception as e:
            st.error(f"寫入失敗：{e}")

      with st.expander("查看 AI 分析說明"):
        st.write(st.session_state.get("gemini_raw_info", ""))

  st.divider()

  # 1. 手動新增想問的問題表單
  with st.form("add_qa_form", clear_on_submit=True):
    st.subheader("📝 手動新增要詢問的問題")
    import datetime

    qa_date_val = st.date_input("預定看診日期", value=datetime.date.today())
    question_val = st.text_area("想詢問的問題 (例如：最近容易疲倦正常嗎？)")
    status_val = st.selectbox("狀態", ["待詢問", "已詢問"])

    qa_submitted = st.form_submit_button("新增到問題清單")

    if qa_submitted:
      if qa_sheet is not None:
        try:
          new_qa_row = [str(qa_date_val), question_val, "", status_val]
          qa_sheet.append_row(new_qa_row)
          st.success("✅ 成功新增問題！")
          st.rerun()
        except Exception as e:
          st.error(f"❌ 新增失敗：{e}")
      else:
        st.error("無法連線至「看診問答」試算表。")

  st.divider()

  # 2. 顯示與在線編輯清單
  st.subheader("📋 問答紀錄總覽（可直接雙擊修改問題、填寫醫生回答或更改狀態）")

  if not qa_df.empty:
    edit_qa_df = qa_df.copy()
    if "預定看診日期" in edit_qa_df.columns:
      edit_qa_df["預定看診日期"] = edit_qa_df["預定看診日期"].dt.strftime(
          "%Y-%m-%d"
      )

    edited_qa_df = st.data_editor(
        edit_qa_df,
        use_container_width=True,
        num_rows="dynamic",
        key="qa_data_editor",
    )

    if st.button("💾 儲存問答修改至 Google 試算表", type="primary"):
      if qa_sheet is not None:
        try:
          updated_qa_data = (
              edited_qa_df.fillna("").astype(str).values.tolist()
          )
          qa_sheet.clear()
          qa_header = list(edited_qa_df.columns)
          qa_sheet.update([qa_header] + updated_qa_data)
          st.success("✅ 問答紀錄已成功同步更新至 Google 試算表！")
          st.rerun()
        except Exception as e:
          st.error(f"❌ 雲端同步失敗：{e}")
      else:
        st.error("無法連線至 Google 試算表。")
  else:
    st.info("目前尚無看診問答紀錄，可以手動新增或上傳錄音檔讓 Gemini 自動整理！")