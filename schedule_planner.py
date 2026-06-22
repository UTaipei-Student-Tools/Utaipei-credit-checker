import streamlit as st
import pandas as pd
import json

DEFAULT_SCHEDULE_DATA = """
{
  "version": 1,
  "school": "臺北市立大學",
  "semester": "114-2",
  "timeConfig": {
    "name": "臺北市立大學",
    "periods": [
      { "id": "1", "startTime": "08:10", "endTime": "09:00" },
      { "id": "2", "startTime": "09:10", "endTime": "10:00" },
      { "id": "3", "startTime": "10:10", "endTime": "11:00" },
      { "id": "4", "startTime": "11:10", "endTime": "12:00" },
      { "id": "5", "startTime": "12:10", "endTime": "13:00" },
      { "id": "6", "startTime": "13:10", "endTime": "14:00" },
      { "id": "7", "startTime": "14:10", "endTime": "15:00" },
      { "id": "8", "startTime": "15:10", "endTime": "16:00" },
      { "id": "9", "startTime": "16:10", "endTime": "17:00" },
      { "id": "10", "startTime": "17:10", "endTime": "18:00" },
      { "id": "11", "startTime": "18:10", "endTime": "19:00" },
      { "id": "12", "startTime": "19:10", "endTime": "20:00" },
      { "id": "13", "startTime": "20:10", "endTime": "21:00" },
      { "id": "14", "startTime": "21:10", "endTime": "22:00" }
    ]
  },
  "courses": []
}
"""

def render_schedule_planner():
    st.markdown("### 🗓️ 模擬排課")
    st.markdown("您可以在下方課表中直接點擊格子，輸入或修改預計修讀的課程名稱。編輯完成後即可匯出 CSV 檔供自行留存。")
    
    # Init or load session state for the schedule dataframe
    if 'schedule_df' not in st.session_state:
        data = json.loads(DEFAULT_SCHEDULE_DATA)
        
        periods = []
        for p in data["timeConfig"]["periods"]:
            periods.append(f"第{p['id']}節 ({p['startTime']}-{p['endTime']})")
            
        df = pd.DataFrame(columns=["節次/時間", "星期一", "星期二", "星期三", "星期四", "星期五"])
        df["節次/時間"] = periods
        df.fillna("", inplace=True)
        
        day_map = {"Monday": "星期一", "Tuesday": "星期二", "Wednesday": "星期三", "Thursday": "星期四", "Friday": "星期五"}
        for c in data["courses"]:
            c_name = c["courseName"]
            for eng_day, p_ids in c.get("schedule", {}).items():
                zh_day = day_map.get(eng_day)
                if zh_day:
                    for p_id in p_ids:
                        idx = int(p_id) - 1
                        if 0 <= idx < len(periods):
                            df.at[idx, zh_day] = c_name
                                
        st.session_state['schedule_df'] = df

    col_config = {
        "節次/時間": st.column_config.TextColumn(
            "節次/時間",
            disabled=True,
            width="medium"
        ),
    }
    for day in ["星期一", "星期二", "星期三", "星期四", "星期五"]:
        col_config[day] = st.column_config.TextColumn(
            day,
            width="medium"
        )

    palette = [
        "#999EA2", "#93939B", "#CCD2CC", "#DBD2C9", "#976666", 
        "#C09D9B", "#BEBEBE", "#7A848D", "#A9B7AA", "#DBD4C6"
    ]
    
    def style_schedule(val):
        if not val or str(val).strip() == "":
            return ''
        idx = sum(ord(c) for c in str(val)) % len(palette)
        bg_color = palette[idx]
        return f'background-color: {bg_color}; color: white; font-weight: 600;'

    # Apply style to days only
    styled_df = st.session_state['schedule_df'].style.map(style_schedule, subset=["星期一", "星期二", "星期三", "星期四", "星期五"])

    st.markdown("<br>", unsafe_allow_html=True)
    edited_df = st.data_editor(
        styled_df,
        use_container_width=True,
        hide_index=True,
        column_config=col_config,
        num_rows="fixed",
        height=580
    )
    
    st.session_state['schedule_df'] = pd.DataFrame(edited_df)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("📥 輸出暫時規劃表 (CSV)"):
        csv = st.session_state['schedule_df'].to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="點擊下載課表 CSV",
            data=csv,
            file_name="Temporary_Schedule.csv",
            mime="text/csv"
        )
