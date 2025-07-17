# 這是 Python Flask 框架的範例程式碼。
# 您需要先安裝 Flask 和 requests 函式庫：
# pip install Flask requests
# 並將其部署到一個雲端伺服器環境中才能運行，例如 Vercel、Heroku 或您自己的伺服器。

from flask import Flask, jsonify, request
from flask_cors import CORS # 用於允許前端網頁存取，解決跨域問題
import requests # 用於發送 HTTP 請求到外部 API
import json # 導入 json 模組用於解析錯誤訊息
import xml.etree.ElementTree as ET # 用於解析 XML 格式的資料 (例如氣象特報 RSS)
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app) # 允許所有來源的跨域請求。在實際部署時，為了安全考量，
          # 建議限制只允許您網頁的特定網域存取，例如：CORS(app, resources={r"/*": {"origins": "https://your-website-domain.com"}})

# 中央氣象署開放資料平台 API Key
# **請務必將 'CWA-DA27CC49-2356-447C-BDB3-D5AA4071E24B' 替換為您自己申請的真實 API Key！**
# 如果您還沒有，請到中央氣象署開放資料平台申請：https://opendata.cwa.gov.tw/
CWA_API_KEY = 'CWA-DA27CC49-2356-447C-BDB3-D5AA4071E24B' 

# 中央氣象署颱風警報 API 端點
# 目前使用 W-C0034-005 (熱帶氣旋路徑) 獲取颱風資訊
CWA_TYPHOON_API_URL = 'https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0034-005'
# 中央氣象署 RSS 警報特報服務 (提供XML格式的最新氣象特報)
CWA_RSS_WARNING_URL = 'https://www.cwa.gov.tw/rss/Data/cwa_warning.xml'

# Tropical Tidbits JTWC 數據來源 (用於解析 JTWC 的 ATCF 數據)
# 這個網站會聚合 JTWC 的數據並提供相對穩定的訪問
TROPICAL_TIDBITS_JTWC_URL = 'https://www.tropicaltidbits.com/storminfo/latest_jtc.txt'

@app.route('/get-typhoon-data', methods=['GET'])
def get_typhoon_data():
    """
    這個路由會作為前端網頁的代理，去中央氣象署 API 獲取颱風資料。
    當前端網頁向此路由發送請求時，它會轉發請求到中央氣象署的颱風 API，
    並將獲取的 JSON 資料直接返回給前端。
    """
    try:
        # 向中央氣象署 API 發送請求，並在 URL 中包含 Authorization 參數 (API Key)
        api_response = requests.get(f"{CWA_TYPHOON_API_URL}?Authorization={CWA_API_KEY}")
        api_response.raise_for_status() # 如果響應狀態碼不是 200 (表示成功)，則拋出 HTTPError 異常

        # 嘗試解析 API 回應為 JSON 格式。如果回應不是有效的 JSON，會拋出 ValueError。
        data = api_response.json()
        return jsonify(data) # 將從氣象署獲取的 JSON 資料直接返回給前端

    except requests.exceptions.RequestException as e:
        # 處理網路請求錯誤（例如連線失敗、DNS 解析失敗、超時等）
        print(f"向中央氣象署 API 請求失敗: {e}")
        # 嘗試獲取中央氣象署 API 的回應狀態碼和內容，以便偵錯
        cwa_response_status = api_response.status_code if 'api_response' in locals() and api_response else None
        cwa_response_text = api_response.text if 'api_response' in locals() and api_response else None
        
        return jsonify({
            "error": "無法從中央氣象署獲取颱風資料",
            "details": str(e), # 錯誤的詳細訊息
            "cwa_response_status": cwa_response_status, # 中央氣象署 API 的 HTTP 狀態碼
            "cwa_response_text": cwa_response_text # 中央氣象署 API 的原始回應內容
        }), 500 # 返回 HTTP 500 內部伺服器錯誤狀態碼
    except json.JSONDecodeError as e: # 捕獲 JSON 解析錯誤
        print(f"解析中央氣象署 API 回應失敗 (非 JSON 格式): {e}")
        # 同樣嘗試獲取中央氣象署 API 的回應狀態碼和內容
        cwa_response_status = api_response.status_code if 'api_response' in locals() and api_response else None
        cwa_response_text = api_response.text if 'api_response' in locals() and api_response else None
        return jsonify({
            "error": "解析中央氣象署 API 回應失敗 (非 JSON 格式)",
            "details": str(e),
            "cwa_response_status": cwa_response_status,
            "cwa_response_text": cwa_response_text
        }), 500
    except Exception as e:
        # 處理其他所有未預期的錯誤
        print(f"伺服器代理獲取颱風資料時發生未知錯誤: {e}")
        return jsonify({"error": "伺服器內部錯誤", "details": str(e)}), 500

@app.route('/get-cwa-warnings', methods=['GET'])
def get_cwa_warnings():
    """
    這個路由會作為前端網頁的代理，去中央氣象署 RSS 服務獲取警報特報資料。
    它會獲取 XML 格式的 RSS feed，解析其中的項目，並篩選出與警報特報相關的資訊，
    然後以 JSON 格式返回給前端。
    """
    print("Received request for /get-cwa-warnings") # 輸出訊息到伺服器控制台，確認請求是否到達代理伺服器
    try:
        # 向中央氣象署 RSS 服務發送請求
        rss_response = requests.get(CWA_RSS_WARNING_URL)
        rss_response.raise_for_status() # 如果響應狀態碼不是 200，則拋出 HTTPError

        # 解析 XML 格式的 RSS 回應
        root = ET.fromstring(rss_response.content)
        warnings = [] # 用於儲存篩選後的警報特報資訊
        
        # 定義要篩選的關鍵字，這些關鍵字通常出現在警報特報的標題或描述中
        keywords_to_filter = ["警報", "特報", "豪(大)雨特報", "低溫特報", "濃霧特報", "強風特報", "大雷雨", "地震"]

        # 遍歷 RSS feed 中的每個 <item> 標籤
        for item in root.findall('.//item'):
            # 安全地獲取每個元素的文本內容，如果元素不存在則設為空字串
            title = item.find('title').text if item.find('title') is not None else ''
            link = item.find('link').text if item.find('link') is not None else ''
            description = item.find('description').text if item.find('description') is not None else ''
            pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ''

            # 檢查標題或描述是否包含任何關鍵字
            is_relevant = False
            for keyword in keywords_to_filter:
                if keyword in title or keyword in description:
                    is_relevant = True
                    break # 只要找到一個關鍵字就停止檢查
            
            if is_relevant: # 如果包含相關關鍵字，則將其加入到 warnings 列表中
                warnings.append({
                    "title": title,
                    "link": link,
                    "description": description,
                    "pubDate": pubDate
                })
        
        return jsonify({"success": True, "warnings": warnings}) # 返回成功的 JSON 回應和篩選後的警報列表

    except requests.exceptions.RequestException as e:
        print(f"向中央氣象署 RSS 請求失敗: {e}")
        return jsonify({"error": "無法從中央氣象署 RSS 獲取資料", "details": str(e)}), 500
    except ET.ParseError as e: # 捕獲 XML 解析錯誤
        print(f"解析 RSS XML 失敗: {e}")
        return jsonify({"error": "解析 RSS XML 失敗", "details": str(e)}), 500
    except Exception as e:
        print(f"伺服器代理獲取警報時發生未知錯誤: {e}")
        return jsonify({"error": "伺服器內部錯誤", "details": str(e)}), 500

@app.route('/get-international-typhoon-data', methods=['GET'])
def get_international_typhoon_data():
    """
    這個路由會作為前端網頁的代理，去 Tropical Tidbits 獲取 JTWC 的原始颱風數據。
    它會解析 ATCF 格式的文本數據，並將其轉換成結構化的 JSON 格式返回給前端。
    """
    print("Received request for /get-international-typhoon-data")
    try:
        # 從 Tropical Tidbits 獲取 JTWC ATCF 數據
        response = requests.get(TROPICAL_TIDBITS_JTWC_URL, timeout=15)
        response.raise_for_status() # 檢查 HTTP 狀態碼，如果不是 200 則拋出異常
        
        atcf_data = response.text
        
        # 解析 ATCF 數據
        typhoon_info = parse_jtwc_atcf(atcf_data)
        
        if typhoon_info:
            return jsonify({"success": True, "typhoon": typhoon_info})
        else:
            return jsonify({"success": False, "message": "目前沒有活躍的國際颱風數據。"}), 200

    except requests.exceptions.Timeout:
        print(f"從 {TROPICAL_TIDBITS_JTWC_URL} 獲取數據超時。")
        return jsonify({"success": False, "error": "獲取國際颱風數據超時，請稍後再試。"}), 504
    except requests.exceptions.RequestException as e:
        print(f"從 {TROPICAL_TIDBITS_JTWC_URL} 獲取數據失敗: {e}")
        return jsonify({"success": False, "error": f"無法獲取國際颱風數據: {str(e)}"}), 500
    except Exception as e:
        print(f"解析國際颱風數據時發生錯誤: {e}")
        return jsonify({"success": False, "error": f"解析國際颱風數據失敗: {str(e)}"}), 500

def parse_jtwc_atcf(atcf_text):
    """
    解析 JTWC 的 ATCF 文本數據，提取颱風資訊。
    ATCF 數據格式非常複雜，這裡只提取必要的路徑點資訊。
    每行數據由逗號分隔，包含多個欄位。
    我們主要關心以下欄位（索引可能因 ATCF 版本而異，這裡基於常見格式）：
    0: Basin (盆地)
    1: Cyclone Number (氣旋編號)
    2: YYYYMMDDHH (時間)
    3: Technique (預報技術)
    4: Forecast Period (預報時效)
    5: Lat (緯度)
    6: Lon (經度)
    7: Max Sustained Wind (最大持續風速，節)
    8: Minimum Sea Level Pressure (最低海平面氣壓，百帕)
    ... (其他欄位)
    """
    lines = atcf_text.strip().split('\n')
    
    if not lines:
        return None

    typhoon_data = {
        "name": "未知颱風",
        "currentPosition": None,
        "pastTrack": [],
        "forecastTrack": []
    }
    
    current_typhoon_id = None # 用於追蹤當前處理的颱風

    for line in lines:
        parts = [p.strip() for p in line.split(',')]
        
        if len(parts) < 10: # 確保有足夠的欄位
            continue
        
        try:
            basin = parts[0]
            cyclone_num = parts[1]
            # 組合颱風 ID，例如 WP012025 (西北太平洋第一個颱風，2025年)
            typhoon_id = f"{basin}{cyclone_num}{parts[2][0:4]}" 

            # 如果是新的颱風，更新當前颱風 ID 和名稱
            if current_typhoon_id is None:
                current_typhoon_id = typhoon_id
            elif current_typhoon_id != typhoon_id:
                # 遇到新的颱風，這裡我們只處理第一個或最新的颱風
                # 如果需要處理多個颱風，需要更複雜的數據結構
                print(f"偵測到新的颱風 {typhoon_id}，但目前只處理第一個颱風。")
                continue # 跳過這個颱風的數據

            # 提取時間 (YYYYMMDDHH)
            time_str = parts[2] # 例如 2025071700
            # 將時間字串轉換為 ISO 格式
            # 確保時間字串長度足夠，並處理可能缺失的情況
            if len(time_str) >= 10:
                dt_object = datetime.strptime(time_str, '%Y%m%d%H')
                iso_time = dt_object.isoformat() + 'Z' # 加上 Z 表示 UTC 時間
            else:
                iso_time = None # 無法解析時間

            # 提取緯度 (Lat) 和經度 (Lon)
            # 緯度格式可能是 123N (12.3度北緯) 或 123S (12.3度南緯)
            # 經度格式可能是 1234W (123.4度西經) 或 1234E (123.4度東經)
            lat_raw = parts[5]
            lon_raw = parts[6]

            lat = float(lat_raw[:-1]) / 10.0 if lat_raw and lat_raw[-1] in ['N', 'S'] else None
            if lat_raw and lat_raw.endswith('S'):
                lat = -lat

            lon = float(lon_raw[:-1]) / 10.0 if lon_raw and lon_raw[-1] in ['E', 'W'] else None
            if lon_raw and lon_raw.endswith('W'):
                lon = -lon
            
            if lat is None or lon is None:
                print(f"無法解析座標: Lat={lat_raw}, Lon={lon_raw}")
                continue # 跳過無效座標的行

            # 提取最大持續風速 (Max Sustained Wind, 節)
            wind_speed_knots = int(parts[7]) if parts[7].isdigit() else 0
            wind_speed_ms = round(wind_speed_knots * 0.514444, 1) # 節轉換為公尺/秒

            # 提取最低海平面氣壓 (Minimum Sea Level Pressure, 百帕)
            pressure_hpa = int(parts[8]) if parts[8].isdigit() else 0

            # 預報時效 (Forecast Period)，通常是 000, 012, 024, ...
            forecast_period_str = parts[4]
            forecast_period_hours = int(forecast_period_str) if forecast_period_str.isdigit() else 0

            # 判斷是歷史路徑還是預測路徑
            # 'BEST' 通常代表最佳路徑 (已分析的歷史數據)
            # 'PROB' 或其他技術代碼代表預測
            technique = parts[3].strip()

            point = {
                "time": iso_time,
                "lat": lat,
                "lon": lon,
                "windSpeed_knots": wind_speed_knots,
                "windSpeed_ms": wind_speed_ms,
                "pressure_hpa": pressure_hpa,
                "forecastPeriod_hours": forecast_period_hours
            }

            if technique == 'BEST':
                typhoon_data["pastTrack"].append(point)
                # 如果是 BEST 數據且預報時效為 0，則視為當前位置
                if forecast_period_hours == 0:
                    typhoon_data["currentPosition"] = point
            else:
                typhoon_data["forecastTrack"].append(point)
                # 如果還沒有設置當前位置，且這是第一個預測點的初始時間，可以考慮設為當前位置
                if typhoon_data["currentPosition"] is None and forecast_period_hours == 0:
                     typhoon_data["currentPosition"] = point

            # 嘗試從 ATCF 數據中獲取颱風名稱
            # ATCF 數據通常不直接包含颱風的英文或中文名稱，
            # 但有時會從備註或預報討論中提取。
            # 這裡我們暫時使用一個通用名稱，或者從 JTWC 的預報號碼來生成。
            # 實際應用中，可能需要額外的查找表或從 JTWC 網站的 HTML 內容中抓取。
            if len(parts) > 27 and parts[27].strip(): # 嘗試從備註欄位獲取名稱
                typhoon_data["name"] = parts[27].strip()
            elif len(parts) > 1 and parts[1].strip(): # 否則使用氣旋編號作為名稱的一部分
                typhoon_data["name"] = f"TC {parts[1].strip()}"
            else:
                typhoon_data["name"] = "未知颱風"

        except (ValueError, IndexError) as e:
            print(f"解析 ATCF 行失敗: {line} - 錯誤: {e}")
            continue # 跳過無法解析的行
    
    # 對路徑點進行排序，確保時間順序正確
    typhoon_data["pastTrack"].sort(key=lambda x: x["time"] if x["time"] else "")
    typhoon_data["forecastTrack"].sort(key=lambda x: x["forecastPeriod_hours"])

    return typhoon_data if typhoon_data["pastTrack"] or typhoon_data["forecastTrack"] else None


if __name__ == '__main__':
    # 在本地運行時，Flask 應用會在 5000 端口上啟動
    # 在 Vercel 上部署時，Vercel 會自動處理服務器的啟動
    app.run(debug=True)
