# Claude Code 설치 메뉴얼

> 직원용 Claude Code 설치 가이드입니다. 아래 순서대로 따라하시면 됩니다.

---

## 목차

1. [시작 전 확인사항](#1-시작-전-확인사항)
2. [설치 방법 (운영체제별)](#2-설치-방법-운영체제별)
3. [로그인 및 인증](#3-로그인-및-인증)
4. [설치 확인](#4-설치-확인)
5. [자주 발생하는 문제](#5-자주-발생하는-문제)

---

## 1. 시작 전 확인사항

### 지원 운영체제

| 운영체제 | 최소 버전 |
|---------|---------|
| macOS | 13.0 이상 |
| Windows | 10 (1809) 이상 / Windows Server 2019 이상 |
| Ubuntu | 20.04 이상 |
| Debian | 10 이상 |

### 사전 요구사항

- RAM: 4GB 이상
- 인터넷 연결 필수
- **Windows 사용자**: 설치 전에 반드시 [Git for Windows](https://git-scm.com/downloads/win) 먼저 설치

---

## 2. 설치 방법 (운영체제별)

### macOS

터미널을 열고 아래 명령어를 실행하세요.

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

설치가 완료되면 터미널을 **재시작**하세요.

---

### Linux (Ubuntu / Debian)

터미널을 열고 아래 명령어를 실행하세요.

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

설치가 완료되면 터미널을 **재시작**하세요.

---

### Windows

#### 방법 1: PowerShell (권장)

PowerShell을 열고 아래 명령어를 실행하세요.

```powershell
irm https://claude.ai/install.ps1 | iex
```

#### 방법 2: WinGet

```powershell
winget install Anthropic.ClaudeCode
```

> **주의**: Git for Windows가 설치되어 있지 않으면 오류가 발생합니다.
> [Git for Windows 다운로드](https://git-scm.com/downloads/win) → 설치 시 "Add to PATH" 옵션 체크

설치 후 터미널(PowerShell 또는 CMD)을 **재시작**하세요.

---

### WSL (Windows Subsystem for Linux) 사용자

WSL 터미널에서 Linux와 동일하게 설치하세요.

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

---

## 3. 로그인 및 인증

설치 후 터미널에서 아래 명령어를 실행하면 인증이 시작됩니다.

```bash
claude
```

**자동으로 브라우저가 열립니다.** 브라우저가 열리지 않으면 터미널에 표시된 URL을 복사해서 브라우저에 직접 붙여넣으세요.

### 계정 유형별 안내

| 계정 유형 | 로그인 방법 |
|---------|----------|
| Claude Pro / Max 개인 구독 | claude.ai 계정으로 로그인 |
| Claude for Teams / Enterprise | 회사에서 제공한 계정으로 로그인 |
| Console 계정 | Console 계정으로 로그인 (관리자가 초대한 경우) |

> **주의**: 무료 Claude.ai 계정은 Claude Code를 사용할 수 없습니다.

---

## 4. 설치 확인

### 버전 확인

```bash
claude --version
```

버전 번호가 출력되면 설치 성공입니다.

### 상태 진단

```bash
claude doctor
```

설치 상태, 설정, 업데이트 여부 등을 자동으로 확인해줍니다.

---

## 5. 자주 발생하는 문제

### `command not found: claude` 오류

설치 후에도 `claude` 명령어를 찾지 못하는 경우입니다.

**macOS / Linux 해결법:**

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Bash를 사용하는 경우:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

**Windows PowerShell 해결법:**

```powershell
$currentPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
[Environment]::SetEnvironmentVariable('PATH', "$currentPath;$env:USERPROFILE\.local\bin", 'User')
```

이후 터미널을 재시작하세요.

---

### Windows: "Claude Code requires git-bash" 오류

Git for Windows가 설치되지 않은 경우입니다.

1. [Git for Windows](https://git-scm.com/downloads/win) 다운로드 및 설치
2. 설치 시 **"Add to PATH"** 옵션 반드시 체크
3. 터미널 재시작 후 다시 시도

---

### 로그인 후 403 오류 / 인증 실패

- 구독 상태를 [claude.ai/settings](https://claude.ai/settings)에서 확인하세요.
- `ANTHROPIC_API_KEY` 환경변수가 설정되어 있다면 제거하세요.

```bash
unset ANTHROPIC_API_KEY
claude
```

---

### 회사 네트워크 / 프록시 환경

회사 네트워크에서 설치가 안 될 경우, IT 담당자에게 프록시 설정을 요청하세요.

```bash
export HTTPS_PROXY=http://프록시주소:포트
export HTTP_PROXY=http://프록시주소:포트
curl -fsSL https://claude.ai/install.sh | bash
```

---

## 업데이트

Claude Code는 백그라운드에서 자동 업데이트됩니다. 수동으로 업데이트하려면:

```bash
claude update
```

---

## 문의

설치 중 문제가 발생하면 IT 담당자 또는 팀 관리자에게 문의하세요.

공식 문서: [claude.ai/code](https://claude.ai/code)
