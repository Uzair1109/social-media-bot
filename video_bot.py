import os
import json
import time
import datetime
import requests
import gspread
from google.oauth2.service_account import Credentials
from google import genai
from google.genai import types

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

REPO_NAME = "Uzair1109/social-media-bot"

def get_services():
    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    gc = gspread.authorize(creds)
    
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    client = genai.Client(api_key=gemini_key)
    return gc, client

def enhance_prompt_for_video(client, raw_prompt, brand, topic):
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=f"""
You are an expert AI video director. Convert this static visual direction into a single-sentence, highly cinematic 5-second video prompt with clear camera motion (e.g. slow cinematic pan, smooth dolly forward, realistic lighting shift, high frame rate, 4k).

Brand: {brand}
Topic: {topic}
Original Visual: {raw_prompt}

Output ONLY the enhanced video prompt:
""",
        )
        enhanced = response.text.strip()
        print(f"Motion Enhanced Prompt: {enhanced}")
        return enhanced
    except Exception as e:
        print(f"Prompt enhancement fallback: {e}")
        return f"Cinematic slow motion video, smooth camera dolly forward, 4k ultra realistic: {raw_prompt}"

def generate_and_save_video(client, prompt, file_name, brand="", topic="", aspect_ratio="9:16"):
    video_prompt = enhance_prompt_for_video(client, prompt, brand, topic)
    print(f"Submitting video task: '{video_prompt[:80]}...'")
    
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    # Attempt 1: Veo / Vertex endpoint via GenAI Client
    try:
        operation = client.models.generate_videos(
            model="veo-2.0-generate-001",
            prompt=video_prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio=aspect_ratio,
                number_of_videos=1,
                duration_seconds=5
            ),
        )

        print("Rendering video...")
        while not operation.done:
            time.sleep(10)
            operation = client.operations.get(operation)

        result = operation.result
        generated_video = result.generated_videos[0]

        os.makedirs("assets/videos", exist_ok=True)
        local_path = os.path.join("assets/videos", file_name)
        client.files.download(file=generated_video.video.uri, download_filepath=local_path)
        print(f"Video saved to: {local_path}")
        return f"https://raw.githubusercontent.com/{REPO_NAME}/main/assets/videos/{file_name}"

    except Exception as e:
        print(f"Standard Veo endpoint error: {e}")

    # Attempt 2: Direct call via Google Sandbox endpoint
    try:
        sandbox_url = f"https://aisandbox-pa.googleapis.com/v1:generateVideo?key={gemini_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "prompt": video_prompt,
            "aspectRatio": aspect_ratio,
            "durationSeconds": 5
        }
        res = requests.post(sandbox_url, json=payload, headers=headers, timeout=60)
        if res.status_code in [200, 201]:
            data = res.json()
            video_url = data.get("videoUrl") or data.get("url")
            if video_url:
                os.makedirs("assets/videos", exist_ok=True)
                local_path = os.path.join("assets/videos", file_name)
                vid_data = requests.get(video_url).content
                with open(local_path, "wb") as f:
                    f.write(vid_data)
                print(f"Video saved to: {local_path}")
                return f"https://raw.githubusercontent.com/{REPO_NAME}/main/assets/videos/{file_name}"
        else:
            print(f"Sandbox endpoint returned status {res.status_code}: {res.text[:120]}")
    except Exception as e:
        print(f"Sandbox call error: {e}")

    return None

def main():
    gc, gemini_client = get_services()
    available_sheets = gc.openall()
    if not available_sheets:
        print("No spreadsheets found!")
        return

    target_spreadsheet = None
    for s in available_sheets:
        if "Master_Social_Media_Calendar" in s.title or "Social" in s.title:
            target_spreadsheet = s
            break

    if not target_spreadsheet:
        target_spreadsheet = available_sheets[0]

    print(f"Connected to Spreadsheet: '{target_spreadsheet.title}'")
    total_processed = 0

    for sheet in target_spreadsheet.worksheets():
        tab_name = sheet.title.strip()
        all_values = sheet.get_all_values()

        print("\n" + "=" * 55)
        print(f"Inspecting Tab for Video Rows: '{tab_name}'")
        print("=" * 55)

        if len(all_values) < 2:
            continue

        header_row = [str(h).strip().lower() for h in all_values[0]]
        brand_col, topic_col, format_col, prompt_col, link_col, status_col = 2, 3, 4, 5, 7, 8

        for col_i, col_name in enumerate(header_row, start=1):
            if "brand" in col_name:
                brand_col = col_i
            elif "topic" in col_name:
                topic_col = col_i
            elif "format" in col_name:
                format_col = col_i
            elif "prompt" in col_name or "visual" in col_name:
                prompt_col = col_i
            elif "folder" in col_name or "link" in col_name:
                link_col = col_i
            elif "status" in col_name:
                status_col = col_i

        target_row_idx = None
        target_row_data = None

        for idx, row in enumerate(all_values[1:], start=2):
            status_val = str(row[status_col - 1]).strip().lower() if len(row) >= status_col else ""
            format_val = str(row[format_col - 1]).strip().upper() if len(row) >= format_col else ""
            prompt_val = str(row[prompt_col - 1]).strip() if len(row) >= prompt_col else ""

            is_video_format = any(k in format_val for k in ["REEL", "VIDEO", "SHORT"])
            if status_val != "done" and len(prompt_val) > 0 and is_video_format:
                target_row_idx = idx
                target_row_data = row
                break

        if not target_row_idx or not target_row_data:
            print(f"No pending video rows found in '{tab_name}'.")
            continue

        brand = str(target_row_data[brand_col - 1]).strip() if len(target_row_data) >= brand_col and str(target_row_data[brand_col - 1]).strip() else tab_name
        topic = str(target_row_data[topic_col - 1]).strip() if len(target_row_data) >= topic_col else "Video_Asset"
        prompt = str(target_row_data[prompt_col - 1]).strip()

        clean_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')[:30]
        clean_brand = "".join(c for c in brand if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')[:20]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{timestamp}_{clean_brand}_{clean_topic}.mp4"

        print(f"Processing Tab: '{tab_name}' | Row {target_row_idx} | Topic: '{topic}'")
        permanent_url = generate_and_save_video(gemini_client, prompt, file_name, brand=brand, topic=topic)

        if permanent_url:
            sheet.update_cell(target_row_idx, link_col, permanent_url)
            sheet.update_cell(target_row_idx, status_col, "Done")
            print(f"Updated row {target_row_idx} in '{tab_name}' to Done.")
            total_processed += 1
            time.sleep(2)
        else:
            print(f"Failed to generate video asset for tab '{tab_name}'.")

    print("\n" + "=" * 55)
    print(f"Video Pipeline Finished! Total videos generated: {total_processed}")
    print("=" * 55)

if __name__ == "__main__":
    main()
