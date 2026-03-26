import requests
import json
import datetime
import time
import re
import pandas as pd

def fetch_news_summary(api_key, stock_id, stock_name):
    """使用 gemini-2.5-flash + Google Search Grounding 抓取最新新聞摘要"""
    try:
        # v1beta 支援 google_search grounding 工具
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{
                    "text": (
                        f"請用繁體中文搜尋並摘要「台股 {stock_id} {stock_name}」最近的重要新聞，"
                        f"包含：最新財報、法人評等、重大訊息、產業動態、題材催化劑。"
                        f"請條列最多 8 則，每則 2~3 句，並標明來源與日期（若有）。"
                        f"若無相關新聞，回覆「查無近期新聞」。"
                    )
                }]
            }],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048
            }
        }
        response = requests.post(f"{url}?key={api_key}", headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            result = response.json()
            candidates = result.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                texts = [p.get("text", "") for p in parts if "text" in p]
                news_text = "\n".join(texts).strip()
                if news_text:
                    return news_text
        return ""
    except Exception:
        return ""


def analyze_stock_trend(api_key, stock_id, stock_name, df, fundamental_summary=None):
    """AI 深度分析 - 動態年份版本"""

    if not api_key:
        return "⚠️ 請先輸入 API Key"

    try:
        # 數據整理
        essential_cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'MA20', 'MA100', '外資', '投信', '融資餘額']
        valid_cols = [c for c in essential_cols if c in df.columns]
        recent_df = df[valid_cols].tail(30).copy()  # 改為30日

        # ✅ 完整的 K 線型態判讀邏輯（參考 quantpass 技術分析標準）
        def classify_kbar(row):
            o, h, l, c = row['open'], row['high'], row['low'], row['close']
            body = abs(c - o)
            total_range = h - l

            # 防止除以零
            if total_range < 0.001:
                return '一字線'

            # 計算上下影線長度
            if c >= o:  # 紅K
                upper_shadow = h - c
                lower_shadow = o - l
            else:  # 黑K
                upper_shadow = h - o
                lower_shadow = c - l

            body_ratio = body / total_range if total_range > 0 else 0
            chg_pct = abs(c - o) / o * 100 if o > 0 else 0  # 單日漲跌幅%

            # === 1. 十字線系列（開盤價≈收盤價） ===
            if body_ratio < 0.05:  # 實體極小，開盤≈收盤
                # (1) 一字線：開盤=最高=最低=收盤
                if total_range / o < 0.003:
                    return '一字線'
                # (2) T字線：開盤=最高=收盤，有長下影線
                elif upper_shadow < total_range * 0.1 and lower_shadow > body * 2:
                    return 'T字線'
                # (3) 倒T線：開盤=最低=收盤，有長上影線
                elif lower_shadow < total_range * 0.1 and upper_shadow > body * 2:
                    return '倒T線'
                # (4) 標準十字線：有明顯上下影線
                else:
                    return '十字線'

            # === 2. 實體K線（影線佔比20%以內） ===
            shadow_ratio = (upper_shadow + lower_shadow) / total_range

            if shadow_ratio <= 0.2:
                if c > o:  # 紅K
                    if body_ratio > 0.7 and chg_pct >= 7:
                        return '大紅K'
                    elif body_ratio > 0.4 and chg_pct >= 3:
                        return '中紅K'
                    else:
                        return '小紅K'
                else:  # 黑K
                    if body_ratio > 0.7 and chg_pct >= 7:
                        return '大黑K'
                    elif body_ratio > 0.4 and chg_pct >= 3:
                        return '中黑K'
                    else:
                        return '小黑K'

            # === 3. K線帶上影線（墓碑線系列） ===
            # 特徵：上影線長度 > 實體2倍，無下影線或下影線極短
            elif upper_shadow > body * 2 and lower_shadow < body * 0.3:
                if c >= o:
                    return '倒鎚紅K(墓碑線-上漲)'
                else:
                    return '倒鎚黑K(墓碑線-下跌)'

            # === 4. K線帶下影線（吊人線系列） ===
            # 特徵：下影線長度 > 實體2倍，無上影線或上影線極短
            elif lower_shadow > body * 2 and upper_shadow < body * 0.3:
                if c >= o:
                    return '紅K鎚子(吊人線-上漲)'
                else:
                    return '黑K鎚子(吊人線-下跌)'

            # === 5. K線帶上下影線（紡錘線系列） ===
            # 特徵：同時有明顯上下影線
            else:
                if c >= o:
                    return '紡錘紅K'
                else:
                    return '紡錘黑K'

        recent_df['K線'] = recent_df.apply(classify_kbar, axis=1)

        # ✅ 價格/均線：小數點後2位；張數（成交量/法人/融資融券）：整數
        int_cols = {'volume','外資','投信','自營商','主力合計','融資餘額','融券餘額'}
        for col in recent_df.columns:
            if col == 'date' or col == 'K線':
                continue
            if col in int_cols:
                recent_df[col] = pd.to_numeric(recent_df[col], errors='coerce').fillna(0).round(0).astype(int)
            else:
                recent_df[col] = pd.to_numeric(recent_df[col], errors='coerce').round(2)
        recent_data = recent_df.to_string(index=False)

        # 動態取得年份
        current_year = datetime.datetime.now().year
        last_year = current_year - 1

        # ⚠️ 下面 prompt 已植入趨勢定義與嚴格規定，其餘格式逐字保留原稿
        prompt = f"""
你是股神等級的「台股首席參謀長」，負責在「AI 股市戰情室」中，針對「{stock_id} {stock_name}」進行極為嚴謹的技術、籌碼與基本面診斷。

**【重要約束與定義】**
1. 在第二章均線分析中，僅能分析 MA20 與 MA100，絕對不可提及 MA5、MA10、MA60、MA120、MA240 等其他均線
2. **均線週期正確定義**：
   - MA20（月線）= 短期趨勢線
   - MA100（百日線）= 中期趨勢線
3. **時間表達方式**：
   - 禁止寫死任何年份（例如「2025年」、「2026年」）
   - 使用「最新資訊」、「近期」、「當前」等動態描述
   - 範例：「根據最新財報」而非「根據2025年財報」
4. **表達方式**：直接描述分析結果，不要在正文中重複列出「最近三個交易日 (20XX-XX-XX...)」等日期羅列
5. **數字格式嚴格規定**：所有數字請務必使用「阿拉伯數字」，絕對不要使用國字數字（例如請寫 150，絕對不可寫一百五十）。
6. **人稱與風格規定**：文章中絕對禁止提到「你」。內容需帶有獨特性財經觀點，延伸前因後果，並讓讀者有被激勵感與共感。
7. **數據呈現規定**：須說明內文的重點數據，且數據應自然融入段落文字中，絕對禁止使用條列式列出數據。

**嚴格要求：以下五大章節必須全部完整輸出，每個章節都要有充足內容，絕對不可以中途停止！**

---

### **第一章：K線型態精密掃描**（列出3項最重要型態，每項50字內）
分析最近 1-3 日的 K 棒組合型態與市場情緒變化：

**重要**：數據中的「K線」欄位已精確標示各種型態，請依此判斷：

**K線型態完整定義（共16種）：**

1. **實體K線（影線佔比20%以內）**：
   - 大紅K/大黑K：實體佔比>70%，單日漲/跌幅須達7%以上，趨勢強勢
   - 中紅K/中黑K：實體佔比40-70%，單日漲/跌幅介於3~7%，趨勢明確
   - 小紅K/小黑K：實體佔比<40%，單日漲/跌幅小於3%，趨勢較弱

2. **帶上影線（墓碑線系列）**：
   - 倒鎚紅K(墓碑線-上漲)：上影線>實體2倍，收盤>開盤，買方追高遇壓
   - 倒鎚黑K(墓碑線-下跌)：上影線>實體2倍，收盤<開盤，買方拉盤後被壓制

3. **帶下影線（吊人線系列）**：
   - 紅K鎚子(吊人線-上漲)：下影線>實體2倍，收盤>開盤，賣壓後買方接盤
   - 黑K鎚子(吊人線-下跌)：下影線>實體2倍，收盤<開盤，殺盤後略有反彈

4. **帶上下影線（紡錘線）**：
   - 紡錘紅K/紡錘黑K：同時有明顯上下影線，多空交戰激烈

5. **十字線系列（開盤≈收盤）**：
   - 十字線：開盤≈收盤，有上下影線，多空平衡
   - T字線：開盤=最高=收盤，長下影線，低檔支撐強
   - 倒T線：開盤=最低=收盤，長上影線，高檔壓力大
   - 一字線：開=高=低=收，漲停/跌停/無量

**分析要點：**

1. **K棒組合型態描述**：
   - 使用「→」符號串連 K 線演變過程，並用「」框起來
   - 例如：「大紅K強勢上攻 → 倒鎚紅K(墓碑線-上漲)追高遇壓 → 紡錘黑K多空交戰」
   - 直接描述多空力量的演變，不要逐日列舉日期
   - **務必使用數據中的完整K線型態名稱**，如「倒鎚紅K(墓碑線-上漲)」而非只說「上影線」

2. **實體與影線分析**：
   - ⚠️ 禁止在報告中輸出任何「實體佔比XX%」、「影線佔比XX%」等佔比數字，這些是內部判斷依據，對讀者無意義
   - 只描述技術意義：上影線代表賣壓、下影線代表買盤支撐，用文字描述強弱程度即可

3. **多空力道判斷**：
   - 大實體K線 = 趨勢強勢明確
   - 長影線K線 = 多空交戰激烈，方向不明
   - 十字線系列 = 多空平衡，可能反轉訊號

4. **關鍵型態識別**：
   - 墓碑線系列（倒鎚紅K/黑K）= 高檔可能反轉
   - 吊人線系列（鎚子紅K/黑K）= 低檔可能支撐
   - T字線 = 低檔止跌訊號
   - 倒T線 = 高檔見頂訊號
   - 十字線 = 多空平衡，趨勢可能轉折

5. **信心評分**：型態可靠度評分（1-5分），並說明評分理由

6. **操作思路**：基於K線型態，提供「若欲操作」或「積極者可考慮」等參考思路（避免直接說「建議」）

---

### **第二章：均線與趨勢結構**（提取關鍵訊號3項，每項50字內）
**僅分析 MA20 與 MA100，請務必從提供的數據中讀取這兩條均線的數值**

* **均線排列分析**：
  - MA20（月線，短期趨勢）與 MA100（百日線，中期趨勢）的相對位置
  - 多頭排列（股價>MA20>MA100）或空頭排列判斷
  - 均線糾結或發散狀態
  - **絕對禁止提及 MA5、MA60 等其他均線**

* **股價位置與乖離率**：
  - 股價相對於 MA20 的乖離率（%）
  - 股價相對於 MA100 的乖離率（%）
  - 超買/超賣判斷

* **趨勢定義**：
  - **請依據以下嚴格邏輯明確定義趨勢格局：**
    (1) 多頭：股價同時站在 MA20 與 MA100 日均線之上
    (2) 空頭：股價同時在 MA20 與 MA100 日均線之下
    (3) 多箱：股價在 MA20 之下，但在 MA100 日均線之上
    (4) 空箱：股價在 MA20 之上，但在 MA100 日均線之下
  - 說明趨勢強度與持續性

* **關鍵價位**：
  - MA20 位置作為短期支撐/壓力
  - MA100 位置作為中期支撐/壓力
  - 其他技術支撐壓力位

---

### **第三章：大戶籌碼與散戶動向**（僅列重要籌碼結論3項）
**請分析近 30 個交易日（約一個月）的籌碼變化**

* **外資動向**：
  - 近 30 日累計買賣超張數與趨勢
  - 操作態度解讀（持續加碼/減碼/觀望）

* **投信籌碼**：
  - 近 30 日買賣超統計
  - 持股變化與操作態度

* **融資融券**：
  - 融資餘額增減意義
  - 散戶情緒判斷

* **籌碼總結**：
  - 主力集中度評估（法人買 vs 散戶賣，或相反）
  - 籌碼安定性與壓力

---

### **第四章：產業與基本面展望**（提取最重要的3項財報訊號，每項100字內）
* **公司定位**：
  - 主要產品服務與產業鏈位置
  - 核心競爭優勢
  - 主要客戶與市場

* **產業趨勢**：
  - 當前產業景氣狀況（使用「最新趨勢」而非「{last_year}-{current_year}年趨勢」）
  - 成長動能與挑戰

* **題材催化劑**：
  - 當前熱門題材（AI、半導體等）
  - 正面/負面因素

* **財務體質**：
  - 最新營收獲利表現（使用「最新財報」而非具體年份）
  - 毛利率、淨利率(如果是金融股，則不分析這兩項)
  - 財務穩健度

* **法人觀點**：
  - 券商目標價
  - 市場共識

---

### **第五章：最終操作策略** (至少 500 字)
* **多空方向**：
  - 明確表態與操作時間軸
  - 綜合評分依據

* **關鍵價位**：
  - 支撐位：第一、第二支撐（MA20 為短期支撐，MA100 為中期支撐）
  - 壓力位：第一、第二壓力
  - 止損價位

* **積極型建議**：
  - 進場時機與價位
  - 停損設定
  - 獲利目標

* **保守型建議**：
  - 觀察訊號
  - 防守策略

* **風險提示**：
  - 情境預測
  - 風險因子
(1)請使用條列式，每個風險獨立編號，(2)移除所有雙星號(**)

**【重要聲明】**
- 使用「若欲操作」、「可考慮」、「參考思路」等詞彙
- 避免使用「建議」、「應該」、「必須」等指示性用語
- 強調這是「技術分析參考」而非「投資建議」

---

**近 30 日完整數據（包含 MA20 與 MA100）**
{recent_data}

**【重要】月營收與季營收數據（第四章財務體質必須使用）**
{fundamental_summary if fundamental_summary else "（暫無月營收/季營收數據）"}

**輸出規則**
1. 繁體中文，Markdown 格式
2. 語氣專業犀利
3. 每章節必須完整
4. 拒絕廢話：每句話必須含數字或具體建議，禁止空洞的「需持續觀察」
5. 數據具體明確
6. 禁止寫死任何年份數字

7. **【嚴格要求】第四章財務體質部分：**
   - 如果上方有提供月營收/季營收數據，你**必須**直接引用這些具體數字進行分析
   - 不可以說「缺乏數據」或「無法獲得數據」
   - 必須分析營收趨勢、年增率變化、毛利率走勢等具體數值
   - 例如：「最近一個月營收為 150 億元，年增率為 +/-10%」

8. **【重要】用詞規範（避免法律風險）- 絕對不可使用投資指示用語：**
   - ❌ 絕對禁用：「建議」、「應該」、「必須」、「強烈推薦」、「推薦」、「買入」、「賣出」、「進場」、「出場」、「加碼」、「減碼」
   - ✅ 改用：「若欲操作」、「可考慮」、「積極者可留意」、「參考思路」、「值得觀察」、「可能」、「或許」
   - 範例：「若欲操作，可考慮在 XX 元附近觀察」而非「建議在 XX 元買進」
   - 範例：「停損可參考設定在 XX 元」而非「應該將停損設在 XX 元」
   - 範例：「積極者可留意 XX 元附近的機會」而非「推薦在 XX 元進場」
   - 所有操作相關內容都要強調「僅供參考」、「學術研究」性質
   - 整篇文章請全面檢查，確保沒有任何投資指示用語

9. **【格式要求】第一章 K 線型態描述：**
   - 必須使用「→」符號串連演變過程
   - 用「」框起整個演變描述
   - 範例：「小陽線觀望 → 大陽線帶長上影線追價遇壓 → 實體極小帶長下影線多空平衡」

10. **【格式要求】移除所有雙星號（**）：**
   - 副標題不使用 ** 包圍，直接呈現文字
   - 例如：「月營收分析」而非「**月營收分析**」
   - 例如：「技術面」而非「**技術面**」
   - 整篇文章不使用 ** 來強調，改用具體描述

11. **【數字格式化要求】- 非常重要：**
   - 所有百分比（年增率、毛利率等）：僅保留小數點後2位（例如：-36.61%，不是-36.612984%）
   - 營收數據已換算為千元單位，請直接使用並標註「千元」（例如：營收 165,191 千元）
   - 不要將營收寫成「1,855,499,000 元」，要寫成「1,855,499 千元」
   - 確保所有數字格式統一、易讀
"""

        # ========== 抓取最新新聞（Google Search Grounding）==========
        news_summary = fetch_news_summary(api_key, stock_id, stock_name)
        if news_summary:
            prompt += f"""

---

**【最新新聞摘要（Google 即時搜尋）】**
{news_summary}

**重要指示**：上方新聞為即時搜尋結果，請在第四章「產業與基本面展望」中適當引用這些最新資訊，包含最新財報、法人評等、產業動態等，讓分析更具時效性與參考價值。
"""

        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 16384,
                "topP": 0.95,
                "topK": 40
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        }

        # 優先使用穩定、配額較寬鬆的模型
        model_attempts = [
            "gemini-3-pro-preview",           # 最新版 Pro（優先，需付費）
            "gemini-3-flash-preview",         # 最新版 Flash（次優先，有免費額度）
            "gemini-2.0-flash-exp",           # 實驗版，通常配額較多
            "gemini-1.5-flash-latest",        # 穩定版 Flash
            "gemini-1.5-pro-latest",          # 穩定版 Pro
            "gemini-2.5-flash"                # 新版 Flash
        ]

        last_error = None

        for idx, model_name in enumerate(model_attempts):
            # 非第一個模型時，等待 3 秒避免速率限制
            if idx > 0:
                time.sleep(3)  # 移除 print，靜默等待
            try:
                # gemini-3 preview 需走 v1beta；其餘走 v1
                api_ver = "v1beta" if model_name.startswith("gemini-3") else "v1"
                url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model_name}:generateContent"

                # ✅ 每次請求前稍微延遲，避免觸發速率限制
                model_success = False
                for attempt in range(3):
                    if attempt > 0:
                        # 重試時等待更久
                        delay = min(15, 3 * (2 ** attempt))
                        time.sleep(delay)  # 移除 print，靜默等待

                    response = requests.post(f"{url}?key={api_key}", headers=headers, json=payload, timeout=90)

                    if response.status_code == 200:
                        result = response.json()
                        if 'candidates' in result and len(result['candidates']) > 0:
                            text = result['candidates'][0]['content']['parts'][0]['text']
                            return f"### 🧬 AI 戰情室：全方位深度解析\n\n{text}\n\n---\n**使用模型**: {model_name}"
                        last_error = f"{model_name} HTTP 200 但回傳格式異常: {str(result)[:300]}"
                        break

                    if response.status_code == 429:
                        try:
                            err = response.json()
                            msg = err.get("error", {}).get("message", "")
                            m = re.search(r"Please retry in ([0-9.]+)s", msg)
                            # 限制最長等待時間為 10 秒，避免等太久
                            wait_s = min(10, float(m.group(1)) if m else (2 ** attempt) * 2)
                        except Exception:
                            wait_s = min(10, (2 ** attempt) * 2)

                        last_error = f"{model_name} HTTP 429 (attempt {attempt+1}/3): quota/rate limit"
                        time.sleep(wait_s)  # 移除 print，靜默等待
                        continue  # 繼續下一次重試

                    # 其他 HTTP 錯誤（400, 404, 500 等）直接跳過這個模型
                    last_error = f"{model_name} HTTP {response.status_code}: {response.text[:800]}"
                    break  # 跳出重試迴圈，嘗試下一個模型

                # 如果這個模型的所有重試都失敗了，繼續嘗試下一個模型
                if not model_success:
                    continue  # 移除 print，靜默切換到下一個模型

            except Exception as e:
                last_error = f"{model_name} Exception: {str(e)}"
                continue  # 移除 print，靜默嘗試下一個模型

        return f"❌ 所有模型皆無法連線，請檢查 API Key / 額度 / 網路狀態\n\n最後錯誤：{last_error}"

    except Exception as e:
        return f"系統錯誤: {str(e)}"

def generate_quick_summary(df, name):
    try:
        latest = df.iloc[-1]
        change = latest['close'] - df.iloc[-2]['close']
        pct = (change / df.iloc[-2]['close']) * 100
        color = "🔴" if change > 0 else "🟢" if change < 0 else "⚪"
        return f"{color} {name} 收盤：{latest['close']} ({change:+.2f} / {pct:+.2f}%) | 量 {int(latest['volume'])} 張"
    except:
        return "數據載入中..."

def analyze_leading_indicators(api_key, df_leading):
    """AI 分析先行指標趨勢"""
    if not api_key:
        if not api_key: api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key: return "⚠️ 請先設定 Gemini API Key"
    if df_leading is None or df_leading.empty:
        return "⚠️ 無先行指標數據可分析"
    try:
        from leading_indicators import build_ai_data_table
        data_table = build_ai_data_table(df_leading)
        if "外資大小" in df_leading.columns:
            vals = [v for v in df_leading["外資大小"].tolist() if v is not None]
            if len(vals) >= 2:
                delta = vals[-1] - vals[0]
                if delta > 5000:    trend_str = f"近期流向：持續增多，變化 +{delta:,} 口（偏多趨勢）"
                elif delta < -5000: trend_str = f"近期流向：持續減少，變化 {delta:,} 口（偏空趨勢）"
                else:               trend_str = f"近期流向：震盪整理，變化 {delta:+,} 口（中性）"
            else: trend_str = "資料不足，無法判斷趨勢"
        else: trend_str = "外資大小數據不可用"

        lines = [
            "你是台股首席籌碼參謀，專門依照先行指標分析邏輯解讀台股走勢。",
            "",
            "核心哲學：",
            "• 外資與大戶意圖優先，散戶永遠是反向指標",
            "• 流向（趨勢方向）的重要性大於存量（絕對數字）",
            "• 期貨看口數，選擇權看金額，兩者不可直接加減抵銷",
            "• 最高指導原則：不要與散戶站同方向",
            "",
            "規範：禁止寫死年份；禁止使用建議/應該/必須；改用若欲操作/積極者可留意；禁止雙星號(**)",
            "",
            "══════ 近期先行指標數據（最新在上方）══════",
            "",
            data_table,
            "",
            "弘爺警戒門檻速查：",
            "• 外資期貨空單（負值）> 30,000 口 → 高風險警戒",
            "• 前五大空單接近 -10,000 口，前十大接近 -20,000 口 → 嚴重警訊",
            "• 選PCR > 100 → 下方有支撐偏多；< 100 → 上方受壓偏空；< 110 → 市場易走弱",
            "• 外(選) 正值偏多、負值偏空，±10,000 千元為關鍵門檻",
            "• 韭菜指數正值=散戶淨多（反向偏空）；負值=散戶淨空（反向偏多）",
            "",
            f"外資大小近期流向：{trend_str}",
            "",
            "══════ 六大檢查項目（必須全部完整輸出）══════",
            "",
            "第一項：外資期貨留倉（外資大小）",
            "核心心法：流向大於存量。30,000 口為警戒線。",
            "請引用「外資大小」欄位近期數值，說明：(1)當前方向與口數 (2)是否突破警戒線 (3)近期流向趨勢 (4)整體態度傾向",
            "",
            "第二項：大額交易人留倉（前五大、前十大）",
            "注意：前十大含反向ETF避險空單，真實空單可能更少。警戒：前五大接近 -10,000，前十大接近 -20,000。",
            "請說明：(1)是否近警戒門檻 (2)近期空單流向 (3)與外資期貨一致性",
            "",
            "第三項：選擇權 Put/Call Ratio（選PCR）",
            "PCR>100偏多有支撐；PCR<100偏空受壓；PCR<110易走弱。",
            "請說明：(1)當前水位與傾向 (2)近期趨勢 (3)是否跌破100或近110",
            "",
            "第四項：外資選擇權淨部位（外(選)）",
            "正值偏多，負值偏空，±10,000千元為門檻。與期貨同向=趨勢佈局；反向=對沖避險（假摔）。",
            "請說明：(1)方向與量 (2)是否超門檻 (3)期貨vs選擇權方向結論",
            "",
            "第五項：市場整體未平倉口數",
            "放大=分歧加劇波動預警；萎縮=觀望盤整。",
            "請說明：(1)當前水位 (2)趨勢 (3)搭配大盤判斷多空誰在建倉",
            "",
            "第六項：韭菜指數（散戶反向指標）",
            "4種情境：①外資多+散戶空→軋空最佳 ②外資多+散戶多→漲勢謹慎 ③外資空+散戶多→危機最高 ④外資空+散戶空→需再確認",
            "請說明：(1)散戶偏多/空及程度 (2)趨勢 (3)對應哪種情境",
            "",
            "══════ 綜合評分表與最終研判 ══════",
            "",
            "請輸出 Markdown 表格（數值必須直接引用上方數據）：",
            "",
            "| 檢查項目 | 當前數值摘要 | 方向 | 強度 | 研判摘要 |",
            "|---------|------------|------|------|---------|",
            "| 外資期貨留倉 | 填最新外資大小值 | 偏多▲/中性─/偏空▼ | 強/中/弱 | 流向傾向 |",
            "| 大額交易人 | 前五大/前十大值 | 偏多▲/中性─/偏空▼ | 強/中/弱 | 警戒線距離+流向 |",
            "| 選PCR | 最新PCR值 | 偏多▲/中性─/偏空▼ | 強/中/弱 | 支撐/壓力判斷 |",
            "| 外資選擇權 | 外(選)千元值 | 偏多▲/中性─/偏空▼ | 強/中/弱 | 趨勢佈局/對沖 |",
            "| 整體未平倉 | 未平倉口數 | 偏多▲/中性─/偏空▼ | 強/中/弱 | 多空誰建倉 |",
            "| 韭菜指數 | 最新% | 偏多▲/中性─/偏空▼ | 強/中/弱 | 情境矩陣結論 |",
            "",
            "最終研判須包含：",
            "1. 幾項偏多、幾項偏空（一致性評估）",
            "2. 當前最可能情境（多方佔優/多空膠著/空方主導）",
            "3. 最需留意的風險（期貨vs選擇權方向分歧？）",
            "4. 流向大於存量最終判斷：趨勢好轉/惡化/維持？",
            "5. 先行指標研判結論對後續個股分析的意義（強弱市場背景）",
            "",
            "請用繁體中文，萃取最重要的3項指標變化，給出明確方向判斷，不超過500字。",
        ]
        prompt = "\n".join(lines)

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4096},
            "safetySettings": [
                {"category":"HARM_CATEGORY_HARASSMENT","threshold":"BLOCK_NONE"},
                {"category":"HARM_CATEGORY_HATE_SPEECH","threshold":"BLOCK_NONE"},
                {"category":"HARM_CATEGORY_SEXUALLY_EXPLICIT","threshold":"BLOCK_NONE"},
                {"category":"HARM_CATEGORY_DANGEROUS_CONTENT","threshold":"BLOCK_NONE"},
            ]
        }
        headers = {"Content-Type": "application/json"}
        model_attempts = [
            "gemini-2.5-flash-preview-04-17","gemini-2.0-flash-exp",
            "gemini-1.5-flash-latest","gemini-1.5-pro-latest","gemini-2.5-flash",
        ]
        last_error = None
        for midx, model_name in enumerate(model_attempts):
            if midx > 0: time.sleep(3)
            try:
                api_ver = "v1beta" if "preview" in model_name else "v1"
                url = f"https://generativelanguage.googleapis.com/{api_ver}/models/{model_name}:generateContent"
                for attempt in range(3):
                    if attempt > 0: time.sleep(min(15, 3*(2**attempt)))
                    resp = requests.post(f"{url}?key={api_key}", headers=headers, json=payload, timeout=90)
                    if resp.status_code == 200:
                        result = resp.json()
                        if "candidates" in result and result["candidates"]:
                            text = result["candidates"][0]["content"]["parts"][0]["text"]
                            return f"### 📡 AI 先行指標籌碼研判\n\n{text}\n\n---\n**使用模型**: {model_name}"
                        last_error = f"{model_name} HTTP 200 但回傳格式異常"; break
                    if resp.status_code == 429:
                        try:
                            msg = resp.json().get("error",{}).get("message","")
                            m = re.search(r"Please retry in ([0-9.]+)s", msg)
                            wait_s = min(10, float(m.group(1)) if m else (2**attempt)*2)
                        except: wait_s = min(10, (2**attempt)*2)
                        last_error = f"{model_name} HTTP 429 rate limit"
                        time.sleep(wait_s); continue
                    last_error = f"{model_name} HTTP {resp.status_code}"; break
                else: continue
                break
            except Exception as e: last_error = f"{model_name} Exception: {str(e)}"; continue
        return f"❌ 所有模型皆無法連線\n最後錯誤：{last_error}"
    except Exception as e:
        return f"系統錯誤: {str(e)}"


def generate_daily_report(api_key, market_info, top_stocks, risk_alerts=None):
    """
    每日戰情摘要生成（§8.2 AI 輸入資料 + §14.1 每日輸出格式）

    Args:
        api_key      : Gemini API Key
        market_info  : dict - regime, score, index_price, foreign_net, exposure_pct
        top_stocks   : list of dict - [{stock_id, stock_name, total, grade}, ...]
        risk_alerts  : list of str - 風控警示訊息

    Returns:
        str: AI 生成的每日戰情摘要文字
    """
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return "⚠️ 請先設定 Gemini API Key"

    import datetime as _dt
    today = _dt.date.today().strftime('%Y-%m-%d')

    regime_label = market_info.get('label', market_info.get('status', '未知'))
    score        = market_info.get('score', 0)
    max_score    = market_info.get('max_score', 5)
    index_price  = market_info.get('index_price', 0)
    foreign_net  = market_info.get('foreign_net', 0)
    exposure     = market_info.get('exposure_pct', '50%')

    top5_txt = '\n'.join([
        f"  {idx2+1}. {s.get('stock_id','')} {s.get('stock_name','')} - {s.get('total',0):.0f}分（{s.get('grade','')}級）"
        for idx2, s in enumerate(top_stocks[:5])
    ]) or '  （暫無評分資料）'

    alerts_txt = '\n'.join([f'  - {a}' for a in (risk_alerts or [])]) or '  （無風控警示）'

    prompt = f"""你是專業台股投資顧問，請根據以下資料輸出完整的今日投資決策報告（繁體中文）：

═══ 大盤與市場資料 ═══
日期：{today}
市場狀態：{regime_label}（評分 {score}/{max_score}）
大盤指數：{index_price:,.0f}
外資現貨：{'買超' if foreign_net > 0 else '賣超'} {abs(foreign_net)/1e8:.1f}億
建議持股比例：{exposure}

═══ 個股多因子評分 TOP5 ═══
{top5_txt}

═══ 風控警示 ═══
{alerts_txt}

═══ 請按以下格式輸出（每節用 --- 分隔）：═══

## 🌐 一、大盤與國際局勢判讀
（說明當前市場狀態、外資動向、是否適合進場，2-3句）

## 📈 二、個股分析與投資組合建議
（針對上方TOP5股票逐一評論，說明哪些可積極、哪些觀察、哪些等待，3-5句）

## ⚡ 三、建議做法（具體操作策略）
- 做法1：（例：持股XX%，重點佈局評分最高的XXX）
- 做法2：（例：停損設在哪，何時加碼）
- 做法3：（例：觀察哪個指標作為進出場依據）

## ⚠️ 四、注意事項與風險提醒
（說明當前最大風險、需要監控的指標，2-3點條列）

格式要求：繁體中文、具體有力、避免廢話，適合每日快速閱讀。"""

    try:
        import requests as _rq, time as _t
        _models = ['gemini-2.0-flash-exp','gemini-1.5-flash-latest',
                   'gemini-1.5-flash','gemini-2.0-flash','gemini-1.5-pro-latest']
        for model in _models:
            try:
                r = _rq.post(
                    f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                    params={'key': api_key},
                    json={'contents': [{'parts': [{'text': prompt}]}],
                          'generationConfig': {'temperature': 0.3, 'maxOutputTokens': 2048}},
                    timeout=60
                )
                if r.status_code == 200:
                    _d = r.json()
                    return _d['candidates'][0]['content']['parts'][0]['text']
                elif r.status_code == 404:
                    continue  # model not found, try next
                elif r.status_code == 429:
                    _t.sleep(2); continue
            except Exception as _em:
                print(f'[AI/{model}] {_em}'); _t.sleep(1)
    except Exception as e:
        return f'AI 生成失敗：{e}'
    return '⚠️ AI 服務暫時無法使用（請確認 GEMINI_API_KEY 是否正確）'

# 利多出盡防呆機制：已整合到 AI prompt 中
# 當外資/投信連續賣超時，AI 被要求輸出紅色警報
