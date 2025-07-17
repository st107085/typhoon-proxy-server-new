# 這是 Python Flask 框架的範例程式碼。
# 您需要先安裝 Flask 和 requests 函式庫：
# pip install Flask requests
# 並將其部署到一個雲端伺服器環境中才能運行，例如 Vercel、Heroku 或您自己的伺服器。

from flask import Flask, jsonify, request
from flask_cors import CORS # 用於允許前端網頁存取，解決跨域問題
import requests # 用於發送 HTTP 請求到外部 API
import json # 導入 json 模組用於解析錯誤訊息
import xml.etree.ElementTree as ET # 用於解析 XML 格式的資料 (例如氣象特報 RSS 和 KML)
import csv # 導入 csv 模組用於解析 CSV 格式的資料
from datetime import datetime
import io # 用於處理字串作為檔案對象

app = Flask(__name__)
CORS(app) # 允許所有來源的跨域請求。在實際部署時，為了安全考量，
          # 建議限制只允許您網頁的特定網域存取，例如：CORS(app, resources={r"/*": {"origins": "https://your-website-domain.com"}})

# 中央氣象署開放資料平台 API Key
# **請務必將 'CWA-DA27CC49-2356-447C-BDB3-D5AA4071E24B' 替換為您自己申請的真實 API Key！**
# 這個 Key 同時用於 CWA 的颱風列表 API 和檔案 API。
# 如果您還沒有，請到中央氣象署開放資料平台申請：https://opendata.cwa.gov.tw/
CWA_API_KEY = 'CWA-DA27CC49-2356-447C-BDB3-D5AA4071E24B' 

# 中央氣象署颱風警報 API 端點
CWA_TYPHOON_API_URL = 'https://opendata.cwa.gov.tw/api/v1/rest/datastore/W-C0034-005'
# 中央氣象署 RSS 警報特報服務 (提供XML格式的最新氣象特報)
CWA_RSS_WARNING_URL = 'https://www.cwa.gov.tw/rss/Data/cwa_warning.xml'

# 國家科學及技術委員會開放資料平台 - 颱風相關數據索引 CSV URL (來自使用者提供)
NSTC_OPENDATA_CSV_URL = "https://mas.nstc.gov.tw/OPENDATA/GetFile?format=csv&serialno=454&fileodr=1"


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
        rss_response = requests.get(CWA_RSS_WARNING_URL)
        rss_response.raise_for_status() # 如果響應狀態碼不是 200，則拋出 HTTPError

        # 解析 XML 格式的 RSS 回應
        root = ET.fromstring(rss_response.content) # 使用 .content 獲取原始位元組，ET.fromstring 可以處理
        
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

def parse_kml_data(kml_text):
    """
    解析 KML 數據，提取颱風路徑資訊。
    預期 KML 包含多個 Placemark，每個 Placemark 可能代表一個預測模型路徑。
    """
    print("Parsing KML data...")
    try:
        root = ET.fromstring(kml_text)
    except ET.ParseError as e:
        print(f"Error parsing KML XML: {e}")
        return None
    
    # KML 命名空間
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    
    typhoon_paths = []

    # 遍歷所有的 Placemark
    placemarks = root.findall('.//kml:Placemark', ns)
    print(f"Found {len(placemarks)} Placemark elements in KML.")

    if not placemarks:
        print("No Placemark elements found in the KML. This might mean no active typhoon data.")
        return [] # 返回空列表，表示沒有找到路徑

    for i, placemark in enumerate(placemarks):
        print(f"Processing Placemark {i+1}...")
        name_element = placemark.find('kml:name', ns)
        name = name_element.text if name_element is not None else f"未知路徑 {i+1}"
        print(f"  Placemark Name: {name}")
        
        line_string_element = placemark.find('kml:LineString', ns)
        if line_string_element is not None:
            print(f"  Found LineString for {name}.")
            coordinates_element = line_string_element.find('kml:coordinates', ns)
            if coordinates_element is not None and coordinates_element.text:
                coords_text = coordinates_element.text.strip()
                # 移除多餘的空白字符，確保每個座標組都正確分割
                coords_text = ' '.join(coords_text.split()) 
                print(f"  Raw coordinates text: '{coords_text[:100]}...' (truncated)") # Log first 100 chars
                points = []
                # KML 座標格式是 longitude,latitude,altitude，以空格分隔
                for coord_str in coords_text.split(' '):
                    try:
                        # 分割經度、緯度、海拔
                        parts = coord_str.split(',')
                        if len(parts) >= 2: # 確保至少有經緯度
                            lon = float(parts[0]) 
                            lat = float(parts[1])
                            points.append({"lat": lat, "lon": lon}) # Leaflet 期望 latitude,longitude
                        else:
                            print(f"    Skipping malformed coordinate part (not enough parts): '{coord_str}'")
                    except ValueError:
                        print(f"    Skipping invalid coordinate part (parsing error): '{coord_str}'")
                        continue # 跳過格式不正確的座標
                
                if points:
                    print(f"  Successfully parsed {len(points)} points for {name}.")
                    typhoon_paths.append({
                        "name": name,
                        "path": points
                    })
                else:
                    print(f"  No valid points parsed for {name}.")
            else:
                print(f"  No coordinates element or text found for {name}.")
        else:
            print(f"  No LineString element found for {name}.")
    
    print(f"Total typhoon paths extracted: {len(typhoon_paths)}")
    return typhoon_paths


@app.route('/get-international-typhoon-data', methods=['GET'])
def get_international_typhoon_data():
    """
    這個端點將從 NSTC 開放資料平台獲取颱風數據索引 CSV，
    然後從 CSV 中找到實際的 KML 連結，並解析 KML 數據。
    """
    print("Received request for /get-international-typhoon-data (NSTC OpenData CSV)")

    try:
        # 1. 下載 NSTC 開放資料平台的 CSV 索引檔案
        print(f"Attempting to fetch CSV from: {NSTC_OPENDATA_CSV_URL}")
        # *** 修正點：為 NSTC_OPENDATA_CSV_URL 請求禁用 SSL 驗證 ***
        csv_response = requests.get(NSTC_OPENDATA_CSV_URL, timeout=15, verify=False) 
        csv_response.raise_for_status() # 檢查 HTTP 錯誤
        print(f"Successfully fetched CSV. Status: {csv_response.status_code}")
        
        # 使用 io.StringIO 將字串內容模擬成檔案，以便 csv.reader 讀取
        # 由於 CSV 可能包含 BOM，嘗試使用 'utf-8-sig' 或 'big5'
        csv_content = csv_response.text
        try:
            csv_file = io.StringIO(csv_content)
            reader = csv.reader(csv_file)
            header = next(reader) # 讀取標頭行
            print(f"CSV Header: {header}")
        except Exception as e:
            print(f"Initial CSV parsing failed (UTF-8). Trying Big5. Error: {e}")
            try:
                csv_file = io.StringIO(csv_content.encode('latin-1').decode('big5')) # 嘗試 Big5 解碼
                reader = csv.reader(csv_file)
                header = next(reader)
                print(f"CSV Header (Big5): {header}")
            except Exception as e_big5:
                print(f"CSV parsing failed for both UTF-8 and Big5. Error: {e_big5}")
                raise ValueError("無法正確解析 NSTC 開放資料平台 CSV 檔案編碼。")


        data_link_index = -1
        description_index = -1

        # 找到 '資料連結' 和 '說明' 欄位的索引
        try:
            data_link_index = header.index('資料連結')
            description_index = header.index('說明')
        except ValueError as e:
            print(f"CSV 標頭中未找到 '資料連結' 或 '說明' 欄位。錯誤: {e}")
            return jsonify({"success": False, "message": "NSTC 開放資料平台 CSV 格式不符預期 (缺少必要欄位)。"}), 500

        kml_data_url = None
        # 2. 遍歷 CSV 內容，尋找包含颱風路徑的連結
        for i, row in enumerate(reader):
            print(f"Processing CSV row {i+1}: {row}")
            if len(row) > max(data_link_index, description_index):
                description = row[description_index]
                if "颱風路徑" in description or "熱帶氣旋" in description or "預測路徑" in description or "Typhoon Track" in description:
                    kml_data_url = row[data_link_index]
                    print(f"在 CSV 中找到颱風路徑連結: {kml_data_url}")
                    break
            else:
                print(f"Skipping malformed CSV row {i+1} (not enough columns): {row}")
        
        if not kml_data_url:
            print("在 NSTC 開放資料平台 CSV 中未找到任何颱風路徑的資料連結。")
            return jsonify({"success": False, "message": "目前沒有活躍的國際颱風數據，或無法從來源獲取（NSTC：未找到路徑連結）。"}), 200

        # 3. 從找到的 KML 連結下載實際的颱風數據
        print(f"嘗試從找到的 KML URL 獲取數據: {kml_data_url}")
        # *** 修正點：為 KML_data_url 請求禁用 SSL 驗證 ***
        kml_response = requests.get(kml_data_url, timeout=30, verify=False) 
        kml_response.raise_for_status() # 檢查 HTTP 錯誤
        print(f"Successfully fetched KML from {kml_data_url}. Status: {kml_response.status_code}")
        
        kml_data = kml_response.text
        
        if not kml_data.strip():
            print(f"從 {kml_data_url} 獲取的 KML 數據為空。")
            return jsonify({"success": False, "message": "從 NSTC 獲取到 KML 數據，但內容為空。"}), 200

        # 4. 解析 KML 數據
        typhoon_paths = parse_kml_data(kml_data)
        
        if typhoon_paths:
            print(f"成功從 {kml_data_url} 獲取並解析國際颱風數據。")
            return jsonify({"success": True, "typhoonPaths": typhoon_paths})
        else:
            print("從獲取的 KML 數據中未找到任何颱風路徑資訊。")
            return jsonify({"success": False, "message": "從 NSTC 獲取到 KML 數據，但未找到任何颱風路徑資訊。"}), 200

    except requests.exceptions.Timeout:
        print(f"獲取 NSTC 數據超時。")
        return jsonify({"success": False, "error": "獲取國際颱風數據超時，請稍後再試。"}), 504
    except requests.exceptions.RequestException as e:
        print(f"從 NSTC 獲取數據失敗: {e}")
        return jsonify({"success": False, "error": f"無法從 NSTC 獲取國際颱風數據: {str(e)}"}), 500
    except ET.ParseError as e:
        print(f"解析 KML 數據失敗: {e}. 原始 KML 開頭: {kml_data[:500] if 'kml_data' in locals() else 'N/A'}")
        return jsonify({"success": False, "error": f"解析國際颱風 KML 數據失敗: {str(e)}"}), 500
    except ValueError as e: # 捕獲 CSV 編碼或格式錯誤
        print(f"CSV 處理錯誤: {e}")
        return jsonify({"success": False, "error": f"處理 NSTC CSV 檔案時發生錯誤: {str(e)}"}), 500
    except Exception as e:
        print(f"處理國際颱風數據時發生未知錯誤: {e}")
        return jsonify({"success": False, "error": f"處理國際颱風數據時發生未知錯誤: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True)
