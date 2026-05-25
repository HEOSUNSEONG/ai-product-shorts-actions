import os
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Literal
import uvicorn

app = FastAPI(
    title="AI Product Shorts Automation API",
    version="1.1.0",
    description="GPT Actions API with API key authentication."
)

def verify_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
    authorization: Optional[str] = Header(default=None)
):
    expected_api_key = os.getenv("ACTION_API_KEY")
    if not expected_api_key:
        raise HTTPException(status_code=500, detail="ACTION_API_KEY is not configured on the server.")

    bearer_key = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_key = authorization.split(" ", 1)[1].strip()

    provided_key = x_api_key or bearer_key
    if provided_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
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
    selling_points: Optional[List[str]] = []
    affiliate_type: Optional[Literal["coupang_partners", "general_affiliate", "direct_sale", "sponsored", "unknown"]] = "unknown"
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
    captions: Optional[List[str]] = []
    product_images: Optional[List[str]] = []
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

@app.get("/health", operation_id="healthCheck")
def health():
    return {
        "ok": True,
        "status": "healthy",
        "service": "ai-product-shorts-actions"
    }

@app.post("/product/analyze-url", response_model=ProductAnalysis, dependencies=[Depends(verify_api_key)])
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
        target_customer=["가격 비교 후 구매하는 고객", "숏츠로 빠르게 상품을 확인하는 고객", "생활 편의 상품 관심 고객"],
        selling_points=["사용 상황을 짧게 보여주기 좋음", "상품 사진 기반 소개 가능", "후킹형 숏츠 제작 가능"],
        risk_level="low",
        risk_reasons=["초기 분석 단계라 정확한 인증/브랜드/원산지 확인 필요"],
        shorts_score=72,
        notes=["인증 적용 버전입니다.", "실제 가격, 이미지, 리뷰 분석은 다음 단계에서 API 연동 후 추가하세요.", "등록/업로드 전 광고 고지와 저작권, 상품 표현을 검수하세요."]
    )

@app.post("/shorts/generate-package", response_model=ShortsPackage, dependencies=[Depends(verify_api_key)])
def generate_shorts_package(req: ShortsPackageRequest):
    product = req.product_name
    category = req.category or "생활용품"
    points = req.selling_points or ["사용하기 편함", "일상 문제 해결", "짧은 영상으로 설명하기 쉬움"]
    disclosure = disclosure_text(req.affiliate_type)
    point_text = " / ".join(points[:3])

    return ShortsPackage(
        hook_lines=[
            f"{category} 찾는 분들, 이거 한 번 보세요",
            "이런 불편함 있던 분들은 확인해보세요",
            f"짧게 보여드릴게요. {product} 실제 사용 포인트",
            "생각보다 이런 걸 찾는 분들이 많습니다",
            "사기 전에 이 포인트만 확인하세요"
        ],
        script_15s=f"{category} 찾는 분들, 이 상품 한 번 확인해보세요. 핵심 포인트는 {point_text}입니다. 과장해서 말하기보다 실제 사용 상황을 보고 판단하는 게 좋습니다. 제품 정보는 고정댓글 또는 프로필 링크에서 확인해보세요.",
        script_30s=f"{product}은 {category} 쪽에서 숏츠로 소개하기 좋은 상품입니다. 첫 번째 포인트는 {points[0] if len(points)>0 else '사용 편의성'}입니다. 두 번째는 {points[1] if len(points)>1 else '일상 문제 해결'}입니다. 세 번째는 {points[2] if len(points)>2 else '짧은 영상으로 설명하기 쉬운 점'}입니다. 다만 구매 전 옵션, 사이즈, 배송비, 후기 확인은 꼭 필요합니다. 제품 정보는 고정댓글 또는 프로필 링크에서 확인해보세요.",
        scene_plan=["1컷: 불편한 상황 또는 궁금증을 1초 안에 보여주기", "2컷: 상품 이미지/실물 클로즈업", "3컷: 사용하는 장면 또는 사용 전후 비교", "4컷: 장점 3개를 큰 자막으로 표시", "5컷: 고정댓글/프로필 링크 안내와 광고 고지"],
        captions=["이런 불편함 있던 분들?", "핵심 포인트 3개만 보세요", "구매 전 옵션/후기 확인 필수", "제품 정보는 고정댓글 확인"],
        youtube_titles=[f"{category} 찾는 분들 이거 확인해보세요", f"{product} 사기 전 확인할 포인트", "짧게 보는 생활 꿀템 추천", "이런 분들은 한 번 확인해보세요", "고정댓글에 제품 정보 남겨둘게요"],
        tiktok_titles=["이거 은근 찾는 사람 많음", "생활 꿀템 15초 정리", "사기 전 이 포인트 확인", "고정댓글 확인", "추천템 빠르게 보기"],
        description=f"제품 정보는 고정댓글 또는 프로필 링크에서 확인하세요.\n\n{disclosure}",
        pinned_comment=f"상품 링크: [여기에 링크 입력]\n{disclosure}",
        hashtags=["#쇼츠", "#추천템", "#생활꿀템", "#제품추천", "#상품리뷰"],
        upload_checklist=["대가성/광고 고지 문구 포함", "과장 표현 제거", "상품 링크 정상 작동 확인", "상품 이미지 사용 권한 확인", "자막이 모바일에서 잘 보이는지 확인", "위험 카테고리인 경우 자동 업로드 보류"]
    )

@app.post("/video/render-draft", dependencies=[Depends(verify_api_key)])
def render_video_draft(req: RenderDraftRequest):
    return {
        "job_id": "draft-demo-001",
        "status": "not_implemented_demo",
        "message": "인증 적용 Starter 버전입니다. 다음 단계에서 실제 9:16 MP4 렌더링 기능을 추가하세요.",
        "preview_url": None
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
