# -*- coding: utf-8 -*-
"""
UTaipei Portal Scraper - Live Transcript Crawler
"""

import requests
from bs4 import BeautifulSoup
import os

def crawl_transcript_pdf(uid, pwd, download_dir):
    login_url = "https://my.utaipei.edu.tw/utaipei/login_check.jsp"
    perchk_url = "https://my.utaipei.edu.tw/utaipei/perchk.jsp"
    fnc_url = "https://my.utaipei.edu.tw/utaipei/fnc.jsp"
    ag102_url = "https://my.utaipei.edu.tw/utaipei/ag_pro/ag102.jsp"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://my.utaipei.edu.tw/utaipei/index_main.html"
    }
    
    data = {
        "uid": uid,
        "pwd": pwd,
        "myway": "yes",
        "check_choice": "",
        "teach_roll": "",
        "std_dorm": "",
        "std_vote": "",
        "std_choice": ""
    }
    
    session = requests.Session()
    
    try:
        # 1. POST Login Credentials
        response1 = session.post(login_url, headers=headers, data=data)
        if response1.status_code != 200:
            raise ConnectionError(f"Login request failed with status code: {response1.status_code}")
            
        soup1 = BeautifulSoup(response1.text, 'html.parser')
        form1 = soup1.find('form', id='thisform')
        if not form1:
            # Login likely failed (credentials incorrect or page structure changed)
            if "帳號密碼不正確" in response1.text or "密碼錯誤" in response1.text:
                raise ValueError("登入失敗: 帳號或密碼錯誤!")
            raise ValueError("登入失敗: 無法取得登入驗證表單，請確認帳號密碼是否正確。")
            
        perchk_data = {inp.get('name'): inp.get('value', '') for inp in form1.find_all('input')}
        
        # 2. POST Perchk (establish portal session)
        headers['Referer'] = login_url
        response2 = session.post(perchk_url, headers=headers, data=perchk_data)
        if response2.status_code != 200:
            raise ConnectionError("Portal session validation (perchk) failed.")
            
        # 3. POST Fnc for student transcript page AG102 (Get redirect inputs)
        headers['Referer'] = perchk_url
        fnc_data = {
            "fncid": "AG102",
            "hid_type": "S",
            "hid_choice_check": "",
            "hid_teach_roll": "",
            "hid_dorm_room": "",
            "hid_std_vote": "",
            "hid_std_choice": "",
            "hid_atd": "0"
        }
        response3 = session.post(fnc_url, headers=headers, data=fnc_data)
        if response3.status_code != 200:
            raise ConnectionError("Fnc redirection request failed.")
            
        soup3 = BeautifulSoup(response3.text, 'html.parser')
        form3 = soup3.find('form', id='thisform')
        if not form3:
            raise ValueError("無法跳轉至歷年成績查詢頁面。")
            
        ag102_data = {inp.get('name'): inp.get('value', '') for inp in form3.find_all('input')}
        
        # 4. POST ag102.jsp to generate PDF transcript
        headers['Referer'] = fnc_url
        response4 = session.post(ag102_url, headers=headers, data=ag102_data)
        if response4.status_code != 200:
            raise ConnectionError("Transcript PDF generation page request failed.")
            
        if response4.apparent_encoding:
            response4.encoding = response4.apparent_encoding
            
        soup4 = BeautifulSoup(response4.text, 'html.parser')
        
        # Locate the PDF file link or iframe src
        pdf_path_relative = None
        pdf_link_el = soup4.find('a', href=lambda h: h and h.endswith('.pdf'))
        if pdf_link_el:
            pdf_path_relative = pdf_link_el.get('href')
        else:
            iframe_el = soup4.find('iframe', id='pdf1')
            if iframe_el:
                pdf_path_relative = iframe_el.get('src')
                
        if not pdf_path_relative:
            raise ValueError("在成績頁面中找不到 PDF 下載連結。這可能是因為校務系統忙碌中，請稍後再試。")
            
        pdf_url = "https://my.utaipei.edu.tw" + pdf_path_relative
        
        # 5. Download the dynamic PDF file
        headers['Referer'] = ag102_url
        pdf_resp = session.get(pdf_url, headers=headers)
        if pdf_resp.status_code != 200:
            raise ConnectionError("Transcript PDF file download failed.")
            
        # Save file to local directory
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
            
        pdf_file_path = os.path.join(download_dir, "student_transcript.pdf")
        with open(pdf_file_path, "wb") as f:
            f.write(pdf_resp.content)
            
        return pdf_file_path
        
    except Exception as e:
        raise RuntimeError(f"Scraper Error: {str(e)}")
