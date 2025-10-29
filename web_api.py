from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from captcha import captcha
from io import BytesIO
import base64

app = FastAPI()

# Allow your web app's origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:44332"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class CaptchaRequest(BaseModel):
    numbers: list[int]

@app.post("/captcha")
def generate_captcha(data: CaptchaRequest):
    if len(data.numbers) != 5:
        return {"error": "Must provide exactly 5 numbers"}
    text = ''.join(map(str, data.numbers))
    img = captcha(
        text,
        font_size=30,
        height=50,
        mesh_steps=(1, 11),
        grid_spacing=16,
        distortion=0,
        noise=1,
        grid_strength=0,
        rotation=1,
    )
    buf = BytesIO()
    img.save(buf, format="PNG")
    img_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return {"token": "dummy-token", "image_b64": img_b64}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8858)
