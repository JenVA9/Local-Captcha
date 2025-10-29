# Fixed captcha function with 0-1 controls for distortion and noise.
# - Suppresses DeprecationWarning to remove stdout "errors".
# - Adds parameters: distortion, noise, grid_strength, rotation (all 0..1).
# - Enforces readable text area (text pixels forced opaque).
# - Saves test image to /mnt/data/captcha_params.png

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageOps
import random, os, math

# Compatibility helpers
try:
    Resampling = Image.Resampling
except AttributeError:
    class _Resampling:
        BICUBIC = Image.BICUBIC
    Resampling = _Resampling()

# Load fallback fonts
def _load_font(size):
    candidates = [
        "arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

def captcha(text,
            width=None,
            height=50,
            font_path=None,
            font_size=30,
            mesh_steps=(1,11),
            grid_spacing=16,
            distortion=0,    # 0..1  -> 0 = no mesh distortion, 1 = max
            noise=1,         # 0..1  -> 0 = no noise, 1 = strong noise
            grid_strength=0, # 0..1  -> line strength on grid lines
            rotation=1,      # 0..1  -> how much per-char rotation (0 none, 1 strong)
            protect_text=True  # keep text area opaque for readability
           ):
    """
    Returns a PIL RGBA Image.
    Parameters distortion, noise, grid_strength, rotation are floats 0..1.
    """
    # clamp helpers
    def clamp01(v): return max(0.0, min(1.0, float(v)))

    distortion = clamp01(distortion)
    noise = clamp01(noise)
    grid_strength = clamp01(grid_strength)
    rotation = clamp01(rotation)

    if width is None:
        width = max(220, int(len(text) * font_size * 0.6) + 60)
    w,h = int(width), int(height)

    # Base white background
    base = Image.new("RGBA", (w,h), (255,255,255,255))

    # Prepare font
    if font_path:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception:
            font = _load_font(font_size)
    else:
        font = _load_font(font_size)

    # Render text on transparent layer
    text_layer = Image.new("RGBA", (w,h), (0,0,0,0))
    x = 20
    for ch in text:
        ch_w = int(font_size * 1.05) + 8
        ch_img = Image.new("RGBA", (ch_w, h), (0,0,0,0))
        ch_draw = ImageDraw.Draw(ch_img)
        y_offset = max(0, (h - font_size) // 2 - 2)
        ch_draw.text((4, y_offset), ch, font=font, fill=(10,10,10,255))
        # rotation scaled by parameter
        max_angle = 12  # degrees at rotation=1
        angle = random.uniform(-max_angle * rotation, max_angle * rotation)
        ch_img = ch_img.rotate(angle, resample=Resampling.BICUBIC, expand=1)
        if x + ch_img.width > w - 20:
            break
        text_layer.paste(ch_img, (int(x), 0), ch_img)
        x += int(font_size * 0.68) + random.randint(-1,3)

    # Composite text over base so we can distort everything
    composed = Image.alpha_composite(base, text_layer)

    # Mesh distortion
    nx, ny = mesh_steps
    nx = max(1, int(nx)); ny = max(1, int(ny))
    cell_w = w / nx
    cell_h = h / ny
    mesh = []
    # scale offsets by distortion [0..1]
    # base max offsets relative to cell size
    base_x_factor = 0.25
    base_y_factor = 0.30
    max_offset_x = max(1, cell_w * base_x_factor * distortion)
    max_offset_y = max(1, cell_h * base_y_factor * distortion)
    for i in range(nx):
        for j in range(ny):
            x0 = int(i * cell_w)
            y0 = int(j * cell_h)
            x1 = int((i + 1) * cell_w)
            y1 = int((j + 1) * cell_h)
            # corners
            dx0 = int(random.uniform(-max_offset_x, max_offset_x))
            dy0 = int(random.uniform(-max_offset_y, max_offset_y))
            dx1 = int(random.uniform(-max_offset_x, max_offset_x))
            dy1 = int(random.uniform(-max_offset_y, max_offset_y))
            dx2 = int(random.uniform(-max_offset_x, max_offset_x))
            dy2 = int(random.uniform(-max_offset_y, max_offset_y))
            dx3 = int(random.uniform(-max_offset_x, max_offset_x))
            dy3 = int(random.uniform(-max_offset_y, max_offset_y))
            box = (x0, y0, x1, y1)
            quad = (
                x0 + dx0, y0 + dy0,
                x1 + dx1, y0 + dy1,
                x1 + dx2, y1 + dy2,
                x0 + dx3, y1 + dy3
            )
            mesh.append((box, quad))

    # apply transform; if mesh unavailable or distortion=0 skip to preserve crispness
    if distortion > 0.001 and hasattr(Image, "MESH"):
        try:
            composed = composed.transform((w,h), Image.MESH, mesh, resample=Resampling.BICUBIC)
        except Exception:
            # fallback small rotation
            composed = composed.rotate(random.uniform(-2,2), resample=Resampling.BICUBIC, expand=False)
    else:
        # slight global warp via tiny rotation to avoid zero-change
        composed = composed.rotate(random.uniform(-1,1) * rotation, resample=Resampling.BICUBIC, expand=False)

    # Slight blur to smooth edges but keep readable
    composed = composed.filter(ImageFilter.GaussianBlur(radius=0.3 * (0.5 + distortion * 0.5)))

    # Noise generation: effect_noise amplitude scaled by noise param
    # Use larger seed amplitude for higher noise
    noise_amp = int(8 + 120 * noise)  # 8..128
    try:
        noise_img = Image.effect_noise((w,h), noise_amp).convert("L")
    except Exception:
        # fallback manual noise
        noise_img = Image.new("L", (w,h))
        npix = noise_img.load()
        for yy in range(h):
            for xx in range(w):
                npix[xx,yy] = int(128 + (127 * noise) * (random.random() - 0.5))

    # Grid overlay: strength scaled by grid_strength
    grid = Image.new("L", (w,h), 0)
    gdraw = ImageDraw.Draw(grid)
    line_w = max(1, int(max(1, grid_spacing * 0.06) * (0.3 + grid_strength)))
    line_opacity = int(48 + 160 * grid_strength)  # 48..208
    for gx in range(0, w, grid_spacing):
        gdraw.rectangle([gx-line_w, 0, gx+line_w, h], fill=line_opacity)
    for gy in range(0, h, grid_spacing):
        gdraw.rectangle([0, gy-line_w, w, gy+line_w], fill=line_opacity)

    # Combine noise and grid to get a reduction map. Higher values reduce alpha more.
    # scale noise contribution by noise param
    noise_scaled = noise_img.point(lambda p: int(p * noise * 0.85))
    reduction = ImageChops.add(noise_scaled, grid)  # 0..255
    # Convert reduction to alpha subtraction map
    # baseline subtraction amount scaled by overall grid_strength+noise
    base_sub = int(10 + 140 * (0.2*noise + 0.8*grid_strength))
    alpha_map = reduction.point(lambda p: int(min(255, base_sub + p * 0.6)))

    # Start with fully opaque alpha and subtract alpha_map, but enforce text protection
    alpha = Image.new("L", (w,h), 255)
    alpha = ImageChops.subtract(alpha, alpha_map)

    # Ensure text pixels remain highly opaque for readability if protect_text
    if protect_text:
        text_mask = text_layer.split()[-1].convert("L")
        # Where text exists, force alpha to at least 230
        forced = text_mask.point(lambda p: 230 if p > 16 else 0)
        alpha = ImageChops.lighter(alpha, forced)

    # Impose global minimum alpha so image never too transparent
    min_alpha = int(150 - 60 * (noise*0.8 + grid_strength*0.2))  # noise can lower min a bit
    min_alpha = max(100, min(255, min_alpha))
    alpha = alpha.point(lambda p: max(min_alpha, p))

    # Merge alpha back into composed image
    r,g,b,a = composed.split()
    out = Image.merge("RGBA", (r,g,b,alpha.convert("L")))

    # Add very light overlay noise lines and dots scaled by noise param
    overlay = Image.new("RGBA", (w,h), (0,0,0,0))
    od = ImageDraw.Draw(overlay)
    line_count = int(2 + 12 * noise)
    for _ in range(line_count):
        x0 = random.randint(0,w); y0 = random.randint(0,h)
        x1 = random.randint(0,w); y1 = random.randint(0,h)
        od.line((x0,y0,x1,y1), fill=(0,0,0, int(20 + 140 * noise)), width=random.randint(1,2))
    dot_count = int(w*h*0.0006 * (1 + noise*2))
    for _ in range(dot_count):
        x0 = random.randint(0,w-1); y0 = random.randint(0,h-1)
        od.point((x0,y0), fill=(0,0,0, int(10 + 140 * noise)))
    out = Image.alpha_composite(out, overlay)

    # Slight contrast tweak to keep text readable
    rgb = out.convert("RGB").point(lambda p: min(255, int((p-16)*1.06 + 6)))
    out = Image.merge("RGBA", (*rgb.split(), out.split()[-1]))

    return out

# Quick test save demonstrating parameters
if __name__ == "__main__":
    img = captcha("55978", font_size=30, height=50,
                  mesh_steps=(1,11), grid_spacing=16,
                  distortion=0, noise=1, grid_strength=0, rotation=1)
    out_path = "captcha_out2.png"
    img.save(out_path)
    out_path

