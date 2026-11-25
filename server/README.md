# 관리자 서버 기반

Python/FastAPI + SQLite. 관리자 화면은 `/`, API 문서는 `/docs`, 학생 연결은 `/ws`입니다. 공유 GitHub 저장소에 올려도 되는 소스와 로컬 데이터가 분리되어 있습니다. 아직 GitHub 업로드는 하지 않았습니다.

## 실행
프로젝트 루트에서 실행합니다. 현재 패키지는 설치되어 있습니다.
```powershell
cd C:\Users\User\AttendanceDemo
.\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn server.app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 8388608 --no-proxy-headers
```
관리자: http://127.0.0.1:8000
학생 앱 연결 설정: ws://127.0.0.1:8000/ws
중계 경유: ws://127.0.0.1:8765 (중계 프로그램 별도 실행)

## 실제 인증 순서
1. 관리자 화면에서 장소 ID를 입력하고 QR 발급.
2. 학생 앱에서 서버에 연결하고 학생 ID 입력.
3. QR과 주변을 촬영하거나 QR 데이터 입력 후 사진 선택.
4. 인증하기. 서버는 사진 저장 후 워밍업 2회, 평가 10회 RTT를 측정.
5. 장소 검증 호출 후 결과 저장/전송. 관리자 화면에서 행을 클릭하면 사진과 실제 RTT 목록 확인.

장소 검증은 구현되어 기준 사진 등록 후 사용할 수 있습니다(`PLACE_VERIFICATION.md` 참고). RTT 기준 미설정으로 정상 완료도 **추가 확인**입니다. 가짜 일치 결과나 승인 처리는 하지 않습니다. 직접·중계 표본을 수집한 후 임계값을 정합니다. 이 버전은 10회 RTT의 **중앙값**을 판정하므로 임계값도 같은 방식의 표본으로 산정해야 합니다.

공동 작업자가 동일한 패키지 버전을 설치하려면 `server/requirements-lock.txt`를 사용하세요. 관리자 POST API를 직접 호출할 때는 `X-Attendance-Admin: 1` 헤더가 필요합니다. 기본 화면은 이 헤더를 자동으로 보냅니다. 현재 결과 조회는 관리자 화면/API에서만 제공하며, 학생 앱의 결과 재조회는 아직 포함하지 않습니다.

## 공동 개발 영역
```text
app/main.py             HTTP API와 앱 실행 진입점
app/auth.py             학생 인증 흐름·이미지 검증
app/schemas.py          공통 입력·출력 규격 (변경 시 공유)
app/store.py            세션·인증 결과 저장
app/relay/service.py    RTT 측정·판정 (모듈 3)
app/place/service.py    장소 검증 (모듈 2)
app/static/index.html   간단한 관리자 화면
data/                   자동 생성되는 DB·사진 (Git 제외)
```
`verify_place(place_id, image_path) -> PlaceResult`에 SIFT 기반 장소 검증을 구현했습니다. 기준 이미지를 place_id에 따라 조회해 비교하고 status를 match/non_match/inconclusive로 반환합니다. 기존 schemas.py의 수치 필드를 채우면 됩니다. 별도 서버를 운영할 경우 이 함수 안에서 외부 API를 호출하는 형태로 교체할 수 있습니다. 시간 제한은 15초이고 RTT 측정 완료 후 실행합니다.

## 설정
환경변수는 서버 실행 전에 PowerShell에서 지정합니다. .env 파일은 자동으로 읽지 않습니다.
- `ATTENDANCE_DATA_DIR`: DB/사진 저장 폴더 (기본 server/data)
- `RTT_THRESHOLD_MS`: 양의 숫자. 미설정이면 측정만 수행. 임계값 초과는 중계 의심.

## 범위와 주의사항
- 관리자 HTTP 화면/API는 서버 PC에서만 허용합니다. 다른 기기는 학생 WebSocket만 사용합니다. 프록시 헤더를 통한 관리자 우회 방지를 위해 --no-proxy-headers 옵션을 유지합니다.
- 학생 ID는 시연용 입력이며 계정 본인 인증은 아닙니다. QR 토큰·유효시간·세션 종료·attempt_id 중복 검증은 포함합니다. 같은 학생의 새 인증 시도는 별도로 기록합니다.
- 로컬 단일 프로세스로 실행합니다. 다중 worker와 운영 배포용 인증/권한 관리는 이번 기반에 포함하지 않습니다.
- 재시작 시 처리 중이던 인증은 interrupted로 보존합니다. 완료된 결과와 세션은 유지됩니다.
- 학생 앱의 브라우저 스케줄링, Wi-Fi와 서버 부하도 RTT에 포함됩니다. 애플리케이션 프록시 대리 응답 방어는 별도 암호학적 인증이 필요합니다.
- 사진 및 학번은 server/data에 저장됩니다. Git에 올리지 않습니다. 장소 기준 사진 역시 별도 로컬 폴더로 관리합니다.
- 휴대전화 카메라는 HTTPS/WSS 설정 후 사용합니다. 이 단계는 PC localhost 실행 기반입니다.
