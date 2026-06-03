---
name: Custom issue template
about: Describe this issue template's purpose here.
title: ''
labels: ''
assignees: ''

---

name: "📌 Custom Issue"
description: "기타 논의할 사항을 기록"
labels: ["custom"]
body:
  - type: textarea
    attributes:
      label: 📌 피처 개요
      description: 해당 이슈의 주요 개요를 설명해 주세요.
      placeholder: |
        예) 공통 응답 및 예외 핸들러 구현
    validations:
      required: true

  - type: dropdown
    attributes:
      label: ✅ 중요도
      description: 해당 이슈의 중요도를 선택해 주세요.
      options:
        - A (높음)
        - B (보통)
        - C (낮음)
    validations:
      required: true

  - type: dropdown
    attributes:
      label: ✅ 난이도
      description: 해당 이슈의 난이도를 선택해 주세요.
      options:
        - 상 (어려움)
        - 중 (보통)
        - 하 (쉬움)
    validations:
      required: true

  - type: textarea
    attributes:
      label: ✅ 피처 설명
      description: 구현할 기능 또는 논의할 사항에 대한 설명을 작성해 주세요.
      placeholder: |
        - API 응답을 통일하기 위해 ApiResponse 클래스를 구현한다.
    validations:
      required: true

  - type: textarea
    attributes:
      label: ✅ 체크리스트
      description: 할 일을 체크박스 형태로 작성해 주세요.
      placeholder: |
        - [ ] ApiResponse 클래스 구현
    validations:
      required: true

  - type: textarea
    attributes:
      label: ✅ 관련 정보
      description: 관련 문서, 참고 자료 또는 레퍼런스가 있다면 추가해 주세요.
      placeholder: |
        - Spring @RestControllerAdvice, @ExceptionHandler 활용
