    # 這是 Python Flask 框架的範例程式碼。
    # 您需要先安裝 Flask 和 requests 函式庫：
    # pip install Flask requests
    # 並將其部署到一個雲端伺服器環境中才能運行，例如 Vercel、Heroku 或您自己的伺服器。

    from flask import Flask, jsonify, request
    from flask_cors import CORS # 用於允許前端網頁存取，解決跨域問題
    import requests # 用於發送 HTTP 請求到外部 API
    import json # 導入 json 模組用於解析錯誤訊息
    import xml.etree.ElementTree as ET # 用於解析 XML 格式的資料 (例如氣象特報 RSS)

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
    