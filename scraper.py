"""
UTaipei Portal Scraper - Live Transcript Crawler
"""

import os
import re
import tempfile
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

LOGIN_URL = "https://my.utaipei.edu.tw/utaipei/login_check.jsp"
PERCHK_URL = "https://my.utaipei.edu.tw/utaipei/perchk.jsp"
FNC_URL = "https://my.utaipei.edu.tw/utaipei/fnc.jsp"
BASE_URL = "https://my.utaipei.edu.tw/utaipei/"
MAX_PDF_BYTES = 20 * 1024 * 1024

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://my.utaipei.edu.tw/utaipei/index_main.html",
}


def _start_session(uid, pwd):
    uid = uid.strip() if uid else ""
    data = {
        "uid": uid,
        "pwd": pwd,
        "myway": "yes",
        "check_choice": "",
        "teach_roll": "",
        "std_dorm": "",
        "std_vote": "",
        "std_choice": "",
    }
    session = requests.Session()
    try:
        session.get(BASE_URL + "index_main.html", headers=HEADERS, timeout=10)
    except Exception:
        pass
    response = session.post(
        LOGIN_URL, headers={**HEADERS, "Referer": BASE_URL + "index_main.html"}, data=data, timeout=15
    )
    if response.status_code == 403 or "forbidden" in response.text.lower() or "access denied" in response.text.lower():
        raise ValueError("校務系統阻擋了非台灣或雲端伺服器的連線，請在台灣網路環境下執行。")
    if response.status_code != 200:
        raise ConnectionError(f"Login request failed with status code: {response.status_code}")
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    err_input = soup.find("input", id="err")
    if err_input and err_input.get("value") == "Y":
        error_font = soup.find("font", color="red")
        error_text = error_font.text.strip() if error_font else ""
        error_text = error_text.replace("\ufeff", "").strip()
        raise ValueError(error_text or "帳號或密碼不正確，請重新輸入！")
    form = soup.find("form", id="thisform")
    if not form:
        text_lower = response.text.lower()
        if "帳號" in text_lower or "密碼" in text_lower or "error" in text_lower:
            raise ValueError("帳號或密碼錯誤，請重新確認！")
        raise ValueError("無法取得登入驗證表單，請檢查校務系統是否維護中。")
    perchk_data = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
    response2 = session.post(PERCHK_URL, headers={**HEADERS, "Referer": LOGIN_URL}, data=perchk_data, timeout=15)
    if response2.status_code != 200:
        raise ConnectionError("Portal session validation (perchk) failed.")
    return session


def _create_fnc_session(session, fncid):
    response = session.post(
        FNC_URL,
        headers={**HEADERS, "Referer": PERCHK_URL},
        data={
            "fncid": fncid,
            "hid_type": "S",
            "hid_choice_check": "",
            "hid_teach_roll": "",
            "hid_dorm_room": "",
            "hid_std_vote": "",
            "hid_std_choice": "",
            "hid_atd": "0",
        },
        timeout=15,
    )
    if response.status_code != 200:
        raise ConnectionError(f"Fnc redirection request failed for {fncid}.")
    return response


def _submit_portal_form(session, action_path, form_data, referer):
    target = BASE_URL + action_path.lstrip("/")
    response = session.post(target, headers={**HEADERS, "Referer": referer}, data=form_data, timeout=20)
    if response.status_code != 200:
        raise ConnectionError(f"Portal request failed for {action_path}")
    response.encoding = "utf-8"
    return response


def discover_portal_features(uid, pwd):
    """探索校務系統可用功能，回傳可用的 AG 功能代碼與簡述。"""
    session = _start_session(uid, pwd)
    available = []
    try:
        for fncid in ["AG104", "AG107", "AG108", "AG102"]:
            try:
                _create_fnc_session(session, fncid)
                names = {
                    "AG104": "開課選課資料查詢 / 班級課表",
                    "AG107": "教學評量查詢",
                    "AG108": "教學評量填答率查詢",
                    "AG102": "歷年成績單下載",
                }
                available.append({"fncid": fncid, "name": names[fncid], "status": "可用"})
            except Exception as exc:
                available.append({"fncid": fncid, "name": "不可用或無權限", "status": str(exc)})
    finally:
        session.close()
    return available


def crawl_course_schedule(uid, pwd, year="114", semester="2"):
    session = _start_session(uid, pwd)
    try:
        _create_fnc_session(session, "AG104")
        response = _submit_portal_form(
            session,
            "system/sys001_00.jsp?spath=ag_pro/ag104.jsp?",
            {"arg01": year, "arg02": semester, "arg03": uid, "arg04": "", "arg05": "", "arg06": "", "fncid": "AG104"},
            FNC_URL,
        )
        soup = BeautifulSoup(response.text, "html.parser")
        form = soup.find("form")
        if not form:
            raise ValueError("未能載入 AG104 查詢頁面。")
        form_data = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
        form_data["yms"] = f"{year},{semester}"
        schedule_resp = _submit_portal_form(
            session, "ag_pro/ag104.jsp?", form_data, BASE_URL + "system/sys001_00.jsp?spath=ag_pro/ag104.jsp?"
        )
        return schedule_resp.text
    finally:
        session.close()


def crawl_transcript_pdf(uid, pwd, download_dir):
    login_url = LOGIN_URL
    perchk_url = PERCHK_URL
    fnc_url = FNC_URL
    ag102_url = BASE_URL + "ag_pro/ag102.jsp"

    # Copy request headers so concurrent Streamlit sessions never mutate shared state.
    headers = HEADERS.copy()

    # Clean up input username to prevent trailing/leading spaces
    uid = uid.strip() if uid else ""

    data = {
        "uid": uid,
        "pwd": pwd,
        "myway": "yes",
        "check_choice": "",
        "teach_roll": "",
        "std_dorm": "",
        "std_vote": "",
        "std_choice": "",
    }

    session = requests.Session()
    pdf_file_path = None

    try:
        # Pre-fetch index page to initialize critical cookies (e.g. SKIcpCfxhUjHBw__)
        try:
            session.get("https://my.utaipei.edu.tw/utaipei/index_main.html", headers=headers, timeout=10)
        except Exception:
            pass

        # 1. POST Login Credentials
        response1 = session.post(login_url, headers=headers, data=data, timeout=15)

        # Check if IP blocked or forbidden (common in cloud servers like Hugging Face outside Taiwan)
        if (
            response1.status_code == 403
            or "forbidden" in response1.text.lower()
            or "access denied" in response1.text.lower()
        ):
            raise ValueError(
                "校務系統阻擋了非台灣或雲端伺服器 (如 Hugging Face) 的連線，回傳了 403 拒絕存取。請嘗試在您的本機電腦 (台灣區域 IP) 上執行此系統！"
            )

        if response1.status_code != 200:
            raise ConnectionError(f"Login request failed with status code: {response1.status_code}")

        response1.encoding = "utf-8"
        soup1 = BeautifulSoup(response1.text, "html.parser")

        # Robust check for error indicator input: <input type="hidden" id="err" name="err" value="Y">
        err_input = soup1.find("input", id="err")
        if err_input and err_input.get("value") == "Y":
            error_font = soup1.find("font", color="red")
            error_text = error_font.text.strip() if error_font else ""
            # Clean up potential BOM/whitespace in error_text
            error_text = error_text.replace("\ufeff", "").strip()
            if error_text:
                raise ValueError(f"{error_text}")
            raise ValueError("帳號或密碼不正確，請重新輸入！")

        form1 = soup1.find("form", id="thisform")
        if not form1:
            # Fallback text checking for errors
            text_lower = response1.text.lower()
            if "帳號" in text_lower or "密碼" in text_lower or "error" in text_lower:
                raise ValueError("帳號或密碼錯誤，請重新確認！")
            raise ValueError("無法取得登入驗證表單。這可能是校務系統正處於維護中，或阻擋了外部連線！")

        perchk_data = {inp.get("name"): inp.get("value", "") for inp in form1.find_all("input") if inp.get("name")}

        # 2. POST Perchk (establish portal session)
        headers["Referer"] = login_url
        response2 = session.post(perchk_url, headers=headers, data=perchk_data, timeout=15)
        if response2.status_code != 200:
            raise ConnectionError("Portal session validation (perchk) failed.")

        # 3. POST Fnc for student transcript page AG102 (Get redirect inputs)
        headers["Referer"] = perchk_url
        fnc_data = {
            "fncid": "AG102",
            "hid_type": "S",
            "hid_choice_check": "",
            "hid_teach_roll": "",
            "hid_dorm_room": "",
            "hid_std_vote": "",
            "hid_std_choice": "",
            "hid_atd": "0",
        }
        response3 = session.post(fnc_url, headers=headers, data=fnc_data, timeout=15)
        if response3.status_code != 200:
            raise ConnectionError("Fnc redirection request failed.")

        response3.encoding = "utf-8"
        soup3 = BeautifulSoup(response3.text, "html.parser")
        form3 = soup3.find("form", id="thisform")
        if not form3:
            raise ValueError("無法跳轉至歷年成績查詢頁面。")

        ag102_data = {inp.get("name"): inp.get("value", "") for inp in form3.find_all("input") if inp.get("name")}

        # 4. POST ag102.jsp to generate PDF transcript
        headers["Referer"] = fnc_url
        response4 = session.post(ag102_url, headers=headers, data=ag102_data, timeout=20)
        if response4.status_code != 200:
            raise ConnectionError("Transcript PDF generation page request failed.")

        pdf_content = None
        content_type = response4.headers.get("Content-Type", "").lower()
        if "application/pdf" in content_type:
            pdf_content = response4.content
        else:
            response4.encoding = "utf-8"
            soup4 = BeautifulSoup(response4.text, "html.parser")
            pdf_path_relative = None
            pdf_link_el = soup4.find("a", href=lambda h: h and ".pdf" in h.lower())
            if pdf_link_el:
                pdf_path_relative = pdf_link_el.get("href")
            else:
                iframe_el = soup4.find("iframe", src=lambda s: s and ".pdf" in s.lower())
                if iframe_el:
                    pdf_path_relative = iframe_el.get("src")
                else:
                    embed_el = soup4.find("embed", src=lambda s: s and ".pdf" in s.lower())
                    if embed_el:
                        pdf_path_relative = embed_el.get("src")
                    else:
                        pdf_regex = re.search(r'https?://[^"\']+\.pdf', response4.text, re.IGNORECASE)
                        if pdf_regex:
                            pdf_path_relative = pdf_regex.group(0)

            if not pdf_path_relative:
                raise ValueError(
                    "在成績頁面中找不到 PDF 下載連結。這可能是因為校務系統目前忙碌中，或者頁面結構已更新。請稍後再試。"
                )

            pdf_url = urljoin(response4.url, pdf_path_relative)
            parsed_url = urlparse(pdf_url)
            if parsed_url.scheme != "https" or parsed_url.hostname != "my.utaipei.edu.tw":
                raise ValueError("成績單下載連結不是可信任的北市大網址。")

            # 5. Download the dynamic PDF file
            headers["Referer"] = ag102_url
            pdf_resp = session.get(pdf_url, headers=headers, timeout=25)
            if pdf_resp.status_code != 200:
                raise ConnectionError("Transcript PDF file download failed.")
            pdf_content = pdf_resp.content

        if not pdf_content or not pdf_content.startswith(b"%PDF-"):
            raise ValueError("校務系統回傳的內容不是有效 PDF。")
        if len(pdf_content) > MAX_PDF_BYTES:
            raise ValueError("成績單 PDF 超過 20 MB，已停止處理。")

        # Use a unique, private temporary file. A fixed filename can leak or
        # overwrite another user's transcript on a multi-user deployment.
        target_dir = download_dir if download_dir and os.path.isdir(download_dir) else None
        fd, pdf_file_path = tempfile.mkstemp(prefix="utaipei-transcript-", suffix=".pdf", dir=target_dir)
        with os.fdopen(fd, "wb") as f:
            f.write(pdf_content)

        # Read the transcript back into memory for the caller, then remove the
        # crawler-created file in the finally block.  A successful fetch must
        # not leave a student transcript on the host filesystem.
        with open(pdf_file_path, "rb") as handle:
            pdf_content = handle.read()
        return pdf_content

    except Exception as e:
        # Pass the original error message directly if it is custom raised
        raise RuntimeError(f"登入失敗: {e!s}") if isinstance(e, ValueError) else RuntimeError(f"Scraper Error: {e!s}")
    finally:
        session.close()
        if pdf_file_path:
            try:
                os.remove(pdf_file_path)
            except OSError:
                pass
