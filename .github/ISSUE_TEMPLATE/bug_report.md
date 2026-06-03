---
name: Bug report
about: Create a report to help us improve
title: ''
labels: ''
assignees: ''

---

## 🐛 버그 설명

어떤 버그인지 자세히 작성해 주세요.

<!-- 예: 특정 페이지에서 버튼이 작동하지 않습니다. -->

## 🎯 재현 방법

버그가 발생하는 과정을 단계별로 설명해 주세요.

1.
2.
3.

## 🖥 환경 정보

사용한 OS, 브라우저, 기기 등을 작성해 주세요.

* OS:
* 브라우저:
* 기기:
* 도커 사용 여부:

## 📸 스크린샷

가능하다면 스크린샷을 첨부해 주세요.

## ✅ 기대한 동작

원래 기대했던 동작을 작성해 주세요.

<!-- 예: 저장 버튼을 누르면 설정이 저장되고 성공 메시지가 표시되어야 합니다. -->

## ❗ 실제 동작

실제로 발생한 동작을 작성해 주세요.

<!-- 예: 저장 버튼을 눌러도 아무 반응이 없습니다. -->

## 🔍 추가 정보

버그 해결에 도움이 될 만한 로그, 에러 메시지, 참고 사항이 있다면 작성해 주세요.

```text
에러 로그가 있다면 여기에 붙여 주세요.
```

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
