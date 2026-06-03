---
name: Bug report
about: Create a report to help us improve
title: ''
labels: ''
assignees: ''

---

name: "🐞 Bug Report"
description: "버그 발생 시 제보"
labels: ["bug"]
body:
  - type: textarea
    attributes:
      label: 🐛 버그 설명
      description: 어떤 버그인지 자세히 작성해 주세요.
      placeholder: 예) 특정 페이지에서 버튼이 작동하지 않습니다.
    validations:
      required: true

  - type: textarea
    attributes:
      label: 🎯 재현 방법
      description: 버그가 발생하는 과정을 단계별로 설명해 주세요.
      placeholder: |
        1. 로그인 후 '마이페이지' 클릭
        2. '설정' 메뉴에서 '알림' 클릭
        3. 저장 버튼을 눌렀을 때 반응 없음
    validations:
      required: true

  - type: textarea
    attributes:
      label: 🖥 환경 정보
      description: 사용한 OS, 브라우저, 기기 등을 작성해 주세요.
      placeholder: |
        - OS: macOS 14.1 / Windows 11
        - 브라우저: Chrome 119.0.0
        - 기기: MacBook Pro 16-inch (M1)
        - 도커 사용여부 : 도커 사용함
    validations:
      required: false

  - type: textarea
    attributes:
      label: 📸 스크린샷 (선택)
      description: 가능하다면 스크린샷을 첨부해 주세요.
