import os
import uuid
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Literal
from io import BytesIO
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException, Header, Depends, Request as FastAPIRequest
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl, Field
from PIL import Image, ImageDraw, ImageFont
import uvicorn


BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "generated"
VIDEO_DIR = GENERATED_DIR / "videos"
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AI Product Shorts Automation API",
    version="1.4.0",
    description="GPT Actions API with Korean font support, product image rendering, and MP4 draft rendering.",
)

app.mount("/generated", StaticFiles(directory=str(GENERATED_DIR)), name="generated")


def verify_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    authorization: Optional[str] = Header(default=None),
):
    expected_api_key = os.getenv("ACTION_API_KEY")

    if not expected_api_key:
        raise HTTPException(
            status_code=500,
            detail="ACTION_API_KEY is not configured on the server.",
        )

    bearer_key = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_key = authorization.split(" ", 1)[1].strip()

    provided_key = x_api_key or bearer_key

    if provided_key != expected_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key.",
        )

    return True


class AnalyzeUrlRequest(BaseModel):
    url: HttpUrl
    source: Optional[Literal["coupang", "naver", "smartstore", "general"]] = "general"


class ProductAnalysis(BaseModel):
    product_name: str
    category: str
    price: Optional[int] = None
    target_customer: List[str]
    selling_points: List[str]
    risk_level: Literal["low", "medium", "high"]
    risk_reasons: List[str]
    shorts_score: int
    notes: List[str]


class ShortsPackageRequest(BaseModel):
    product_name: str
    category: Optional[str] = "생활용품"
    selling_points: List[str] = Field(default_factory=list)
    affiliate_type: Optional[
        Literal[
            "coupang_partners",
            "general_affiliate",
            "direct_sale",
            "sponsored",
            "unknown",
        ]
    ] = "unknown"
    risk_level: Optional[Literal["low", "medium", "high"]] = "low"


class ShortsPackage(BaseModel):
    hook_lines: List[str]
    script_15s: str
    script_30s: str
    scene_plan: List[str]
    captions: List[str]
    youtube_titles: List[str]
    tiktok_titles: List[str]
    description: str
    pinned_comment: str
    hashtags: List[str]
    upload_checklist: List[str]


class RenderDraftRequest(BaseModel):
    title: str
    script: str
    captions: List[str] = Field(default_factory=list)
    product_images: List[str] = Field(default_factory=list)
    aspect_ratio: Optional[str] = "9:16"
    duration: Optional[int] = 30
    voice: Optional[str] = "korean_female_fast"


def guess_source(url: str) -> str:
    u = url.lower()
    if "coupang" in u:
        return "coupang"
    if "naver" in u or "smartstore" in u:
        return "naver"
    return "general"


def disclosure_text(affiliate_type: str) -> str:
    if affiliate_type == "coupang_partners":
        return "이 게시물은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
    if affiliate_type == "general_affiliate":
        return "이 게시물은 제휴마케팅 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받을 수 있습니다."
    if affiliate_type == "direct_sale":
        return "해당 상품은 판매자가 직접 소개하는 상품입니다."
    if affiliate_type == "sponsored":
        return "이 콘텐츠는 브랜드로부터 제품 또는 광고비를 제공받아 제작되었습니다."
    return "이 콘텐츠에는 광고/제휴/판매 목적의 정보가 포함될 수 있습니다."


def font_candidates() -> List[Path]:
    candidates = [
        BASE_DIR / "fonts" / "NotoSansKR-Regular.ttf",
        BASE_DIR / "NotoSansKR-Regular.ttf",
        BASE_DIR / "fonts" / "NotoSansKR-VariableFont_wght.ttf",
        BASE_DIR / "NotoSansKR-VariableFont_wght.ttf",
        BASE_DIR / "서체" / "NotoSansKR-Regular.ttf",
        BASE_DIR / "서체" / "NotoSansKR-VariableFont_wght.ttf",
        Path.cwd() / "fonts" / "NotoSansKR-Regular.ttf",
        Path.cwd() / "NotoSansKR-Regular.ttf",
        Path.cwd() / "fonts" / "NotoSansKR-VariableFont_wght.ttf",
        Path.cwd() / "NotoSansKR-VariableFont_wght.ttf",
        Path.cwd() / "서체" / "NotoSansKR-Regular.ttf",
        Path.cwd() / "서체" / "NotoSansKR-VariableFont_wght.ttf",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansKR-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]

    search_dirs = [
        BASE_DIR,
        BASE_DIR / "fonts",
        BASE_DIR / "서체",
        Path.cwd(),
        Path.cwd() / "fonts",
        Path.cwd() / "서체",
    ]

    patterns = [
        "NotoSansKR*.ttf",
        "NotoSansKR*.otf",
        "NotoSansCJK*.ttc",
        "*Noto*KR*.ttf",
        "*Noto*Korean*.ttf",
    ]

    for folder in search_dirs:
        if folder.exists() and folder.is_dir():
            for pattern in patterns:
                candidates.extend(folder.glob(pattern))

    unique = []
    seen = set()

    for path in candidates:
        resolved = str(path)
        if resolved not in seen:
            unique.append(path)
            seen.add(resolved)

    return unique


@lru_cache(maxsize=1)
def selected_font_path() -> Optional[str]:
    for path in font_candidates():
        try:
            if path.exists() and path.is_file() and path.stat().st_size > 1000:
                font = ImageFont.truetype(str(path), size=40)
                mask = font.getmask("한글테스트")
                bbox = mask.getbbox()
                if bbox is not None:
                    return str(path)
        except Exception:
            continue

    return None


def find_font(size: int):
    path = selected_font_path()

    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass

    return ImageFont.load_default()


def download_product_image(url: str, out_path: Path) -> Optional[Path]:
    """
    상품 이미지 URL을 다운로드해서 Render 서버 임시 폴더에 저장합니다.
    쿠팡/쇼핑몰 이미지가 차단될 수 있으므로 User-Agent를 붙여 시도합니다.
    """
    try:
        req = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            },
        )

        with urlopen(req, timeout=15) as response:
            data = response.read(10 * 1024 * 1024)

        img = Image.open(BytesIO(data)).convert("RGB")
        img.save(out_path, "JPEG", quality=92)

        return out_path

    except Exception:
        return None


def prepare_product_images(urls: List[str], job_dir: Path) -> List[Path]:
    image_paths = []

    for idx, url in enumerate(urls or [], start=1):
        if not url:
            continue

        out_path = job_dir / f"product_{idx:03d}.jpg"
        saved = download_product_image(str(url), out_path)

        if saved and saved.exists():
            image_paths.append(saved)

    return image_paths


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
    lines = []
    current = ""

    for char in text:
        test = current + char
        bbox = draw.textbbox((0, 0), test, font=font)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = char

    if current:
        lines.append(current)

    return lines


def draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: List[str],
    font,
    y: int,
    fill: str,
    frame_width: int,
    line_gap: int = 12,
    stroke_width: int = 0,
    stroke_fill: str = "#000000",
):
    for line in lines:
        bbox = draw.textbbox(
            (0, 0),
            line,
            font=font,
            stroke_width=stroke_width,
        )
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (frame_width - text_width) // 2

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )

        y += text_height + line_gap

    return y


def make_frame(
    title: str,
    caption: str,
    index: int,
    total: int,
    out_path: Path,
    product_image_path: Optional[Path] = None,
):
    width, height = 720, 1280

    img = Image.new("RGB", (width, height), "#111827")
    draw = ImageDraw.Draw(img)

    # 배경 그라데이션
    for y in range(height):
        shade = int(17 + (y / height) * 35)
        color = (shade, shade + 8, shade + 22)
        draw.line([(0, y), (width, y)], fill=color)

    title_font = find_font(42)
    caption_font = find_font(48)
    small_font = find_font(24)
    badge_font = find_font(22)

    badge = f"{index}/{total} SHORTS DRAFT"

    draw.rounded_rectangle((40, 45, 680, 100), radius=22, fill="#2563eb")
    badge_bbox = draw.textbbox((0, 0), badge, font=badge_font)
    badge_x = (width - (badge_bbox[2] - badge_bbox[0])) // 2
    draw.text((badge_x, 60), badge, font=badge_font, fill="white")

    title_lines = wrap_text(draw, title, title_font, 620)
    draw_centered_lines(
        draw,
        title_lines[:2],
        title_font,
        145,
        "white",
        width,
        14,
        stroke_width=2,
        stroke_fill="#000000",
    )

    has_product_image = (
        product_image_path is not None
        and product_image_path.exists()
        and product_image_path.is_file()
    )

    if has_product_image:
        card_left, card_top, card_right, card_bottom = 60, 295, 660, 735

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        overlay_draw.rounded_rectangle(
            (card_left, card_top, card_right, card_bottom),
            radius=36,
            fill=(255, 255, 255, 235),
            outline=(255, 255, 255, 180),
            width=3,
        )

        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

        try:
            product_img = Image.open(product_image_path).convert("RGB")
            product_img.thumbnail((540, 390), Image.LANCZOS)

            px = card_left + ((card_right - card_left) - product_img.width) // 2
            py = card_top + ((card_bottom - card_top) - product_img.height) // 2

            img.paste(product_img, (px, py))

        except Exception:
            pass

        draw = ImageDraw.Draw(img)

        box_top = 775
        box_bottom = 1015
        footer_y = 1060

    else:
        box_top = 430
        box_bottom = 820
        footer_y = 1010

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    overlay_draw.rounded_rectangle(
        (45, box_top, 675, box_bottom),
        radius=38,
        fill=(0, 0, 0, 150),
        outline=(255, 255, 255, 80),
        width=3,
    )

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    caption_lines = wrap_text(draw, caption, caption_font, 590)

    line_height = 64
    total_text_height = min(len(caption_lines), 4) * line_height
    start_y = box_top + ((box_bottom - box_top - total_text_height) // 2)

    draw_centered_lines(
        draw,
        caption_lines[:4],
        caption_font,
        start_y,
        "white",
        width,
        14,
        stroke_width=3,
        stroke_fill="#000000",
    )

    footer_1 = "제품 정보는 고정댓글 또는 프로필 링크에서 확인하세요"
    footer_2 = "쿠팡 파트너스 활동으로 수수료를 제공받을 수 있습니다"

    footer_lines_1 = wrap_text(draw, footer_1, small_font, 620)
    footer_lines_2 = wrap_text(draw, footer_2, small_font, 620)

    y = footer_y
    y = draw_centered_lines(
        draw,
        footer_lines_1,
        small_font,
        y,
        "#facc15",
        width,
        10,
        stroke_width=1,
        stroke_fill="#000000",
    )

    y += 16

    draw_centered_lines(
        draw,
        footer_lines_2,
        small_font,
        y,
        "#d1d5db",
        width,
        10,
        stroke_width=1,
        stroke_fill="#000000",
    )

    img.save(out_path, "PNG")


def split_script_to_captions(script: str, max_items: int = 6) -> List[str]:
    raw = script.replace("\n", " ").strip()

    if not raw:
        return ["상품 포인트를 확인해보세요"]

    separators = [".", "!", "?", "。", "…"]
    parts = []
    current = ""

    for char in raw:
        current += char

        if char in separators:
            cleaned = current.strip()

            if cleaned:
                parts.append(cleaned)

            current = ""

    if current.strip():
        parts.append(current.strip())

    if len(parts) <= 1:
        chunk_size = max(18, len(raw) // max_items)
        parts = [
            raw[i : i + chunk_size].strip()
            for i in range(0, len(raw), chunk_size)
        ]

    return parts[:max_items]


def create_mp4_from_frames(frames: List[Path], output_path: Path, duration: int):
    if not frames:
        raise ValueError("No frames to render")

    ffmpeg_path = shutil.which("ffmpeg")

    if ffmpeg_path is None:
        raise RuntimeError("ffmpeg is not installed or not available in PATH")

    per_slide = max(1.5, duration / len(frames))
    concat_file = output_path.parent / "frames.txt"

    with concat_file.open("w", encoding="utf-8") as f:
        for frame in frames:
            f.write(f"file '{frame.resolve().as_posix()}'\n")
            f.write(f"duration {per_slide}\n")

        f.write(f"file '{frames[-1].resolve().as_posix()}'\n")

    cmd = [
        ffmpeg_path,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-vf",
        "fps=24,format=yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    completed = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )

    if completed.returncode != 0:
        raise RuntimeError(completed.stderr[-2000:])


@app.get("/health", operation_id="healthCheck")
@app.get("/health/", include_in_schema=False)
def health():
    return {
        "ok": True,
        "status": "healthy",
        "service": "ai-product-shorts-actions",
        "version": "1.4.0",
    }


@app.get("/debug/font", dependencies=[Depends(verify_api_key)])
def debug_font():
    selected = selected_font_path()
    checked = []

    for path in font_candidates():
        item = {
            "path": str(path),
            "exists": path.exists(),
            "is_file": path.is_file() if path.exists() else False,
            "size": path.stat().st_size if path.exists() and path.is_file() else None,
            "loadable": False,
            "error": None,
        }

        if path.exists() and path.is_file():
            try:
                font = ImageFont.truetype(str(path), size=40)
                item["loadable"] = True

                try:
                    item["font_name"] = font.getname()
                except Exception:
                    item["font_name"] = None

            except Exception as e:
                item["error"] = str(e)

        checked.append(item)

    return {
        "ok": selected is not None,
        "base_dir": str(BASE_DIR),
        "cwd": str(Path.cwd()),
        "selected_font_path": selected,
        "message": "selected_font_path가 NotoSansKR로 나오면 한글 자막이 정상 표시됩니다.",
        "checked_fonts": checked,
    }


@app.get("/debug/ffmpeg", dependencies=[Depends(verify_api_key)])
def debug_ffmpeg():
    ffmpeg_path = shutil.which("ffmpeg")

    if not ffmpeg_path:
        return {
            "ok": False,
            "message": "ffmpeg를 찾을 수 없습니다.",
            "ffmpeg_path": None,
        }

    try:
        completed = subprocess.run(
            [ffmpeg_path, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )

        return {
            "ok": completed.returncode == 0,
            "ffmpeg_path": ffmpeg_path,
            "version": completed.stdout.splitlines()[0] if completed.stdout else None,
            "stderr": completed.stderr[:500],
        }

    except Exception as e:
        return {
            "ok": False,
            "ffmpeg_path": ffmpeg_path,
            "message": str(e),
        }


@app.get("/debug/render-ready", dependencies=[Depends(verify_api_key)])
def debug_render_ready():
    return {
        "ok": True,
        "generated_dir_exists": GENERATED_DIR.exists(),
        "video_dir_exists": VIDEO_DIR.exists(),
        "ffmpeg_path": shutil.which("ffmpeg"),
        "selected_font_path": selected_font_path(),
        "message": "renderDraft 준비 상태 확인 완료",
    }


@app.post("/debug/echo-render", dependencies=[Depends(verify_api_key)])
def debug_echo_render(req: RenderDraftRequest):
    return {
        "ok": True,
        "message": "renderDraft 입력값 수신 성공",
        "received": {
            "title": req.title,
            "script": req.script,
            "captions": req.captions,
            "product_images": req.product_images,
            "aspect_ratio": req.aspect_ratio,
            "duration": req.duration,
            "voice": req.voice,
        },
    }


@app.post(
    "/product/analyze-url",
    response_model=ProductAnalysis,
    dependencies=[Depends(verify_api_key)],
)
def analyze_product_url(req: AnalyzeUrlRequest):
    source = req.source or guess_source(str(req.url))

    if source == "coupang":
        product_name = "쿠팡 상품 링크 기반 추천 상품"
        category = "쿠팡/쇼핑상품"
    elif source in ["naver", "smartstore"]:
        product_name = "네이버 쇼핑 링크 기반 추천 상품"
        category = "네이버/스마트스토어 상품"
    else:
        product_name = "링크 기반 추천 상품"
        category = "일반 쇼핑상품"

    return ProductAnalysis(
        product_name=product_name,
        category=category,
        price=None,
        target_customer=[
            "가격 비교 후 구매하는 고객",
            "숏츠로 빠르게 상품을 확인하는 고객",
            "생활 편의 상품 관심 고객",
        ],
        selling_points=[
            "사용 상황을 짧게 보여주기 좋음",
            "상품 사진 기반 소개 가능",
            "후킹형 숏츠 제작 가능",
        ],
        risk_level="low",
        risk_reasons=[
            "초기 분석 단계라 정확한 인증/브랜드/원산지 확인 필요",
        ],
        shorts_score=72,
        notes=[
            "인증 적용 버전입니다.",
            "실제 가격, 이미지, 리뷰 분석은 다음 단계에서 API 연동 후 추가하세요.",
            "등록/업로드 전 광고 고지와 저작권, 상품 표현을 검수하세요.",
        ],
    )


@app.post(
    "/shorts/generate-package",
    response_model=ShortsPackage,
    dependencies=[Depends(verify_api_key)],
)
def generate_shorts_package(req: ShortsPackageRequest):
    product = req.product_name
    category = req.category or "생활용품"

    points = req.selling_points or [
        "사용하기 편함",
        "일상 문제 해결",
        "짧은 영상으로 설명하기 쉬움",
    ]

    disclosure = disclosure_text(req.affiliate_type or "unknown")
    point_text = " / ".join(points[:3])

    return ShortsPackage(
        hook_lines=[
            f"{category} 찾는 분들, 이거 한 번 보세요",
            "이런 불편함 있던 분들은 확인해보세요",
            f"{product} 실제 사용 포인트",
            "생각보다 이런 걸 찾는 분들이 많습니다",
            "사기 전에 이 포인트만 확인하세요",
        ],
        script_15s=(
            f"{category} 찾는 분들, 이 상품 한 번 확인해보세요. "
            f"핵심 포인트는 {point_text}입니다. "
            "과장해서 말하기보다 실제 사용 상황을 보고 판단하는 게 좋습니다. "
            "제품 정보는 고정댓글 또는 프로필 링크에서 확인해보세요."
        ),
        script_30s=(
            f"{product}은 {category} 쪽에서 숏츠로 소개하기 좋은 상품입니다. "
            f"첫 번째 포인트는 {points[0] if len(points) > 0 else '사용 편의성'}입니다. "
            f"두 번째는 {points[1] if len(points) > 1 else '일상 문제 해결'}입니다. "
            f"세 번째는 {points[2] if len(points) > 2 else '짧은 영상으로 설명하기 쉬운 점'}입니다. "
            "다만 구매 전 옵션, 사이즈, 배송비, 후기 확인은 꼭 필요합니다. "
            "제품 정보는 고정댓글 또는 프로필 링크에서 확인해보세요."
        ),
        scene_plan=[
            "1컷: 불편한 상황 또는 궁금증을 1초 안에 보여주기",
            "2컷: 상품 이미지/실물 클로즈업",
            "3컷: 사용하는 장면 또는 사용 전후 비교",
            "4컷: 장점 3개를 큰 자막으로 표시",
            "5컷: 고정댓글/프로필 링크 안내와 광고 고지",
        ],
        captions=[
            "이런 불편함 있던 분들?",
            "핵심 포인트 3개만 보세요",
            "구매 전 옵션/후기 확인 필수",
            "제품 정보는 고정댓글 확인",
        ],
        youtube_titles=[
            f"{category} 찾는 분들 이거 확인해보세요",
            f"{product} 사기 전 확인할 포인트",
            "짧게 보는 생활 꿀템 추천",
            "이런 분들은 한 번 확인해보세요",
            "고정댓글에 제품 정보 남겨둘게요",
        ],
        tiktok_titles=[
            "이거 은근 찾는 사람 많음",
            "생활 꿀템 15초 정리",
            "사기 전 이 포인트 확인",
            "고정댓글 확인",
            "추천템 빠르게 보기",
        ],
        description=f"제품 정보는 고정댓글 또는 프로필 링크에서 확인하세요.\n\n{disclosure}",
        pinned_comment=f"상품 링크: [여기에 링크 입력]\n{disclosure}",
        hashtags=[
            "#쇼츠",
            "#추천템",
            "#생활꿀템",
            "#제품추천",
            "#상품리뷰",
        ],
        upload_checklist=[
            "대가성/광고 고지 문구 포함",
            "과장 표현 제거",
            "상품 링크 정상 작동 확인",
            "상품 이미지 사용 권한 확인",
            "자막이 모바일에서 잘 보이는지 확인",
            "위험 카테고리인 경우 자동 업로드 보류",
        ],
    )


@app.post("/video/render-draft", dependencies=[Depends(verify_api_key)])
def render_video_draft(req: RenderDraftRequest, request: FastAPIRequest):
    job_id = f"draft-{uuid.uuid4().hex[:10]}"
    job_dir = VIDEO_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    captions = req.captions or split_script_to_captions(req.script)
    captions = [c.strip() for c in captions if c and c.strip()]

    if not captions:
        captions = ["상품 포인트를 확인해보세요"]

    product_image_paths = prepare_product_images(req.product_images, job_dir)

    duration = req.duration or 30

    if duration < 5:
        duration = 5

    if duration > 60:
        duration = 60

    frames = []

    try:
        for idx, caption in enumerate(captions, start=1):
            frame_path = job_dir / f"frame_{idx:03d}.png"

            product_image_path = None

            if product_image_paths:
                product_image_path = product_image_paths[(idx - 1) % len(product_image_paths)]

            make_frame(
                title=req.title,
                caption=caption,
                index=idx,
                total=len(captions),
                out_path=frame_path,
                product_image_path=product_image_path,
            )

            frames.append(frame_path)

        output_path = job_dir / "output.mp4"
        create_mp4_from_frames(frames, output_path, duration)

        base_url = str(request.base_url).rstrip("/")
        preview_url = f"{base_url}/generated/videos/{job_id}/output.mp4"

        return {
            "job_id": job_id,
            "status": "completed",
            "message": "9:16 MP4 영상 초안이 생성되었습니다. 상품 이미지 URL이 있으면 영상 중앙에 표시됩니다.",
            "preview_url": preview_url,
            "font_path": selected_font_path(),
            "product_images_received": len(req.product_images or []),
            "product_images_loaded": len(product_image_paths),
        }

    except Exception as e:
        return {
            "job_id": job_id,
            "status": "failed",
            "message": f"영상 생성 중 오류가 발생했습니다: {str(e)}",
            "preview_url": None,
            "font_path": selected_font_path(),
            "product_images_received": len(req.product_images or []),
            "product_images_loaded": len(product_image_paths),
        }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
