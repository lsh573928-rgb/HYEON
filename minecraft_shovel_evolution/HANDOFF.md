# 맥북에서 이어서 하기

이 폴더는 클라우드 Claude Code 세션(2026-11-04)에서 만들었습니다.
GitHub 권한 문제로 push가 안 돼서, 압축 파일로 맥북에 옮기는 방법을 먼저 적었습니다.

## 방법 1 — 압축 파일로 옮기기 (지금 바로 가능)

1. 대화에 첨부된 `minecraft_shovel_evolution.zip`을 받아서 원하는 곳에 풉니다(예: `~/Projects/`).
2. 터미널에서 준비합니다(한 번만).
   ```bash
   cd ~/Projects/minecraft_shovel_evolution
   brew install ffmpeg                  # 없으면
   python3 -m pip install numpy pillow  # 없으면
   ```
3. 잘 되는지 확인합니다(약 3분 + 2초).
   ```bash
   cd source && python3 render.py && python3 sfx.py && python3 verify.py
   ```
4. 같은 폴더에서 `claude`를 실행하고 첫 메시지로 이렇게 보냅니다.
   > HANDOFF.md랑 README.md 읽고 이어서 작업해줘

   이 방법은 파일만 옮겨지고 대화 기록은 옮겨지지 않습니다. 필요한 맥락은 이 문서와 README에 다 적어 두었습니다.

## 방법 2 — 대화까지 통째로 가져오기 (`--teleport`)

1. https://claude.ai/connect-github 에서 GitHub를 다시 연결하고, 같은 페이지에서
   Claude GitHub App이 `lsh573928-rgb/HYEON` 저장소에 설치되어 있는지 확인합니다.
2. 클라우드 세션에 "push 다시 해줘"라고 보냅니다.
   그러면 브랜치 `claude/minecraft-shovel-evolution-mp4-t4l7jc`가 GitHub에 올라갑니다.
3. 맥북 터미널에서 아래를 실행합니다.
   ```bash
   git clone https://github.com/lsh573928-rgb/HYEON.git && cd HYEON
   claude --teleport          # 목록에서 이 세션 선택
   ```
   - Claude Code가 claude.ai 계정으로 로그인되어 있어야 합니다. 안 되어 있으면 `claude auth login`을 먼저 실행합니다.
   - 가져온 세션은 맥북에서 따로 이어집니다. 그 뒤 맥북에서 한 작업은 클라우드 세션에 나타나지 않습니다.

## 지금 상태

- 완료: 영상(효과음 포함, 무음본 따로 있음)·preview·thumbnail·검증(15개 항목 통과)·Threads 초안(`threads_post.md`).
- 로컬 커밋만 있고 push는 안 됐습니다. 원인은 GitHub App 권한입니다.
- 코드 구성
  - `source/pixelart.py`: 텍스처 정의
  - `source/scene.py`: 그리기 도구
  - `source/render.py`: 타임라인과 렌더
  - `source/sfx.py`: 효과음
  - `source/stills.py`: 미리보기·썸네일
  - `source/verify.py`: 검증

## 다음에 할 만한 일

- Threads·릴스용 세로 버전(1080×1350 또는 1080×1920)
  - `render.py`의 `W, H, CX, CY`와 배경 여백만 바꾸면 됩니다.
  - 삽 크기(`TEXEL`)는 그대로 두거나 조금 키웁니다.
- 효과음 크기 조정: `sfx.py` 각 함수의 `m.put(..., gain)`
- 공식 텍스처로 바꾸기(본인이 정식으로 가진 리소스만): `python3 render.py --textures <폴더>`
