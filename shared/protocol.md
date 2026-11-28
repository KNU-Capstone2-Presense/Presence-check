# 인증 통신 규격 v1

WebSocket 텍스트 JSON 메시지를 사용합니다. 앱 설정에 넣는 주소만 바꾸어 Direct/Relay 경로를 선택합니다. 이미지와 RTT 신호는 같은 연결을 사용합니다. 바이너리 메시지는 프록시가 전달하지만 앱 프로토콜에서는 사용하지 않습니다.

## QR
JSON 또는 아래 키를 query string으로 담은 URL입니다. QR에서 서버 주소를 자동 적용하지 않습니다.

```json
{"session_id":"class-001","place_id":"room-101","token":"server-issued-token","expires_at":"2026-12-01T12:00:00+09:00"}
```

## 앱 → 서버: auth_request
```json
{"type":"auth_request","attempt_id":"UUID","student_id":"20260001","session_id":"class-001","place_id":"room-101","token":"server-issued-token","image":{"mime_type":"image/jpeg","data_base64":"..."}}
```
이미지는 긴 변 최대 1600px, JPEG 품질 0.88입니다. 주변 환경은 자르지 않습니다. 장소 검증 팀과 해상도 규격 확정 후 조정할 수 있습니다. 서버는 세션, 토큰, 만료 시간, 이미지 크기와 실제 형식을 검증해야 합니다. attempt_id 중복 요청은 재승인하지 않도록 처리합니다.

## 서버 → 앱: auth_received
```json
{"type":"auth_received","attempt_id":"UUID"}
```

## RTT
서버는 이미지 수신 완료 후 장소 검증 연산과 겹치지 않게 측정합니다. 연결이 준비된 상태에서 짧은 요청을 순차적으로 전송합니다. 서버의 단조 증가 시계로 send 직전과 일치하는 echo 수신 직후를 기록합니다. 지연의 단위는 ms입니다.

```json
{"type":"rtt_probe","attempt_id":"UUID","probe_id":"1","nonce":"fresh-random-value"}
```
```json
{"type":"rtt_echo","attempt_id":"UUID","probe_id":"1","nonce":"fresh-random-value"}
```
앱은 현재 인증 시도에 해당하는 probe만 즉시 반환합니다. 서버가 nonce, 연결, probe_id 및 중복/만료 응답을 검증합니다. 서버는 표본과 사용한 대표값·임계값을 저장해야 합니다. 앱은 RTT를 계산하거나 결과를 위조해서 표시하지 않습니다. 브라우저 앱 스케줄링도 RTT에 포함되므로 AWS 실험 임계값은 재사용하지 않습니다.

단순 nonce 반환은 학생 앱의 암호학적 인증이 아닙니다. 이 버전은 정직한 앱과 단순 전달 프록시의 시연이며, 악의적인 프록시의 대리 응답이나 학생 사칭을 방어하지 않습니다.

## 서버 → 앱: auth_result
```json
{"type":"auth_result","attempt_id":"UUID","decision":"approved","place":{"decision":"장소 일치","inlier_count":184,"inlier_ratio":0.8},"relay":{"decision":"지연 기준 충족","rtt_ms":3.2,"threshold_ms":5.0}}
```
위 숫자는 형식 예시이며 실제 결과가 아닙니다. decision은 approved/rejected/review 중 하나입니다. 장소 기능 미연동 상태에서 승인을 생성하지 않습니다. result 수신 후 앱의 인증 시도는 종료됩니다.

## 오류
```json
{"type":"error","attempt_id":"UUID","message":"세션이 만료되었습니다"}
```
앱은 인증 응답을 최대 60초 기다립니다. 시간 초과가 서버 작업 취소를 의미하지 않으므로 서버 측 결과 조회/취소 정책은 관리자 서버 구현 시 추가합니다.

## 관리자 서버 기반 구현
- 관리자 화면: `http://127.0.0.1:8000/`
- 학생 WebSocket: `ws://127.0.0.1:8000/ws`
- 세션 생성: `POST /api/sessions` (place_id). 같은 place_id의 기존 활성 세션은 종료되며, 응답의 closed_sessions에 종료한 개수가 담깁니다.
- QR PNG: `GET /api/sessions/{session_id}/qr`
- 세션 종료: `POST /api/sessions/{session_id}/close`
- 인증 결과 목록: `GET /api/attempts`
- 촬영 이미지: `GET /api/attempts/{attempt_id}/image`

관리자 HTTP는 서버 PC에서만 허용하며 POST에는 X-Attendance-Admin: 1 헤더를 사용합니다. 학생 WS 연결은 QR 토큰으로 세션을 확인합니다. 측정은 워밍업 2회 후 10회 평가, 응답당 제한 2초, 완료 응답 후 100ms 간격입니다. 대표값은 평가 10회의 중앙값입니다. 서버가 반환하는 relay.samples에는 warmup 여부와 각 RTT가 포함됩니다. 장소 API 미연동 또는 RTT 기준 미설정은 review로 처리합니다.
