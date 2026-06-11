# ADR-0001: Type C 구조화 LLM 벤더를 Anthropic 에서 OpenAI 로 변경

- 상태: 승인됨 (Accepted)
- 날짜: 2026-06-11
- 관련 문서: `docs/OCR_시스템_아키텍처_v3.md`

## 컨텍스트

Type C 자유텍스트(전체 의뢰서의 ~25%)는 CLOVA OCR 텍스트를 LLM 으로 JSON 구조화한다.
초기 설계(아키텍처 v2.0)는 Anthropic Claude Haiku(1차) / Sonnet(승급)을 사용했다.
LLM 은 **텍스트 구조화 전용**이며 이미지 입력은 어떤 경우에도 전달하지 않는다.

## 결정

Type C 구조화 LLM 을 **Anthropic(Haiku/Sonnet) → OpenAI(경량/상위 모델)** 로 변경한다.

- 1차: `LLM_MODEL_PRIMARY` (기본 `gpt-5-mini`, 잠정값)
- 승급: `LLM_MODEL_ESCALATION` (기본 `gpt-5`, 잠정값)
- 모델명은 코드에 하드코딩하지 않고 설정(Settings/환경변수)으로만 지정한다.
- LLM 클라이언트는 `LLMStructurer` Protocol(`app/infra/llm/base.py`)로 추상화 —
  벤더 재교체 시 구현체 1개와 DI(`app/api/deps.py`)만 변경하면 되고,
  승급 체인 로직·DB 스키마·플래그는 무변이다.

## 근거

1. **손글씨 후처리 벤치마크 우위**: 의뢰서 자유텍스트(손글씨 OCR 산출물) 후처리
   품질 비교에서 OpenAI 모델이 우위로 평가됨.
2. **Structured Outputs strict 모드**: `response_format: json_schema + strict: true` 가
   스키마 준수를 API 레벨에서 강제 — JSON 파싱 실패로 인한 재시도/승급 비용을
   구조적으로 절감한다. (pydantic 검증은 2차 방어로 유지)

## 영향

- 플래그 개명: `sonnet_escalated` → `model_escalated` (벤더 종속 명칭의 DB 유입 차단).
- 설정/환경변수: `ANTHROPIC_API_KEY` 제거, `OPENAI_API_KEY` +
  `LLM_MODEL_PRIMARY` / `LLM_MODEL_ESCALATION` 추가.
- **외부 문서 별도 갱신 필요**: 아키텍처 v2.0 문서(PDF)의 "Anthropic API — Haiku/Sonnet"
  및 "Sonnet 승급" 표기는 외부에서 관리되는 산출물이다. 저장소에서는 v2.0 PDF 를 제거하고
  `docs/OCR_시스템_아키텍처_v3.md` 가 대체하지만, 저장소 밖 v2.0 원본(공유 드라이브 등)은
  소유자가 별도 갱신해야 한다. `docs/DentalSync_개발_프롬프트_단계별.md` 의 Step 6 원문은
  이력 기록이므로 수정하지 않는다.
- 모델 기본값(gpt-5-mini/gpt-5)은 **잠정값** — 도입 시점의 OpenAI 라인업·가격 확인 후
  설정 변경만으로 확정한다(코드 변경 불필요, 테스트로 교체 가능성 증명됨).

## 재검토 조건

JSON 포맷 일관성·Type C 필드 정확도가 파일럿 측정에서 기준 미달이면
`LLMStructurer` 인터페이스를 통해 벤더 재전환을 검토한다.
