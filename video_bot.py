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
