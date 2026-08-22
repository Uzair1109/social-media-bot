import datetime
import os
import json
import time
import io
import gspread
from google.oauth2.service_account import Credentials
from google import genai
from google.genai import types
from PIL import Image

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

REPO_NAME = "Uzair1109/social-media-bot"

def get_services():
    creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    gc = gspread.authorize(creds)
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return gc, client

def generate_and_save_image(client, prompt, file_name):
    print(f"Calling Google Imagen 3 with prompt: '{prompt[:75]}...'")
    try:
        result = client.models.generate_images(
            model='imagen-3.0-generate-002',
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="1:1",
                output_mime_type="image/png"
            )
        )
        
        os.makedirs("assets", exist_ok=True)
        local_path = os.path.join("assets", file_name)

        for generated_image in result.generated_images:
            image = Image.open(io.BytesIO(generated_image.image.image_bytes))
            image.save(local_path)
            break

        permanent_github_url = f"https://raw.githubusercontent.com/{REPO_NAME}/main/assets/{file_name}"
        print(f"Image saved locally: {local_path}")
        return permanent_github_url
    except Exception as e:
        print(f"Gemini/Imagen Generation Error: {e}")
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
        print(f"Inspecting Tab: '{tab_name}' ({len(all_values)} total rows)")
        print("=" * 55)
        
        if len(all_values) < 2:
            continue

        header_row = [str(h).strip().lower() for h in all_values[0]]
        
        brand_col = 2
        topic_col = 3
        prompt_col = 5
        link_col = 7
        status_col = 8

        for col_i, col_name in enumerate(header_row, start=1):
            if "brand" in col_name:
                brand_col = col_i
            elif "topic" in col_name:
                topic_col = col_i
            elif "visual direction" in col_name or "prompt" in col_name:
                prompt_col = col_i
            elif "folder" in col_name or "link" in col_name or "asset" in col_name:
                link_col = col_i
            elif "status" in col_name:
                status_col = col_i

        target_row_idx = None
        target_row_data = None

        for idx, row in enumerate(all_values[1:], start=2):
            status_val = str(row[status_col - 1]).strip().lower() if len(row) >= status_col else ""
            prompt_val = str(row[prompt_col - 1]).strip() if len(row) >= prompt_col else ""
            
            if status_val != "done" and len(prompt_val) > 0:
                target_row_idx = idx
                target_row_data = row
                break

        if not target_row_idx or not target_row_data:
            print(f"No pending rows found in '{tab_name}'.")
            continue

        brand = str(target_row_data[brand_col - 1]).strip() if len(target_row_data) >= brand_col and str(target_row_data[brand_col - 1]).strip() else tab_name
        topic = str(target_row_data[topic_col - 1]).strip() if len(target_row_data) >= topic_col else "Asset"
        prompt = str(target_row_data[prompt_col - 1]).strip()

        clean_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')[:30]
        clean_brand = "".join(c for c in brand if c.isalnum() or c in (' ', '_')).strip().replace(' ', '_')[:20]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{timestamp}_{clean_brand}_{clean_topic}.png"

        print(f"Processing Tab: '{tab_name}' | Row {target_row_idx} | Topic: '{topic}'")
        permanent_url = generate_and_save_image(gemini_client, prompt, file_name)
        
        if permanent_url:
            sheet.update_cell(target_row_idx, link_col, permanent_url)
            sheet.update_cell(target_row_idx, status_col, "Done")
            print(f"Updated row {target_row_idx} in '{tab_name}' to Done.")
            total_processed += 1
            time.sleep(2)
        else:
            print(f"Failed to generate asset for tab '{tab_name}'.")

    print("\n" + "=" * 55)
    print(f"Pipeline Completed! Total assets generated across tabs: {total_processed}")
    print("=" * 55)

if __name__ == "__main__":
    main()
