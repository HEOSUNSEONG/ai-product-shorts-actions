# AI Product Shorts GPTS Starter

이 프로젝트는 GPTS Actions에 붙일 수 있는 FastAPI 기본 서버입니다.

## 1. 포함된 기능

- `/health`: 서버 상태 확인
- `/product/analyze-url`: 쿠팡/네이버 등 상품 링크를 starter 방식으로 분석
- `/shorts/generate-package`: 숏츠 대본, 제목, 설명, 고정댓글, 해시태그 생성
- `/video/render-draft`: 다음 단계 영상 렌더링 자리

## 2. 로컬 실행

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

브라우저에서 확인:

```text
http://localhost:8000/docs
```

## 3. GitHub에 올릴 파일

- main.py
- requirements.txt
- openapi.yaml
- .env.example
- README.md

실제 API 키는 절대 GitHub에 올리지 마세요.

## 4. Render 배포 설정

Render Web Service 생성 시:

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

## 5. GPTS Actions 설정

1. GPT 편집 화면으로 이동
2. Configure
3. Actions
4. Create new action
5. Authentication: 처음에는 None
6. Schema: openapi.yaml 내용 붙여넣기
7. servers.url을 내 Render 주소로 변경
8. Preview에서 테스트

## 6. 다음에 추가할 기능

- 네이버 쇼핑 검색 API
- 아이템스카우트 CSV/엑셀 분석
- 상품 이미지 분석
- 9:16 MP4 자동 생성
- 유튜브 비공개 업로드
- 틱톡 초안 업로드
- 성과 분석
