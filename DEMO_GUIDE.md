# iPhone 출석 시연

## 연결 구성

- 정상: iPhone(서버 PC와 같은 Wi-Fi) → HTTPS 서버 8443
- 중계: iPhone(LTE/5G) → Cloudflare 임시 공개 주소 → 중계 프로그램 8766 → HTTPS 서버 8443
- 관리자: 서버 PC에서 https://localhost:8443/

외부 공개 입구에는 학생 화면과 WebSocket 중계만 있다. 관리자 API, 등록 이미지 조회, 인증 내역 조회는 공개 입구에 없으며 서버에서도 로컬 접근만 허용한다. 공개 주소에서 학생 앱을 여는 것은 누구나 가능하지만 인증·표본 수집에는 유효한 QR의 토큰이 필요하다. 시연용 QR과 사진만 사용한다.

공개 연결은 Cloudflare를 경유한다. 따라서 측정값에 이동통신·인터넷·터널·중계 프로그램의 지연이 함께 포함된다. 이 시연은 중계 프로그램만의 순수 오버헤드 측정이 아니다. 정상과 중계가 반드시 분리된다고 보장하지 않는다.

## 최초 준비

현재 확인한 Wi-Fi IPv4는 `192.168.219.49`이다. 장소 또는 Wi-Fi를 바꾸면 `ipconfig`에서 기본 게이트웨이가 있는 Wi-Fi의 IPv4를 다시 확인한다. VMware/WSL 주소를 사용하지 않는다.

프로젝트 PowerShell에서 실행한다. 명령의 IP는 실제 PC 주소로 바꾼다.

```powershell
cd C:\Users\User\AttendanceDemo
powershell -ExecutionPolicy Bypass -File .\scripts\setup-phone.ps1 -LanIP 192.168.219.49
```

학생 앱 빌드와 HTTPS 인증서를 준비한다. IP가 바뀌면 다시 실행한다. 기존 CA는 유지되므로 휴대폰에 재설치하지 않아도 된다. 인증서는 90일, CA는 1년이며 만료 시 재발급이 필요하다.

Windows에서 `certs\public\attendance-ca.cer`를 열어 **현재 사용자 → 신뢰할 수 있는 루트 인증 기관**에 설치하면 관리자 페이지의 인증서 경고를 없앨 수 있다. 이 프로젝트에서 생성한 인증서만 설치한다. `ca-key.pem`, `server-key.pem`은 휴대폰으로 보내지 않는다.

## iPhone 인증서 설치 (정상 Wi-Fi 연결에 필요)

1. iPhone과 PC를 같은 Wi-Fi에 연결한다.
2. 새 PowerShell에서 아래 명령을 실행한다.

```powershell
cd C:\Users\User\AttendanceDemo
powershell -ExecutionPolicy Bypass -File .\scripts\serve-phone-cert.ps1 -LanIP 192.168.219.49
```

3. Safari에서 `http://192.168.219.49:8081/attendance-ca.cer`를 열고 프로파일 다운로드를 허용한다.
4. iPhone 설정 → 일반 → VPN 및 기기 관리에서 Attendance Demo CA 프로파일을 설치한다.
5. 설정 → 일반 → 정보 → 인증서 신뢰 설정에서 Attendance Demo CA의 전체 신뢰를 켠다.
6. 다운로드 창은 Ctrl+C로 종료한다. 시연 후 더 이상 사용하지 않을 경우 프로파일을 삭제한다.

Apple 공식 안내: https://support.apple.com/en-us/102390

휴대폰에서 PC에 접속이 안 되면 Windows 방화벽에서 Python의 개인 네트워크 접근 허용을 확인한다. 필요한 인바운드 포트는 로컬 서브넷의 TCP 8443, 인증서 전달 중에는 8081이다. 학교/공용 Wi-Fi의 단말 간 통신 차단은 별도 공유기에서 시연하는 방법으로 해결한다. 방화벽 전체를 끄지 않는다.

## 실행: PowerShell 창 세 개

각 창에서 먼저 `cd C:\Users\User\AttendanceDemo`를 입력한다. 기존 8000 서버는 Ctrl+C로 종료한 뒤 아래 서버만 사용한다. 같은 DB를 사용하는 서버 두 개를 동시에 띄우지 않는다. Vite 5173은 이 시연에 필요 없다.

**창 1: 인증·관리 서버**
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-server.ps1
```

**창 2: 중계 프로그램**
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-relay.ps1
```

**창 3: 외부 주소 연결**
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-public.ps1
```

최초 실행은 Cloudflare 공식 배포 파일을 내려받고 공식 SHA256과 일치하는지 검사한다. `https://…trycloudflare.com` 주소가 출력되면 기록한다. 이 주소는 재실행 시 변경되며 해당 창을 종료하면 접속도 종료된다. 공유기 포트 포워딩은 필요 없다.

Cloudflare 공식 안내: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/

## 표본 확보와 판정 기준

1. 관리자 화면에서 장소 ID를 지정하고 기준 이미지 등록을 펼쳐 사진을 저장한다. 초기 Inlier 20개·비율 40%는 시연 가설값이며 검증된 논문 임계값이 아니다.
2. QR을 발급한다. 기준 이미지와 촬영 이미지에 같은 QR만 크게 포함되면 QR 특징점이 매칭을 지배할 수 있으므로 주변 환경이 충분히 보이도록 구성한다.
3. 정상 표본: iPhone Safari에서 `https://192.168.219.49:8443/student/` 접속 → 학생 ID 입력 → 카메라로 QR 인식 → RTT 표본 수집 → 수집 대기.
4. 관리자 RTT 기준 설정에서 대기 앱 선택 → Direct / 기준 설정 / 표본 수 입력 → 반복 수집.
5. 중계 표본: iPhone Wi-Fi를 끄고 LTE/5G에서 공개 주소의 `/student/`에 접속한다. 유효한 QR을 인식하거나 연결 설정의 QR 데이터에 관리자 QR JSON을 복사한다. 수집 대기 후 관리자에서 Relay / 기준 설정으로 반복 수집한다.
6. 1개 표본은 워밍업 2회 제외 후 10회 RTT의 중앙값이다. 표본 최소 개수 제한은 없고 Relay가 1개 이상이면 후보 임계값을 계산한다. 소표본에서 목표 90%는 매우 불안정하며 실제 비율은 100%처럼 계단식으로 나타날 수 있다.
7. 후보값은 등록 Relay의 최소 90%가 초과하도록 정한다. Direct 표본으로 FRR을 계산한다. 그래프·비율을 확인하고 **임계값 적용**을 누른다. 이후 인증에 반영된다.
8. 별도 평가를 선택하면 적용된 임계값으로 새 표본을 평가한다. 이 표본은 기준 설정에 추가하지 않는다. 적용값을 다시 바꾸면 별도 평가 화면은 새 기준에 해당하는 결과만 보여준다.
9. 수집 중 iPhone 화면을 켜 두고 Safari를 전면에 유지한다. 중지는 현재 표본이 끝난 뒤 적용된다. 측정 중 QR이 만료되면 새 QR을 발급한다.

## 영상 촬영 순서

1. 정상 Wi-Fi에서 QR과 주변 공간 촬영 → 인증하기 → 관리자에서 장소 일치, RTT와 적용 임계값 확인.
2. 장소 결과를 선택하고 장소 상세에서 원본 두 장, 실제 매칭 연결선, Inlier 수·비율을 보여준다.
3. 외부 장소의 LTE/5G에서 공개 주소로 접속하고 유효한 QR을 읽는다. QR을 먼저 인식한 뒤 다른 주변 사진을 촬영해도 현재 QR 세션이 유지된다.
4. 인증하며 중계 프로그램 창의 양방향 forwarded 로그를 보여준다.
5. 관리자에서 실제 장소 결과와 RTT 기준 초과 여부를 확인한다. 결과가 예상과 다르면 임의로 성공값을 표시하지 않고 실제 결과를 설명한다.

장소 결과는 일치/불일치/판정 불가이다. 특징점·대응점 부족이나 기준 이미지 미등록은 판정 불가이며 불일치와 구별한다. 최종 승인은 장소 일치와 지연 기준 충족을 모두 만족했을 때만 표시한다. 시연은 현장 실재성에 대한 보조 검증이며 사진 재사용 등 모든 우회를 막는 것은 아니다.

## 종료와 보존

세 창에서 각각 Ctrl+C. 인증 내역·사진·표본·적용값은 `server\data`에 남고 Git 대상에서는 제외된다. 소스만 공유하고 실제 사진·QR 토큰·인증서 개인키는 공유하지 않는다.
