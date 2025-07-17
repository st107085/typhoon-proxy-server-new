# 這是 Python Flask 框架的範例程式碼。
# 您需要先安裝 Flask 和 requests 函式庫：
# pip install Flask requests
# 並將其部署到一個雲端伺服器環境中才能運行，例如 Vercel、Heroku 或您自己的伺服器。

from flask import Flask, jsonify, request
from flask_cors import CORS # 用於允許前端網頁存取，解決跨域問題
import requests # 用於發送 HTTP 請求到外部 API
import json # 導入 json 模組用於解析錯誤訊息
import xml.etree.ElementTree as ET # 用於解析 XML 格式的資料 (例如氣象特報 RSS)
from datetime import datetime, timedelta, timezone # 用於解析日期時間，新增 timedelta 和 timezone
import traceback # 導入 traceback 以獲取完整的錯誤堆疊資訊

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

# 新的 JTWC 數據源：NCEP 的 TCVITALS FTP 伺服器
# 這些檔案的命名格式是 gfs.YYYYMMDDHH/gfs.tHHZ.syndata.tcvitals.tm00
# 其中 YYYYMMDD 是日期，HH 是預報時間 (00, 06, 12, 18 UTC)
NCEP_TCVITALS_BASE_URL = "https://ftpprd.ncep.noaa.gov/data/nccf/com/gfs/prod/"


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

def parse_atcf_line(line):
    """
    解析 JTWC ATCF 格式的單行數據，提取關鍵資訊。
    ATCF 格式非常複雜，這裡只解析最常用的欄位。
    參考資料: https://www.nrlmry.navy.mil/atcf_web/docs/dm.txt
    """
    parts = line.strip().split(',')
    # TCVITALS 檔案的欄位數量可能與 ATCF 公開檔案略有不同，但核心資訊位置應相似。
    # 這裡我們需要確保至少有足夠的欄位來解析我們關心的數據（至少到颱風名稱欄位 27）。
    if len(parts) < 28: 
        # print(f"Warning: ATCF line has too few parts to parse all expected fields: {line.strip()}")
        return None

    try:
        # 欄位索引 (基於 ATCF 格式定義，從 0 開始)
        # 欄位 0: Basin (盆地)
        # 欄位 1: Cyclone Number (氣旋編號)
        # 欄位 2: Date/Time (YYYYMMDDHH) - TCVITALS 通常是 YYYYMMDDHH，而非 YYMMDDHH
        # 欄位 3: Technique (預報技術)
        # 欄位 4: Technique Number
        # 欄位 5: Forecast Period (預報時效，00表示觀測)
        # 欄位 6: Latitude (緯度)
        # 欄位 7: Longitude (經度)
        # 欄位 8: Max Wind (最大風速，節)
        # 欄位 9: MSLP (中心氣壓，毫巴)
        # 欄位 27: Name (颱風名稱)

        basin = parts[0].strip()
        cyclone_num = parts[1].strip()
        
        # 解析日期時間 (YYYYMMDDHH)
        dt_str = parts[2].strip()
        
        # TCVITALS 檔案的日期格式通常是 YYYYMMDDHH，所以直接解析
        try:
            dt_object = datetime.strptime(dt_str, '%Y%m%d%H')
            time_iso = dt_object.isoformat() + 'Z' # 轉換為 ISO 8601 格式，UTC
        except ValueError as ve:
            print(f"日期時間解析錯誤 (TCVITALS): {dt_str} - {ve}")
            return None

        # 解析緯度 (格式如 150N, 200S，表示 15.0N, 20.0S)
        lat_str = parts[6].strip()
        lat = float(lat_str[:-1]) / 10.0
        if lat_str.endswith('S'):
            lat *= -1

        # 解析經度 (格式如 1250E, 1300W，表示 125.0E, 130.0W)
        lon_str = parts[7].strip()
        lon = float(lon_str[:-1]) / 10.0
        if lon_str.endswith('W'):
            lon *= -1

        # 最大風速 (節，轉換為 公尺/秒)
        max_wind_knots = int(parts[8].strip())
        max_wind_ms = round(max_wind_knots * 0.514444, 1) # 1 節 = 0.514444 公尺/秒

        # 中心氣壓 (毫巴)
        pressure_hpa = int(parts[9].strip())

        # 預報時效 (小時)
        forecast_period_hours = int(parts[5].strip())

        # 颱風名稱 (通常在欄位 27)
        typhoon_name = parts[27].strip()
        if typhoon_name == "INVEST": # 投資區 (尚未發展成熱帶氣旋)
            typhoon_name = f"INVEST {cyclone_num}"


        return {
            "time": time_iso,
            "lat": lat,
            "lon": lon,
            "windSpeed_knots": max_wind_knots,
            "windSpeed_ms": max_wind_ms,
            "pressure_hpa": pressure_hpa,
            "forecastPeriod_hours": forecast_period_hours,
            "typhoonName": typhoon_name,
            "cycloneId": f"{basin}{cyclone_num}" # 組合盆地和編號作為唯一 ID
        }
    except (ValueError, IndexError) as e:
        print(f"解析 ATCF/TCVITALS 行時發生錯誤 (可能資料不完整或格式不符): {line.strip()} - 錯誤: {e}")
        traceback.print_exc() # 打印完整的錯誤堆疊資訊
        return None

@app.route('/get-international-typhoon-data')
def get_international_typhoon_data():
    """
    這個端點將從 NCEP 的 FTP 伺服器獲取 JTWC 的 TCVITALS 檔案，
    並解析後返回其中一個（例如，最新的或第一個找到的）颱風路徑資料。
    """
    # 獲取當前 UTC 時間
    now_utc = datetime.now(timezone.utc)
    
    # TCVITALS 檔案通常在 00Z, 06Z, 12Z, 18Z 更新。
    # 我們需要找到最近的可用時間。
    # 例如，如果現在是 09Z，我們應該嘗試獲取 06Z 的數據。
    # 如果現在是 05Z，我們應該嘗試獲取前一天 18Z 的數據。
    
    # 計算最近的 6 小時間隔
    # 將當前小時數除以 6，取整數，再乘以 6
    # 例如 09Z -> 9/6 = 1.5 -> 1 * 6 = 06Z
    # 例如 13Z -> 13/6 = 2.16 -> 2 * 6 = 12Z
    # 如果結果小時數大於當前小時數，則回溯一天
    
    # 這裡我們直接嘗試當天和前一天的幾個常見時間點，以確保能找到最近的數據
    possible_times = []
    # 嘗試當天
    for hour in [0, 6, 12, 18]:
        dt_candidate = now_utc.replace(hour=hour, minute=0, second=0, microsecond=0)
        if dt_candidate <= now_utc: # 只考慮過去或當前的時間點
            possible_times.append(dt_candidate)
    
    # 嘗試前一天
    yesterday_utc = now_utc - timedelta(days=1)
    for hour in [0, 6, 12, 18]:
        dt_candidate = yesterday_utc.replace(hour=hour, minute=0, second=0, microsecond=0)
        possible_times.append(dt_candidate)

    # 按時間倒序排序，從最新的時間點開始嘗試
    possible_times.sort(reverse=True)

    tcvitals_url = None
    response = None
    
    for dt_to_fetch in possible_times:
        date_str = dt_to_fetch.strftime('%Y%m%d')
        hour_str = dt_to_fetch.strftime('%H')
        
        # 構建 TCVITALS 檔案的完整 URL
        # 範例: https://ftpprd.ncep.noaa.gov/data/nccf/com/gfs/prod/gfs.20250717/gfs.t00z.syndata.tcvitals.tm00
        tcvitals_url_candidate = f"{NCEP_TCVITALS_BASE_URL}gfs.{date_str}/gfs.t{hour_str}z.syndata.tcvitals.tm00"
        print(f"嘗試從 NCEP FTP 獲取數據: {tcvitals_url_candidate}")

        try:
            # 對於 FTP 伺服器，通常不需要複雜的 HTTP 標頭
            response = requests.get(tcvitals_url_candidate, timeout=15) # 增加超時設定
            response.raise_for_status() # 檢查 HTTP 錯誤
            
            # 如果成功獲取，則使用這個 URL
            tcvitals_url = tcvitals_url_candidate
            print(f"成功獲取 TCVITALS 數據: {tcvitals_url}")
            break # 找到第一個可用的檔案就停止
        except requests.exceptions.RequestException as e:
            print(f"從 {tcvitals_url_candidate} 獲取數據失敗: {e}")
            # 繼續嘗試下一個時間點
            response = None # 重置 response，避免使用舊的失敗響應
            continue

    if not response:
        print("未能從 NCEP FTP 獲取任何 TCVITALS 檔案。")
        return jsonify({"success": False, "message": "未能從 NCEP FTP 獲取國際颱風資料，可能沒有活躍颱風數據或伺服器問題。"}), 500


    atcf_lines = response.text.strip().split('\n')
    print(f"成功獲取 TCVITALS 數據，共 {len(atcf_lines)} 行。")
    
    # 用於儲存所有解析後的颱風數據，按 ID 分組
    all_typhoons_parsed_data = {}

    for line_num, line in enumerate(atcf_lines):
        # 跳過註解行 (通常以 # 或空白開頭)
        if not line.strip() or line.strip().startswith('#'):
            continue

        parsed_point = parse_atcf_line(line)
        if parsed_point:
            cyclone_id = parsed_point["cycloneId"]
            typhoon_name = parsed_point["typhoonName"]

            if cyclone_id not in all_typhoons_parsed_data:
                all_typhoons_parsed_data[cyclone_id] = {
                    "pastTrack": [],
                    "forecastTrack": [],
                    "currentPosition": None,
                    "name": typhoon_name, # 使用 ATCF 中解析出的名稱
                    "id": cyclone_id,
                    "agency": "JTWC (via NCEP)" # 標記數據來源
                }
            
            # 根據預報時效分類數據點
            if parsed_point["forecastPeriod_hours"] == 0:
                all_typhoons_parsed_data[cyclone_id]["pastTrack"].append({
                    "lat": parsed_point["lat"],
                    "lon": parsed_point["lon"],
                    "time": parsed_point["time"],
                    "windSpeed_knots": parsed_point["windSpeed_knots"],
                    "windSpeed_ms": parsed_point["windSpeed_ms"],
                    "pressure_hpa": parsed_point["pressure_hpa"]
                })
                # 更新當前位置為最新的 00 小時點
                # 注意：這裡假設 00 小時預報是按時間順序出現的，最後一個就是當前位置
                all_typhoons_parsed_data[cyclone_id]["currentPosition"] = {
                    "lat": parsed_point["lat"],
                    "lon": parsed_point["lon"],
                    "time": parsed_point["time"],
                    "windSpeed_knots": parsed_point["windSpeed_knots"],
                    "windSpeed_ms": parsed_point["windSpeed_ms"],
                    "pressure_hpa": parsed_point["pressure_hpa"]
                }
            elif parsed_point["forecastPeriod_hours"] > 0:
                all_typhoons_parsed_data[cyclone_id]["forecastTrack"].append({
                    "lat": parsed_point["lat"],
                    "lon": parsed_point["lon"],
                    "time": parsed_point["time"],
                    "windSpeed_knots": parsed_point["windSpeed_knots"],
                    "windSpeed_ms": parsed_point["windSpeed_ms"],
                    "pressure_hpa": parsed_point["pressure_hpa"],
                    "forecastPeriod_hours": parsed_point["forecastPeriod_hours"]
                })
        else:
            print(f"警告: 無法解析 TCVITALS 檔案中第 {line_num + 1} 行的數據: {line.strip()}")
    
    # 選擇一個颱風來顯示。如果有多個，我們選擇 ID 最大的那個 (通常是最新生成的颱風)
    # 確保選中的颱風有數據
    if all_typhoons_parsed_data:
        # 找到 ID 最大的颱風 (例如 'WP152025' 會比 'WP142025' 大)
        selected_typhoon_id = max(all_typhoons_parsed_data.keys())
        selected_typhoon = all_typhoons_parsed_data[selected_typhoon_id]

        # 對 pastTrack 和 forecastTrack 進行時間排序，確保路徑正確
        selected_typhoon["pastTrack"].sort(key=lambda x: x["time"])
        selected_typhoon["forecastTrack"].sort(key=lambda x: x["time"])

        # 確保 currentPosition 是 pastTrack 中最新的點
        if selected_typhoon["pastTrack"]:
            selected_typhoon["currentPosition"] = selected_typhoon["pastTrack"][-1]
        else:
            selected_typhoon["currentPosition"] = None # 如果沒有歷史點，則沒有當前位置

        print(f"返回 JTWC 颱風數據: {selected_typhoon['name']} ({selected_typhoon['id']})")
        return jsonify({"success": True, "typhoon": selected_typhoon})
    else:
        # 如果 TCVITALS 檔案中沒有找到任何活躍熱帶氣旋數據
        print("NCEP TCVITALS 檔案中沒有找到活躍的熱帶氣旋數據。")
        return jsonify({"success": False, "message": "NCEP TCVITALS 檔案中沒有找到活躍的熱帶氣旋數據。"}), 200 # 返回 200 但說明沒有數據

except requests.exceptions.RequestException as e:
    print(f"獲取 NCEP TCVITALS 數據失敗: {e}")
    traceback.print_exc() # 打印完整的錯誤堆疊資訊
    return jsonify({"success": False, "message": f"無法從 NCEP FTP 獲取國際颱風資料: {e}"}), 500
except Exception as e:
    print(f"處理 NCEP TCVITALS 數據時發生錯誤: {e}")
    traceback.print_exc() # 打印完整的錯誤堆疊資訊
    return jsonify({"success": False, "message": f"處理國際颱風資料失敗: {e}"}), 500

if __name__ == '__main__':
    # 在本地運行時，將 host 設定為 '0.0.0.0' 以便外部訪問
    # 在 Vercel 上部署時，Vercel 會自動處理主機和端口
    app.run(debug=True, host='0.0.0.0', port=5000)
