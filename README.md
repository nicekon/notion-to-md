# Notion to Markdown

Notion database/data source에서 조건에 맞는 페이지를 조회하고, 페이지 본문과 댓글을 Markdown 파일로 저장하는 로컬 Python 웹앱입니다.

## 기능

- Notion DB URL 또는 data source ID 입력
- 날짜 필터 모드: 전체, 시작일 이후, 종료일 이전, 기간
- 담당자 이름/이메일 로컬 필터
- 상태, select, multi-select 필터
- 제목, 속성, 본문 키워드 검색
- 선택 시 검색 결과 표에 본문 일부 미리보기 표시
- 기간, 담당자, 상태/옵션 속성 자동 추천
- 페이지 본문 Markdown 저장
- 페이지 댓글 및 본문 블록 댓글 저장
- 댓글 작성자 이름 보강
- 댓글이 있는 페이지만 저장하는 옵션
- 댓글만 저장하는 옵션
- YAML frontmatter, Properties 표, 댓글 섹션 포함 여부 선택
- 댓글이 없을 때 Comments 섹션 자동 생략
- 페이지별 실패/경고 기록 및 부분 성공 처리
- export 조건과 결과를 `_export_summary.md`로 자동 기록
- 저장 파일명 형식 선택 및 중복 파일명 자동 회피
- 저장 전 예상 파일명 미리보기
- 파일명 날짜는 `YYYY-MM-DD` 또는 `YYYY-MM-DD_HH-mm` 형식으로 자동 정리
- DB/검색/내보내기 설정 프리셋 저장 및 불러오기
- 생성된 Markdown 파일 ZIP 다운로드

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env`에 Notion integration token을 넣습니다.

```bash
NOTION_TOKEN=secret_xxx
```

기본 Notion API version은 `2025-09-03`입니다. 이 버전에서 database와 data source가 분리된 최신 API를 사용합니다.

Notion에서 해당 integration을 조회할 DB에 초대해야 합니다.

## 실행

```bash
streamlit run app.py
```

브라우저에서 열린 로컬 앱에 DB URL과 검색 조건을 입력한 뒤 `미리 조회`로 결과를 확인하고, 선택한 페이지를 Markdown으로 저장하면 `exports/` 아래에 파일이 생성됩니다.

현재 앱 흐름은 세 단계입니다.

1. `스키마 불러오기`로 DB/data source 속성을 읽습니다.
2. 검색 조건을 정하고 `미리 조회`로 후보 페이지를 확인합니다.
3. 결과 표에서 저장할 페이지를 선택한 뒤 Markdown으로 저장하거나 ZIP으로 다운로드합니다.

## 참고

- 담당자 필터는 Notion API에서 직접 이름 검색을 하지 않고, 조회된 페이지의 people 속성을 로컬에서 필터링합니다.
- 키워드 검색도 본문 Markdown까지 가져온 뒤 로컬에서 필터링합니다.
- Notion comments API는 권한과 API 제공 범위에 따라 조회 가능한 댓글이 제한될 수 있습니다.
- 댓글 작성자 이름 보강은 Notion integration의 user information capability가 필요합니다. 권한이 없으면 작성자 ID로 fallback합니다.
- 프리셋은 `presets.json`에 저장되며, Notion API token은 저장하지 않습니다.
- 날짜 필터의 `기간` 모드에서 종료일을 비우면 시작일과 같은 날짜로 처리합니다.

## 개발 인수인계

새 Codex/에이전트 세션에서 이어서 작업할 때는 `AGENTS.md`와 `docs/project-state.md`를 먼저 읽으면 됩니다.

- `AGENTS.md`: 짧은 자동 로드 지침, setup/test/architecture map
- `docs/project-state.md`: 현재 구현 상태, 제약, 다음 작업, 새 세션용 handoff prompt
- `docs/decisions/`: 오래 유지해야 하는 결정 기록
