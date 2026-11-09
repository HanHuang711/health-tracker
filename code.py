import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

# 1. 設定 Google API 授權範圍
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def load_health_data(json_path, spreadsheet_name, worksheet_index=0):
  """讀取 Google 試算表並轉換為 Pandas DataFrame"""
  try:
    # 載入服務帳戶金鑰進行認證
    creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
    client = gspread.authorize(creds)

    # 開啟雲端試算表
    sheet = client.open(spreadsheet_name)
    worksheet = sheet.get_worksheet(worksheet_index)

    # 取得所有資料並轉成 DataFrame
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)

    return df
  except Exception as e:
    print(f"讀取失敗，錯誤訊息：{e}")
    return None


if __name__ == "__main__":
  # 請替換成你的 Google Cloud 服務帳戶 JSON 檔案路徑
  JSON_KEY_PATH = "credentials.json"

  # 你的 Google 試算表名稱（檔案標題）
  SPREADSHEET_NAME = "我的健康與就醫紀錄"

  # 執行讀取
  df = load_health_data(JSON_KEY_PATH, SPREADSHEET_NAME)

  if df is not None and not df.empty:
    print("成功讀取試算表！前幾筆資料：")
    print(df.head())

    # 範例：篩選特定項目的數據（假設欄位名稱叫 "項目"）
    # cholesterol_df = df[df["項目"] == "膽固醇"]
    # print(cholesterol_df)