# Repaint a rendered picture as a soft hand-painted illustration with Gemini image editing, keeping the layout.
# python paint.py <env_file> <in.png> <out.png> <model>
import base64, json, sys, urllib.request, urllib.error

env, src, dst, model = sys.argv[1:5]
key = ""
for line in open(env, encoding="utf-8-sig"):
    if line.strip().startswith("GEMINI_API_KEY="):
        key = line.split("=", 1)[1].strip()
if not key:
    sys.exit("no GEMINI_API_KEY")

PROMPT = (
    "Repaint this picture as a soft hand-painted 2D illustration for a cute casual mobile game: painterly brushwork, "
    "gentle colour variation and texture in the grass and dirt, warm late-afternoon sunlight from the upper left, "
    "soft painted shadows under trees and buildings, slightly glowing highlights, a light blue sky with soft clouds "
    "above the distant hills. Keep EXACTLY the same layout, every object in the same place and size, the same "
    "camera angle and composition, and the empty dirt yard in the middle. Do not add people, animals, text or logos."
)
body = {
    "contents": [{"parts": [
        {"text": PROMPT},
        {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(src, "rb").read()).decode()}},
    ]}],
    "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
}
req = urllib.request.Request(
    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
try:
    res = json.load(urllib.request.urlopen(req, timeout=180))
except urllib.error.HTTPError as e:
    sys.exit(f"HTTP {e.code}: {e.read().decode()[:400]}")
for cand in res.get("candidates", []):
    for part in cand.get("content", {}).get("parts", []):
        data = part.get("inline_data") or part.get("inlineData")
        if data:
            open(dst, "wb").write(base64.b64decode(data["data"]))
            print("saved", dst)
            sys.exit(0)
        if part.get("text"):
            print("text:", part["text"][:300])
sys.exit("no image in response: " + json.dumps(res)[:400])
