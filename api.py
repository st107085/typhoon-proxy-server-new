from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

app = Flask(__name__)
CORS(app) # 允許所有來源的跨域請求

# 中央氣象署颱風路徑 API (W-C0034-005)
CWA_TYPHOON_API_URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0034-005?Authorization=CWA-YOUR_API_KEY"
# 中央氣象署氣象特報 RSS
CWA_WARNINGS_RSS_URL = "https://alerts.ncdr.nat.gov.tw/JSONAtomFeed.ashx"

# 請替換成您在中央氣象署申請的 API Key
# CWA_API_KEY = "CWA-YOUR_API_KEY" # 這裡應該替換成您自己的 API Key

@app.route('/get-typhoon-data')
def get_typhoon_data():
    api_key = request.args.get('api_key') # 從前端獲取 API Key
    if not api_key:
        return jsonify({"success": False, "message": "API Key is missing."}), 400

    full_url = CWA_TYPHOON_API_URL.replace("CWA-YOUR_API_KEY", api_key)
    try:
        response = requests.get(full_url)
        response.raise_for_status() # 檢查 HTTP 錯誤
        data = response.json()
        return jsonify(data)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching CWA typhoon data: {e}")
        return jsonify({"success": False, "message": f"無法從中央氣象署獲取颱風資料: {e}"}), 500

@app.route('/get-cwa-warnings')
def get_cwa_warnings():
    try:
        response = requests.get(CWA_WARNINGS_RSS_URL)
        response.raise_for_status() # 檢查 HTTP 錯誤
        
        # 修正：使用 response.text 來獲取字串內容，避免編碼問題
        root = ET.fromstring(response.text)
        
        warnings = []
        # Atom Feed 的命名空間
        ns = {'atom': 'http://www.w3.org/2005/Atom', 
              'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}

        for entry in root.findall('atom:entry', ns):
            title = entry.find('atom:title', ns).text if entry.find('atom:title', ns) is not None else '無標題'
            pub_date_str = entry.find('atom:published', ns).text if entry.find('atom:published', ns) is not None else ''
            link_elem = entry.find('atom:link', ns)
            link = link_elem.get('href') if link_elem is not None else '#'

            # 嘗試從 content 或 summary 獲取描述
            description = '無描述'
            content_elem = entry.find('atom:content', ns)
            if content_elem is not None and content_elem.text:
                description = content_elem.text
            else:
                summary_elem = entry.find('atom:summary', ns)
                if summary_elem is not None and summary_elem.text:
                    description = summary_elem.text

            warnings.append({
                "title": title,
                "pubDate": pub_date_str,
                "description": description,
                "link": link
            })
        
        return jsonify({"success": True, "warnings": warnings})
    except requests.exceptions.RequestException as e:
        print(f"Error fetching CWA warnings: {e}")
        return jsonify({"success": False, "message": f"無法從中央氣象署獲取特報資料: {e}"}), 500
    except ET.ParseError as e:
        print(f"Error parsing CWA warnings XML: {e}")
        return jsonify({"success": False, "message": f"解析特報資料失敗: {e}"}), 500
    except Exception as e:
        print(f"An unexpected error occurred in get_cwa_warnings: {e}")
        return jsonify({"success": False, "message": f"處理特報資料時發生未知錯誤: {e}"}), 500


def parse_atcf_line(line):
    """
    解析 JTWC ATCF 格式的單行數據，提取關鍵資訊。
    ATCF 格式非常複雜，這裡只解析最常用的欄位。
    參考資料: https://www.nrlmry.navy.mil/atcf_web/docs/dm.txt
    """
    parts = line.strip().split(',')
    if len(parts) < 20: # ATCF 格式至少有 20 個欄位
        return None

    try:
        # 欄位索引 (基於 ATCF 格式定義，從 0 開始)
        # 欄位 0: Basin (盆地)
        # 欄位 1: Cyclone Number (氣旋編號)
        # 欄位 2: Date/Time (YYMMDDHH)
        # 欄位 3: Technique (預報技術)
        # 欄位 4: Technique Number
        # 欄位 5: Forecast Period (預報時效，00表示觀測)
        # 欄位 6: Latitude (緯度)
        # 欄位 7: Longitude (經度)
        # 欄位 8: Max Wind (最大風速，節)
        # 欄位 9: MSLP (中心氣壓，毫巴)
        # ... 還有很多其他欄位

        basin = parts[0].strip()
        cyclone_num = parts[1].strip()
        
        # 解析日期時間 (YYMMDDHH)
        dt_str = parts[2].strip()
        # ATCF 日期格式通常是 YYMMDDHH，例如 25071512 (2025年7月15日12時)
        # 需要補上世紀，假設是 20xx 年
        year_prefix = "20" if int(dt_str[0:2]) < 50 else "19" # 簡單判斷世紀
        full_dt_str = year_prefix + dt_str
        
        # 嘗試解析為 datetime 物件
        # 格式: YYYYMMDDHH (例如 2025071512)
        dt_object = datetime.strptime(full_dt_str, '%Y%m%d%H')
        time_iso = dt_object.isoformat() + 'Z' # 轉換為 ISO 8601 格式，UTC

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
        # 注意：ATCF 格式的欄位索引可能因版本而異，這裡假設為 27
        typhoon_name = parts[27].strip() if len(parts) > 27 else "UNKNOWN"
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
            "cycloneId": f"{basin}{cyclone_num}"
        }
    except (ValueError, IndexError) as e:
        print(f"Error parsing ATCF line: {line.strip()} - {e}")
        return None

@app.route('/get-international-typhoon-data')
def get_international_typhoon_data():
    """
    這個端點將從模擬的 JTWC ATCF 數據 URL 獲取數據，並進行解析。
    在實際應用中，這裡需要動態判斷要獲取哪個颱風的 ATCF 檔案。
    """
    # 模擬的 JTWC ATCF 數據 URL
    # 這是一個虛構的 URL，用於模擬從 JTWC 下載 ATCF 檔案
    # 在真實情況下，您需要找到 JTWC 實際的 ATCF 檔案路徑
    JTWC_ATCF_MOCK_URL = "https://raw.githubusercontent.com/wdfwfs/typhoon-info-hub/main/mock_jtwc_atcf_data.txt"
    # 注意：這個 URL 指向的是一個我在 GitHub 上為您準備的模擬 ATCF 數據文件
    # 它的內容是簡化的 ATCF 格式，包含一個虛構颱風的歷史和預測數據。

    try:
        response = requests.get(JTWC_ATCF_MOCK_URL)
        response.raise_for_status() # 檢查 HTTP 錯誤

        atcf_lines = response.text.strip().split('\n')
        
        typhoon_data = {
            "pastTrack": [],
            "forecastTrack": [],
            "currentPosition": None,
            "name": "未知颱風",
            "id": "UNKNOWN",
            "agency": "JTWC"
        }
        
        # 為了簡化，我們只處理第一個颱風的數據
        # 在真實應用中，您可能需要根據颱風 ID 過濾數據
        
        # 儲存所有解析後的數據點
        all_points = []

        for line in atcf_lines:
            parsed_point = parse_atcf_line(line)
            if parsed_point:
                all_points.append(parsed_point)
                # 假設第一個解析到的颱風就是我們要顯示的颱風
                if typhoon_data["id"] == "UNKNOWN":
                    typhoon_data["id"] = parsed_point["cycloneId"]
                    typhoon_data["name"] = parsed_point["typhoonName"]

        # 將數據點分類為歷史路徑和預測路徑
        # 00 小時預報時效通常表示當前觀測或歷史數據
        # 大於 00 的表示預測數據
        for point in all_points:
            if point["cycloneId"] == typhoon_data["id"]: # 確保是同一個颱風
                if point["forecastPeriod_hours"] == 0:
                    typhoon_data["pastTrack"].append({
                        "lat": point["lat"],
                        "lon": point["lon"],
                        "time": point["time"],
                        "windSpeed_knots": point["windSpeed_knots"],
                        "pressure_hpa": point["pressure_hpa"]
                    })
                    # 最後一個 00 小時的點作為當前位置
                    typhoon_data["currentPosition"] = {
                        "lat": point["lat"],
                        "lon": point["lon"],
                        "time": point["time"],
                        "windSpeed_knots": point["windSpeed_knots"],
                        "pressure_hpa": point["pressure_hpa"]
                    }
                elif point["forecastPeriod_hours"] > 0:
                    typhoon_data["forecastTrack"].append({
                        "lat": point["lat"],
                        "lon": point["lon"],
                        "time": point["time"],
                        "windSpeed_knots": point["windSpeed_knots"],
                        "pressure_hpa": point["pressure_hpa"],
                        "forecastPeriod_hours": point["forecastPeriod_hours"]
                        # JTWC ATCF 格式中的機率圓半徑 (PROB) 欄位較複雜，這裡暫不解析
                        # 如果需要，可以擴展 parse_atcf_line 函數來獲取
                    })
        
        # 如果沒有解析到任何數據，返回失敗
        if not typhoon_data["pastTrack"] and not typhoon_data["forecastTrack"]:
            return jsonify({"success": False, "message": "無法解析 JTWC 颱風數據或數據為空。"}), 500

        return jsonify({"success": True, "typhoon": typhoon_data})

    except requests.exceptions.RequestException as e:
        print(f"Error fetching JTWC ATCF data: {e}")
        return jsonify({"success": False, "message": f"無法從 JTWC 獲取原始颱風資料: {e}"}), 500
    except Exception as e:
        print(f"Error processing JTWC ATCF data: {e}")
        return jsonify({"success": False, "message": f"處理 JTWC 原始颱風資料失敗: {e}"}), 500

if __name__ == '__main__':
    app.run(debug=True)
