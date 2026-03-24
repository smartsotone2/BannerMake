import io
import random
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont


def build_size_tone_instruction(selected_size: str) -> str:
    width, height = parse_size(selected_size)
    if width > height:
        return (
            "Layout tone: wide horizontal campaign banner. "
            "Keep the center and one side visually calm to support long headline placement, "
            "with cinematic depth and a dynamic left-to-right flow."
        )
    if height > width:
        return (
            "Layout tone: vertical mobile-first promotional banner. "
            "Use bold focal composition near upper-middle area, maintain clear top and bottom safe zones, "
            "and emphasize energetic storytelling for scrolling feeds."
        )
    return (
        "Layout tone: square social post banner. "
        "Use balanced composition, centered visual hierarchy, and stable symmetry suitable for thumbnail previews."
    )


def build_banner_background_prompt(banner_topic: str, desired_text: str, selected_size: str) -> str:
    size_tone_instruction = build_size_tone_instruction(selected_size)
    return (
        "Create a premium, high-quality advertisement banner background image. "
        f"Theme: {banner_topic}. "
        "Style requirements: cinematic lighting, clean composition, strong visual hierarchy, "
        "brand-safe design, and enough negative space for headline/copy overlays. "
        f"{size_tone_instruction} "
        "Do not include logos, watermarks, or readable text in the image. "
        f"Intended ad copy context: {desired_text}."
    )


def generate_free_banner_image_candidates(
    banner_topic: str,
    desired_text: str,
    selected_size: str,
) -> tuple[list[str], str]:
    prompt = build_banner_background_prompt(
        banner_topic=banner_topic,
        desired_text=desired_text,
        selected_size=selected_size,
    )
    width, height = parse_size(selected_size)
    encoded_prompt = quote_plus(prompt)
    encoded_topic = quote_plus(banner_topic)
    seed = random.randint(1, 999_999_999)
    pollinations_url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width={width}&height={height}&model=flux&seed={seed}&nologo=true"
    )
    safe_topic = re.sub(r"[^a-zA-Z0-9가-힣 ]", "", banner_topic).strip()
    topic_tag = quote_plus(safe_topic) if safe_topic else "nature"
    loremflickr_url = f"https://loremflickr.com/{width}/{height}/{topic_tag},advertisement"
    picsum_url = f"https://picsum.photos/seed/{seed}/{width}/{height}"
    unsplash_source_url = f"https://source.unsplash.com/{width}x{height}/?{encoded_topic}"
    return [pollinations_url, loremflickr_url, unsplash_source_url, picsum_url], prompt


def image_url_to_bytes(candidate_urls: list[str]) -> tuple[bytes, str]:
    last_error: Exception | None = None
    for image_url in candidate_urls:
        try:
            response = requests.get(
                image_url,
                timeout=30,
                headers={"User-Agent": "Mozilla/5.0 BannerMaker/1.0"},
            )
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "image" not in content_type:
                raise ValueError(f"이미지 응답이 아닙니다: {content_type}")
            return response.content, response.url
        except Exception as error:
            last_error = error

    raise RuntimeError(f"무료 이미지 소스에서 이미지를 가져오지 못했습니다: {last_error}")


def build_final_banner_png(
    banner_topic: str,
    desired_text: str,
    selected_size: str,
    text_position: str,
) -> tuple[bytes, str, str]:
    candidate_urls, used_prompt = generate_free_banner_image_candidates(
        banner_topic=banner_topic,
        desired_text=desired_text,
        selected_size=selected_size,
    )
    image_bytes, image_url = image_url_to_bytes(candidate_urls)
    generated_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    final_image = resize_and_crop(generated_image, selected_size)
    final_image = compose_text_on_image(
        image=final_image,
        text=desired_text,
        position=text_position,
    )

    output_buffer = io.BytesIO()
    final_image.save(output_buffer, format="PNG")
    return output_buffer.getvalue(), image_url, used_prompt


def save_image_bytes_to_local(image_bytes: bytes, banner_topic: str) -> str:
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_topic = "_".join(banner_topic.strip().split())[:40] or "banner"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{safe_topic}_{timestamp}.png"
    output_path.write_bytes(image_bytes)
    return str(output_path)


def build_download_filename(banner_topic: str) -> str:
    safe_topic = "_".join(banner_topic.strip().split())[:40] or "banner"
    date_text = datetime.now().strftime("%Y%m%d")
    return f"{safe_topic}_{date_text}.png"


def parse_size(size_text: str) -> tuple[int, int]:
    width_text, height_text = size_text.split("x")
    return int(width_text), int(height_text)


def resize_and_crop(image: Image.Image, target_size: str) -> Image.Image:
    target_width, target_height = parse_size(target_size)
    target_ratio = target_width / target_height
    source_ratio = image.width / image.height

    if source_ratio > target_ratio:
        new_height = target_height
        new_width = int(target_height * source_ratio)
    else:
        new_width = target_width
        new_height = int(target_width / source_ratio)

    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    left = (new_width - target_width) // 2
    top = (new_height - target_height) // 2
    right = left + target_width
    bottom = top + target_height
    return resized.crop((left, top, right, bottom))


def load_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, font_size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    return right - left


def wrap_text_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = text.strip().split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]

    for word in words[1:]:
        candidate = f"{current} {word}"
        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)

    normalized: list[str] = []
    for line in lines:
        remaining = line
        while text_width(draw, remaining, font) > max_width and len(remaining) > 1:
            cut = len(remaining)
            while cut > 1 and text_width(draw, remaining[:cut], font) > max_width:
                cut -= 1
            normalized.append(remaining[:cut])
            remaining = remaining[cut:].lstrip()
        if remaining:
            normalized.append(remaining)
    return normalized or [""]


def measure_multiline(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.ImageFont,
    line_spacing: int,
) -> tuple[int, int, list[int], int]:
    line_widths = [text_width(draw, line, font) for line in lines]
    line_height = draw.textbbox((0, 0), "가", font=font)[3]
    text_block_width = max(line_widths) if line_widths else 0
    text_block_height = (line_height * len(lines)) + (line_spacing * max(0, len(lines) - 1))
    return text_block_width, text_block_height, line_widths, line_height


def compose_text_on_image(
    image: Image.Image,
    text: str,
    position: str = "bottom",
) -> Image.Image:
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    max_text_width = int(base.width * 0.84)
    max_text_height = int(base.height * 0.32)
    min_font_size = max(18, int(base.width * 0.022))
    max_font_size = max(42, int(base.width * 0.09))

    selected_font: ImageFont.ImageFont = load_font(min_font_size)
    selected_lines = [text]
    selected_spacing = max(8, int(min_font_size * 0.2))
    selected_metrics = measure_multiline(draw, selected_lines, selected_font, selected_spacing)

    for font_size in range(max_font_size, min_font_size - 1, -2):
        font = load_font(font_size)
        lines = wrap_text_to_width(draw, text, font, max_text_width)
        line_spacing = max(8, int(font_size * 0.2))
        metrics = measure_multiline(draw, lines, font, line_spacing)
        if metrics[0] <= max_text_width and metrics[1] <= max_text_height:
            selected_font = font
            selected_lines = lines
            selected_spacing = line_spacing
            selected_metrics = metrics
            break

    text_block_width, text_block_height, line_widths, line_height = selected_metrics

    if position == "center":
        text_y = (base.height - text_block_height) // 2
    else:
        bottom_margin = int(base.height * 0.08)
        text_y = base.height - text_block_height - bottom_margin

    text_x = (base.width - text_block_width) // 2

    padding_x = max(16, int(base.width * 0.025))
    padding_y = max(12, int(line_height * 0.45))
    box_left = max(0, text_x - padding_x)
    box_top = max(0, text_y - padding_y)
    box_right = min(base.width, text_x + text_block_width + padding_x)
    box_bottom = min(base.height, text_y + text_block_height + padding_y)
    radius = max(10, int(base.width * 0.02))

    draw.rounded_rectangle(
        [(box_left, box_top), (box_right, box_bottom)],
        radius=radius,
        fill=(0, 0, 0, 135),
    )

    y_cursor = text_y
    for index, line in enumerate(selected_lines):
        current_width = line_widths[index]
        line_x = (base.width - current_width) // 2
        draw.text(
            (line_x + 2, y_cursor + 2),
            line,
            font=selected_font,
            fill=(0, 0, 0, 180),
        )
        draw.text(
            (line_x, y_cursor),
            line,
            font=selected_font,
            fill=(255, 255, 255, 245),
        )
        y_cursor += line_height + selected_spacing

    return Image.alpha_composite(base, overlay).convert("RGB")


if "generated_image_url" not in st.session_state:
    st.session_state.generated_image_url = None
if "generated_image_bytes" not in st.session_state:
    st.session_state.generated_image_bytes = None
if "generated_prompt" not in st.session_state:
    st.session_state.generated_prompt = None
if "generated_banner_size" not in st.session_state:
    st.session_state.generated_banner_size = None
if "generated_banner_topic" not in st.session_state:
    st.session_state.generated_banner_topic = None

st.set_page_config(page_title="AI 배너 생성기", page_icon="🖼️", layout="centered")

st.title("AI 배너 생성기")
st.caption("원하는 정보를 입력하고 배너 생성을 시작하세요.")

with st.expander("사용 방법", expanded=True):
    st.markdown(
        """
        1. `배너 주제`, `원하는 문구`, `문구 위치`, `배너 사이즈`를 선택합니다.  
        2. 무료 이미지 생성 엔진으로 배너를 만듭니다 (API 키 불필요).  
        3. `배너 생성하기` 버튼을 누릅니다.  
        4. 생성 결과를 미리보기로 확인하고, `PNG 다운로드` 또는 `로컬에 저장`을 사용합니다.
        """
    )

with st.sidebar:
    st.header("설정")
    st.info("무료 이미지 생성 모드 (API 키 불필요)")

# Main: 배너 생성 폼
with st.form("banner_form"):
    banner_topic = st.text_input("배너 주제", placeholder="예: 여름 세일 프로모션")
    desired_text = st.text_area("원하는 문구", placeholder="예: 최대 50% 할인! 지금 바로 만나보세요.")
    text_position = st.selectbox("문구 위치", ["하단", "중앙"], index=0)
    banner_size = st.selectbox(
        "배너 사이즈",
        [
            "1280x720",
            "1024x1024",
            "1080x1080",
            "1920x1080",
            "1080x1920",
        ],
        index=0,
    )

    submit = st.form_submit_button("배너 생성하기")

if submit:
    if not banner_topic.strip() or not desired_text.strip():
        st.warning("배너 주제와 원하는 문구를 모두 입력해주세요.")
    else:
        with st.spinner("AI가 배너를 생성하고 있습니다..."):
            try:
                position = "center" if text_position == "중앙" else "bottom"
                final_png_bytes, image_url, used_prompt = build_final_banner_png(
                    banner_topic=banner_topic,
                    desired_text=desired_text,
                    selected_size=banner_size,
                    text_position=position,
                )

                st.session_state.generated_image_url = image_url
                st.session_state.generated_image_bytes = final_png_bytes
                st.session_state.generated_prompt = used_prompt
                st.session_state.generated_banner_size = banner_size
                st.session_state.generated_banner_topic = banner_topic
            except Exception as error:
                st.error(f"배너 생성 중 오류가 발생했습니다: {error}")
                st.stop()

if st.session_state.generated_image_url and st.session_state.generated_image_bytes:
    st.success("배너 생성이 완료되었습니다!")
    st.write("이미지 생성 URL")
    st.markdown(f"[이미지 URL 열기]({st.session_state.generated_image_url})")

    preview_image = Image.open(io.BytesIO(st.session_state.generated_image_bytes)).convert("RGB")
    st.image(
        preview_image,
        caption=f"생성된 배너 ({st.session_state.generated_banner_size})",
        use_container_width=True,
    )

    st.download_button(
        label="PNG 다운로드",
        data=st.session_state.generated_image_bytes,
        file_name=build_download_filename(st.session_state.generated_banner_topic),
        mime="image/png",
    )

    if st.button("로컬에 저장"):
        saved_path = save_image_bytes_to_local(
            image_bytes=st.session_state.generated_image_bytes,
            banner_topic=st.session_state.generated_banner_topic,
        )
        st.info(f"저장 완료: {saved_path}")

    with st.expander("자동 생성된 프롬프트 보기"):
        st.write(st.session_state.generated_prompt)
